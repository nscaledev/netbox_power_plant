from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from dcim.models import PowerPort
from netbox_power_plant.choices import PlacementScopeChoices
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    InstantiationArtifact,
    InstantiationRun,
    PowerHandoffPoint,
    RedundancyGroup,
)


@dataclass(frozen=True)
class ProposedArtifact:
    artifact_type: str
    action: str
    template_key: str
    stable_slug: str
    proposed_data: dict
    object: object = None
    status: str = "proposed"


@dataclass(frozen=True)
class InstantiationResult:
    run: InstantiationRun
    artifacts: tuple[ProposedArtifact, ...]

    @property
    def total_count(self):
        return len(self.artifacts)

    @property
    def created_count(self):
        return len([artifact for artifact in self.artifacts if artifact.action == "create"])

    @property
    def updated_count(self):
        return len([artifact for artifact in self.artifacts if artifact.action == "update"])

    @property
    def skipped_count(self):
        return len(
            [artifact for artifact in self.artifacts if artifact.action == "skip" or artifact.status == "skipped"]
        )

    @property
    def artifact_summaries(self):
        return tuple(_artifact_summary(artifact) for artifact in self.artifacts)

    @property
    def summary(self):
        by_type = {}
        for artifact in self.artifacts:
            type_counts = by_type.setdefault(
                artifact.artifact_type,
                {"total": 0, "create": 0, "update": 0, "skip": 0, "applied": 0, "proposed": 0, "skipped": 0},
            )
            type_counts["total"] += 1
            type_counts[artifact.action] = type_counts.get(artifact.action, 0) + 1
            type_counts[artifact.status] = type_counts.get(artifact.status, 0) + 1
        return {
            "total": self.total_count,
            "created": self.created_count,
            "updated": self.updated_count,
            "skipped": self.skipped_count,
            "by_type": by_type,
        }


class TemplateContext(dict):
    def __missing__(self, key):
        return ""


def instantiate_template(power_system, template, context=None, apply=False):
    """
    Stamp a power architecture template into a power system.

    Dry-runs persist an InstantiationRun with proposed artifacts only. Apply mode
    records the same proposal shape, then attaches each artifact to the created or
    updated object for provenance.
    """
    merged_context = _build_context(power_system, template, context)
    with transaction.atomic():
        run = _create_run(power_system, template, merged_context, dry_run=not apply)
        proposals = _build_proposals(power_system, template, merged_context)
        object_map = {}

        if apply:
            object_map = _apply_proposals(power_system, proposals)
            power_system.is_template_derived = True
            power_system.save(update_fields=("is_template_derived",))

        artifacts = tuple(
            _persist_artifact(
                run,
                proposal,
                object_map.get((proposal.artifact_type, proposal.template_key)) if apply else proposal.object,
                applied=apply,
            )
            for proposal in proposals
        )
        run.artifact_count = len(artifacts)
        run.status = "applied" if apply else "dry-run"
        run.save(update_fields=("artifact_count", "status"))

    return InstantiationResult(run=run, artifacts=artifacts)


def apply_existing_instantiation_run(run):
    """
    Apply the proposed artifacts from an existing dry-run.

    The existing InstantiationArtifact rows are updated in place so downstream
    audit links remain attached to the original reviewable dry-run artifact.
    """
    with transaction.atomic():
        run = InstantiationRun.objects.select_for_update().select_related("power_system", "template").get(pk=run.pk)
        artifacts = tuple(run.artifacts.select_for_update().order_by("artifact_type", "template_key", "pk"))
        proposals = tuple(_proposal_from_artifact(artifact) for artifact in artifacts)
        object_map = _apply_proposals(run.power_system, proposals)

        persisted = tuple(
            _update_artifact_from_application(
                artifact,
                proposal,
                object_map.get((proposal.artifact_type, proposal.template_key)),
            )
            for artifact, proposal in zip(artifacts, proposals, strict=True)
        )
        run.artifact_count = len(persisted)
        run.status = "applied"
        run.dry_run = False
        run.power_system.is_template_derived = True
        run.power_system.save(update_fields=("is_template_derived",))
        run.save(update_fields=("artifact_count", "status", "dry_run"))

    return InstantiationResult(run=run, artifacts=persisted)


def _create_run(power_system, template, context, dry_run):
    timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
    mode = "dry-run" if dry_run else "apply"
    base_slug = _truncate_slug(f"{power_system.slug}-{template.slug}-{mode}-{timestamp}")
    return InstantiationRun.objects.create(
        name=_truncate_name(f"{power_system.name} {template.name} {mode} {timestamp}"),
        slug=base_slug,
        power_system=power_system,
        template=template,
        status="pending",
        dry_run=dry_run,
        context=context,
    )


def _build_context(power_system, template, context):
    merged = {}
    merged.update(template.default_context or {})
    merged.update(context or {})
    merged.update(
        {
            "power_system": power_system.name,
            "power_system_slug": power_system.slug,
            "template": template.name,
            "template_slug": template.slug,
            "site": power_system.site.name,
            "site_slug": power_system.site.slug,
            "location": power_system.location.name if power_system.location_id else "",
            "location_slug": power_system.location.slug if power_system.location_id else "",
        }
    )
    return merged


def _build_proposals(power_system, template, context):
    proposals = []
    template_nodes = tuple(template.nodes.prefetch_related("terminals", "placement_rule").order_by("key"))

    for template_node in template_nodes:
        for node_key, node_context, node_attributes in _expand_template_item(
            template_node.key,
            template_node.attributes,
            context,
        ):
            parent_key = (
                _render_attribute_format(node_attributes, "parent_key_format", node_context) or template_node.parent_key
            )
            node_slug = _stable_slug(power_system, template, "node", node_key, template_node.slug_format, node_context)
            node_name = _stable_name(
                power_system,
                template,
                "Node",
                node_key,
                template_node.name_format,
                node_context,
            )
            node_data = {
                "name": node_name,
                "slug": node_slug,
                "power_system": power_system.pk,
                "site": power_system.site_id,
                "location": power_system.location_id,
                "parent_key": parent_key,
                "node_kind": template_node.node_kind,
                "equipment_role": template_node.equipment_role,
                "phase_mode": template_node.phase_mode,
                "install_state": template_node.install_state,
                "topology_state": template_node.topology_state,
            }
            node_data.update(node_attributes)
            proposals.append(_proposal("node", node_key, node_slug, node_data, ElectricalNode))

            for template_terminal in template_node.terminals.order_by("position_index", "key"):
                terminal_local_key = _render_key(template_terminal.key, node_context)
                terminal_key = _terminal_template_key(node_key, terminal_local_key)
                terminal_slug = _stable_slug(
                    power_system,
                    template,
                    "terminal",
                    terminal_key,
                    template_terminal.slug_format,
                    node_context,
                )
                terminal_name = _stable_name(
                    power_system,
                    template,
                    "Terminal",
                    terminal_key,
                    template_terminal.name_format,
                    node_context,
                )
                terminal_data = {
                    "name": terminal_name,
                    "slug": terminal_slug,
                    "node_key": node_key,
                    "terminal_role": template_terminal.terminal_role,
                    "direction": template_terminal.direction,
                    "supply_type": template_terminal.supply_type,
                    "position_index": template_terminal.position_index,
                }
                terminal_data.update(template_terminal.attributes or {})
                proposals.append(_proposal("terminal", terminal_key, terminal_slug, terminal_data, ElectricalTerminal))

            for handoff in node_attributes.get("power_handoffs", ()):
                proposals.append(_handoff_proposal(power_system, template, node_key, node_context, handoff))

            placement_rule = getattr(template_node, "placement_rule", None)
            if placement_rule is not None:
                placement_key = f"{node_key}:placement"
                placement_slug = _stable_slug(power_system, template, "placement", node_key, "", node_context)
                placement_data = {
                    "name": _stable_name(power_system, template, "Placement", node_key, "", node_context),
                    "slug": placement_slug,
                    "power_system": power_system.pk,
                    "node_key": node_key,
                    "site": power_system.site_id,
                    "location": (
                        power_system.location_id
                        if placement_rule.placement_scope_type == PlacementScopeChoices.SCOPE_LOCATION
                        else None
                    ),
                    "placement_scope_type": placement_rule.placement_scope_type,
                    "x": placement_rule.x,
                    "y": placement_rule.y,
                    "width": placement_rule.width,
                    "height": placement_rule.height,
                    "rotation_degrees": placement_rule.rotation_degrees,
                    "symbol_kind": placement_rule.symbol_kind,
                    "label_mode": placement_rule.label_mode,
                    "color": placement_rule.color,
                    "z_index": placement_rule.z_index,
                }
                proposals.append(
                    _proposal("placement", placement_key, placement_slug, placement_data, ElectricalNodePlacement)
                )

    for template_segment in template.segments.order_by("key"):
        for segment_key, segment_context, segment_attributes in _expand_template_item(
            template_segment.key,
            template_segment.attributes,
            context,
        ):
            segment_slug = _stable_slug(
                power_system,
                template,
                "segment",
                segment_key,
                template_segment.slug_format,
                segment_context,
            )
            segment_data = {
                "name": _stable_name(
                    power_system,
                    template,
                    "Segment",
                    segment_key,
                    template_segment.name_format,
                    segment_context,
                ),
                "slug": segment_slug,
                "power_system": power_system.pk,
                "from_node_key": _render_attribute_format(
                    segment_attributes,
                    "from_node_key_format",
                    segment_context,
                )
                or template_segment.from_node_key,
                "from_terminal_key": _render_attribute_format(
                    segment_attributes,
                    "from_terminal_key_format",
                    segment_context,
                )
                or template_segment.from_terminal_key,
                "to_node_key": _render_attribute_format(segment_attributes, "to_node_key_format", segment_context)
                or template_segment.to_node_key,
                "to_terminal_key": _render_attribute_format(
                    segment_attributes,
                    "to_terminal_key_format",
                    segment_context,
                )
                or template_segment.to_terminal_key,
                "segment_kind": template_segment.segment_kind,
                "path_state": template_segment.path_state,
            }
            segment_data.update(segment_attributes)
            proposals.append(_proposal("segment", segment_key, segment_slug, segment_data, ElectricalSegment))

    return tuple(proposals)


def _proposal(artifact_type, template_key, stable_slug, data, model):
    existing = model.objects.filter(slug=stable_slug).first()
    action = "update" if existing is not None else "create"
    data = _with_review_metadata(
        data,
        artifact_type=artifact_type,
        action=action,
        status="proposed",
        template_key=template_key,
        stable_slug=stable_slug,
        obj=existing,
    )
    return ProposedArtifact(
        artifact_type=artifact_type,
        action=action,
        template_key=template_key,
        stable_slug=stable_slug,
        proposed_data=_json_ready(data),
        object=existing,
    )


def _skip_proposal(artifact_type, template_key, stable_slug, data, reason):
    proposed_data = dict(data)
    proposed_data["skip_reason"] = reason
    proposed_data = _with_review_metadata(
        proposed_data,
        artifact_type=artifact_type,
        action="skip",
        status="skipped",
        template_key=template_key,
        stable_slug=stable_slug,
        skip_reason=reason,
    )
    return ProposedArtifact(
        artifact_type=artifact_type,
        action="skip",
        template_key=template_key,
        stable_slug=stable_slug,
        proposed_data=_json_ready(proposed_data),
        status="skipped",
    )


def _handoff_proposal(power_system, template, node_key, context, handoff):
    handoff_context = TemplateContext(context)
    handoff_key = _render(str(handoff.get("key") or f"{node_key}-handoff"), handoff_context)
    template_key = _truncate_name(f"{node_key}:{handoff_key}")
    stable_slug = _stable_slug(
        power_system,
        template,
        "power-handoff",
        template_key,
        handoff.get("slug_format", ""),
        handoff_context,
    )
    terminal_key = _render(str(handoff.get("terminal_key", "")), handoff_context)
    terminal_template_key = _terminal_template_key(node_key, terminal_key) if terminal_key else ""
    data = {
        "name": _stable_name(
            power_system,
            template,
            "Power Handoff",
            template_key,
            handoff.get("name_format", ""),
            handoff_context,
        ),
        "slug": stable_slug,
        "power_system": power_system.pk,
        "electrical_node_key": node_key,
        "electrical_terminal_key": terminal_template_key,
        "power_port_context_key": handoff.get("power_port_context_key", ""),
        "expected_redundancy_group_context_key": handoff.get("expected_redundancy_group_context_key", ""),
        "delivery_role": _render(str(handoff.get("delivery_role", "")), handoff_context),
        "feed_label": _render(str(handoff.get("feed_label", "")), handoff_context),
    }

    if not terminal_template_key:
        return _skip_proposal("power_handoff", template_key, stable_slug, data, "terminal_key is required.")

    power_port_context_key = _render(str(handoff.get("power_port_context_key", "")), handoff_context)
    power_port_id = context.get(power_port_context_key) if power_port_context_key else None
    if not power_port_id:
        return _skip_proposal(
            "power_handoff",
            template_key,
            stable_slug,
            data,
            f'PowerPort context key "{power_port_context_key}" is required.',
        )
    power_port = _resolve_power_port(power_port_id)
    if power_port is None:
        return _skip_proposal(
            "power_handoff",
            template_key,
            stable_slug,
            data,
            f"PowerPort {power_port_id} was not found.",
        )
    data["power_port"] = power_port.pk

    redundancy_context_key = _render(str(handoff.get("expected_redundancy_group_context_key", "")), handoff_context)
    if redundancy_context_key:
        redundancy_group_id = context.get(redundancy_context_key)
        if not redundancy_group_id:
            return _skip_proposal(
                "power_handoff",
                template_key,
                stable_slug,
                data,
                f'RedundancyGroup context key "{redundancy_context_key}" is required.',
            )
        redundancy_group = _resolve_redundancy_group(power_system, redundancy_group_id)
        if redundancy_group is None:
            return _skip_proposal(
                "power_handoff",
                template_key,
                stable_slug,
                data,
                f"RedundancyGroup {redundancy_group_id} was not found for this power system.",
            )
        data["expected_redundancy_group"] = redundancy_group.pk

    return _proposal("power_handoff", template_key, stable_slug, data, PowerHandoffPoint)


def _apply_proposals(power_system, proposals):
    object_map = {}
    node_map = {}
    terminal_map = {}

    for proposal in [item for item in proposals if item.artifact_type == "node"]:
        data = dict(proposal.proposed_data)
        parent_key = data.pop("parent_key", "")
        data["power_system"] = power_system
        data["site"] = power_system.site
        data["location"] = power_system.location
        node, _ = ElectricalNode.objects.update_or_create(
            slug=proposal.stable_slug,
            defaults=_model_defaults(ElectricalNode, data),
        )
        node._template_parent_key = parent_key
        object_map[(proposal.artifact_type, proposal.template_key)] = node
        node_map[proposal.template_key] = node

    for key, node in node_map.items():
        parent_key = getattr(node, "_template_parent_key", "")
        parent = node_map.get(parent_key)
        if parent and node.parent_node_id != parent.pk:
            node.parent_node = parent
            node.save(update_fields=("parent_node",))

    for proposal in [item for item in proposals if item.artifact_type == "terminal"]:
        data = dict(proposal.proposed_data)
        node = node_map[data.pop("node_key")]
        data["node"] = node
        terminal, _ = ElectricalTerminal.objects.update_or_create(
            slug=proposal.stable_slug,
            defaults=_model_defaults(ElectricalTerminal, data),
        )
        object_map[(proposal.artifact_type, proposal.template_key)] = terminal
        terminal_map[proposal.template_key] = terminal

    for proposal in [item for item in proposals if item.artifact_type == "placement"]:
        data = dict(proposal.proposed_data)
        node = node_map[data.pop("node_key")]
        data["power_system"] = power_system
        data["electrical_node"] = node
        data["site"] = power_system.site
        data["location"] = power_system.location if data.get("location") else None
        placement, _ = ElectricalNodePlacement.objects.update_or_create(
            slug=proposal.stable_slug,
            defaults=_model_defaults(ElectricalNodePlacement, data),
        )
        object_map[(proposal.artifact_type, proposal.template_key)] = placement

    for proposal in [item for item in proposals if item.artifact_type == "segment"]:
        data = dict(proposal.proposed_data)
        from_terminal = terminal_map[_terminal_template_key(data.pop("from_node_key"), data.pop("from_terminal_key"))]
        to_terminal = terminal_map[_terminal_template_key(data.pop("to_node_key"), data.pop("to_terminal_key"))]
        data["power_system"] = power_system
        data["from_terminal"] = from_terminal
        data["to_terminal"] = to_terminal
        segment, _ = ElectricalSegment.objects.update_or_create(
            slug=proposal.stable_slug,
            defaults=_model_defaults(ElectricalSegment, data),
        )
        object_map[(proposal.artifact_type, proposal.template_key)] = segment

    for proposal in [item for item in proposals if item.artifact_type == "power_handoff"]:
        if proposal.action == "skip" or proposal.status == "skipped":
            continue
        data = dict(proposal.proposed_data)
        node = node_map[data.pop("electrical_node_key")]
        terminal = terminal_map[data.pop("electrical_terminal_key")]
        power_port = PowerPort.objects.get(pk=data.pop("power_port"))
        redundancy_group_id = data.pop("expected_redundancy_group", None)
        data["power_system"] = power_system
        data["electrical_node"] = node
        data["electrical_terminal"] = terminal
        data["power_port"] = power_port
        data["expected_redundancy_group"] = (
            RedundancyGroup.objects.get(pk=redundancy_group_id) if redundancy_group_id else None
        )
        handoff, _ = PowerHandoffPoint.objects.update_or_create(
            slug=proposal.stable_slug,
            defaults=_model_defaults(PowerHandoffPoint, data),
        )
        handoff.full_clean()
        handoff.save()
        object_map[(proposal.artifact_type, proposal.template_key)] = handoff

    return object_map


def _persist_artifact(run, proposal, obj, *, applied=False):
    object_type = None
    object_id = None
    status = proposal.status
    action = proposal.action

    if obj is not None:
        object_type = ContentType.objects.get_for_model(obj)
        object_id = obj.pk
        if applied:
            status = "applied"
            action = "update" if proposal.object is not None else "create"

    artifact = InstantiationArtifact.objects.create(
        name=_artifact_name(run, proposal),
        slug=_artifact_slug(run, proposal),
        run=run,
        artifact_type=proposal.artifact_type,
        action=action,
        status=status,
        template_key=proposal.template_key,
        stable_slug=proposal.stable_slug,
        object_type=object_type,
        object_id=object_id,
        proposed_data=proposal.proposed_data,
    )
    return ProposedArtifact(
        artifact_type=artifact.artifact_type,
        action=artifact.action,
        template_key=artifact.template_key,
        stable_slug=artifact.stable_slug,
        proposed_data=artifact.proposed_data,
        object=obj,
        status=artifact.status,
    )


def _update_artifact_from_application(artifact, proposal, obj):
    artifact.object_type = None
    artifact.object_id = None
    artifact.action = proposal.action
    artifact.status = proposal.status

    if obj is not None:
        artifact.object_type = ContentType.objects.get_for_model(obj)
        artifact.object_id = obj.pk
        artifact.status = "applied"
        artifact.action = "update" if proposal.object is not None else "create"

    artifact.save(update_fields=("object_type", "object_id", "action", "status"))
    return ProposedArtifact(
        artifact_type=artifact.artifact_type,
        action=artifact.action,
        template_key=artifact.template_key,
        stable_slug=artifact.stable_slug,
        proposed_data=artifact.proposed_data,
        object=obj,
        status=artifact.status,
    )


def _proposal_from_artifact(artifact):
    if artifact.action == "skip" or artifact.status == "skipped":
        return ProposedArtifact(
            artifact_type=artifact.artifact_type,
            action="skip",
            template_key=artifact.template_key,
            stable_slug=artifact.stable_slug,
            proposed_data=artifact.proposed_data,
            object=artifact.object,
            status="skipped",
        )

    model = _model_for_artifact_type(artifact.artifact_type)
    existing = model.objects.filter(slug=artifact.stable_slug).first() if model is not None else None
    return ProposedArtifact(
        artifact_type=artifact.artifact_type,
        action="update" if existing is not None else "create",
        template_key=artifact.template_key,
        stable_slug=artifact.stable_slug,
        proposed_data=artifact.proposed_data,
        object=existing,
        status="proposed",
    )


def _model_for_artifact_type(artifact_type):
    return {
        "node": ElectricalNode,
        "terminal": ElectricalTerminal,
        "placement": ElectricalNodePlacement,
        "segment": ElectricalSegment,
        "power_handoff": PowerHandoffPoint,
    }.get(artifact_type)


def _artifact_name(run, proposal):
    base = _truncate_name(run.name)[:64].strip()
    fingerprint = _artifact_fingerprint(proposal)
    return _truncate_name(f"{base} {proposal.artifact_type} {fingerprint} {proposal.template_key}")


def _artifact_slug(run, proposal):
    base = _truncate_slug(run.slug)[:64].strip("-")
    fingerprint = _artifact_fingerprint(proposal)
    return _truncate_slug(f"{base}-{proposal.artifact_type}-{fingerprint}-{proposal.template_key}")


def _artifact_fingerprint(proposal):
    value = f"{proposal.artifact_type}:{proposal.template_key}:{proposal.stable_slug}"
    return sha1(value.encode()).hexdigest()[:8]


def _artifact_summary(artifact):
    data = artifact.proposed_data or {}
    review = data.get("review", {})
    return {
        "artifact_type": artifact.artifact_type,
        "action": artifact.action,
        "status": artifact.status,
        "template_key": artifact.template_key,
        "stable_slug": artifact.stable_slug,
        "template_ref": review.get("template_ref")
        or {
            "artifact_type": artifact.artifact_type,
            "template_key": artifact.template_key,
            "stable_slug": artifact.stable_slug,
        },
        "object_ref": _object_ref(artifact.object) if artifact.object is not None else review.get("object_ref"),
        "proposed_name": data.get("name"),
        "proposed_type": _proposed_type(artifact.artifact_type, data),
        "skip_reason": data.get("skip_reason"),
        "operator_summary": review.get("operator_summary")
        or _operator_summary(
            artifact.artifact_type,
            artifact.action,
            artifact.status,
            data,
        ),
    }


def _with_review_metadata(
    data,
    *,
    artifact_type,
    action,
    status,
    template_key,
    stable_slug,
    obj=None,
    skip_reason="",
):
    proposed_data = dict(data)
    proposed_data["review"] = {
        "template_ref": {
            "artifact_type": artifact_type,
            "template_key": template_key,
            "stable_slug": stable_slug,
        },
        "object_ref": _object_ref(obj),
        "proposed": {
            "name": proposed_data.get("name", ""),
            "type": _proposed_type(artifact_type, proposed_data),
        },
        "operator_summary": _operator_summary(artifact_type, action, status, proposed_data, skip_reason=skip_reason),
    }
    return proposed_data


def _operator_summary(artifact_type, action, status, data, *, skip_reason=""):
    name = data.get("name") or data.get("slug") or data.get("stable_slug") or "unnamed artifact"
    proposed_type = _proposed_type(artifact_type, data)
    if action == "skip" or status == "skipped":
        reason = skip_reason or data.get("skip_reason") or "No reason provided."
        return f'Skip {artifact_type} "{name}": {reason}'
    verb = "Update" if action == "update" else "Create"
    if proposed_type:
        return f'{verb} {artifact_type} "{name}" ({proposed_type}).'
    return f'{verb} {artifact_type} "{name}".'


def _proposed_type(artifact_type, data):
    if artifact_type == "node":
        return data.get("node_kind", "")
    if artifact_type == "terminal":
        return data.get("terminal_role", "")
    if artifact_type == "segment":
        return data.get("segment_kind", "")
    if artifact_type == "placement":
        return data.get("symbol_kind", "")
    if artifact_type == "power_handoff":
        return data.get("delivery_role") or data.get("feed_label", "")
    return ""


def _object_ref(obj):
    if obj is None:
        return None
    return {
        "id": obj.pk,
        "model": obj._meta.label_lower,
        "display": str(obj),
        "slug": getattr(obj, "slug", ""),
    }


def _stable_slug(power_system, template, artifact_type, key, format_string, context):
    if format_string:
        return _truncate_slug(slugify(_render(format_string, context)))
    return _truncate_slug(f"{power_system.slug}-{template.slug}-{artifact_type}-{slugify(key)}")


def _stable_name(power_system, template, artifact_label, key, format_string, context):
    if format_string:
        return _truncate_name(_render(format_string, context))
    return _truncate_name(f"{power_system.name} {template.name} {artifact_label} {key}")


def _expand_template_item(key, attributes, context):
    attributes = dict(attributes or {})
    repeat = attributes.pop("repeat", None)
    if not repeat:
        return ((key, context, attributes),)

    repeat = dict(repeat)
    count = repeat.get("count")
    if repeat.get("count_context_key"):
        count = context.get(repeat["count_context_key"], count)
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = 0

    start = int(repeat.get("start", 1))
    context_key = repeat.get("context_key", "counter")
    key_format = repeat.get("key_format", f"{key}-{{{context_key}}}")
    expanded = []
    for index in range(max(count, 0)):
        counter = start + index
        item_context = dict(context)
        item_context.update(
            {
                "repeat_index": index,
                "repeat_number": counter,
                "counter": counter,
                context_key: counter,
            }
        )
        expanded.append((_render_key(key_format, item_context), item_context, dict(attributes)))
    return tuple(expanded)


def _render_attribute_format(attributes, key, context):
    format_string = attributes.pop(key, "")
    return _render(str(format_string), context) if format_string else ""


def _render_key(value, context):
    return _truncate_slug(_render(str(value), context))


def _render(format_string, context):
    return format_string.format_map(TemplateContext(context))


def _terminal_template_key(node_key, terminal_key):
    return f"{node_key}:{terminal_key}"


def _truncate_name(value):
    return str(value).strip()[:100]


def _truncate_slug(value):
    slug = slugify(value)[:100]
    return slug or "template-artifact"


def _model_defaults(model, data):
    field_names = {field.name for field in model._meta.fields}
    return {key: value for key, value in data.items() if key in field_names}


def _resolve_power_port(value):
    if isinstance(value, PowerPort):
        return value
    return PowerPort.objects.filter(pk=value).first()


def _resolve_redundancy_group(power_system, value):
    if isinstance(value, RedundancyGroup):
        value = value.pk
    return RedundancyGroup.objects.filter(power_system=power_system, pk=value).first()


def _json_ready(data):
    if isinstance(data, dict):
        return {key: _json_ready(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [_json_ready(value) for value in data]
    if isinstance(data, Decimal):
        return str(data)
    if isinstance(data, (PowerPort, RedundancyGroup)):
        return data.pk
    return data
