from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from dcim.models import PowerPort

from netbox_power_plant.choices import (
    InternalPowerBusAttachmentRoleChoices,
    PowerFindingSeverityChoices,
    TerminalDirectionChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import InternalPowerBus, InternalPowerBusAttachment, PowerHandoffPoint
from netbox_power_plant.services.graph import PowerGraphBuilder
from netbox_power_plant.services.rack_delivery import RACK_BOUNDARY_NODE_KINDS


@dataclass(frozen=True)
class RackBoundaryCandidate:
    node: object
    terminal: object
    has_active_path: bool
    inbound_segment_count: int


@dataclass(frozen=True)
class TargetPowerPortIssue:
    owner: object
    power_port: object | None
    finding_type: str
    message: str


@dataclass(frozen=True)
class InternalBusAttachmentCoverage:
    buses: tuple
    attachments: tuple
    candidate_power_ports: tuple
    covered_power_ports: tuple
    uncovered_power_ports: tuple
    stale_attachments: tuple[TargetPowerPortIssue, ...]
    source_attachment_count: int
    load_attachment_count: int

    @property
    def bus_count(self) -> int:
        return len(self.buses)

    @property
    def attachment_count(self) -> int:
        return len(self.attachments)

    @property
    def candidate_power_port_count(self) -> int:
        return len(self.candidate_power_ports)

    @property
    def covered_power_port_count(self) -> int:
        return len(self.covered_power_ports)

    @property
    def uncovered_power_port_count(self) -> int:
        return len(self.uncovered_power_ports)

    @property
    def stale_attachment_count(self) -> int:
        return len(self.stale_attachments)


@dataclass(frozen=True)
class PowerSystemCompletenessSummary:
    power_system: object
    rack_boundary_candidates: tuple[RackBoundaryCandidate, ...]
    modeled_handoffs: tuple
    handoffs_with_active_path: tuple
    handoffs_without_active_path: tuple
    target_power_port_issues: tuple[TargetPowerPortIssue, ...]
    scoped_power_ports: tuple
    unmodeled_power_ports: tuple
    internal_bus_coverage: InternalBusAttachmentCoverage
    findings: tuple[dict, ...]

    @property
    def total_rack_boundary_candidates(self) -> int:
        return len(self.rack_boundary_candidates)

    @property
    def modeled_handoff_count(self) -> int:
        return len(self.modeled_handoffs)

    @property
    def handoffs_with_active_graph_path_count(self) -> int:
        return len(self.handoffs_with_active_path)

    @property
    def handoffs_without_active_path_count(self) -> int:
        return len(self.handoffs_without_active_path)

    @property
    def target_power_ports_missing_or_stale_count(self) -> int:
        return len(self.target_power_port_issues)

    @property
    def unmodeled_power_port_count(self) -> int:
        return len(self.unmodeled_power_ports)

    @property
    def finding_count(self) -> int:
        return len(self.findings)


def build_power_system_completeness_summary(power_system) -> PowerSystemCompletenessSummary:
    snapshot = PowerGraphBuilder.build_for_power_system(
        power_system,
        node_states=(TopologyStateChoices.STATE_ACTIVE,),
        path_states=(TopologyStateChoices.STATE_ACTIVE,),
    )
    rack_boundary_candidates = _rack_boundary_candidates(snapshot)
    candidate_by_terminal_id = {candidate.terminal.pk: candidate for candidate in rack_boundary_candidates}
    candidates_by_node_id = _candidates_by_node_id(rack_boundary_candidates)

    modeled_handoffs = _handoffs(power_system)
    handoffs_with_active_path = []
    handoffs_without_active_path = []
    modeled_candidate_terminal_ids = set()

    for handoff in modeled_handoffs:
        candidate = _candidate_for_handoff(handoff, candidate_by_terminal_id, candidates_by_node_id)
        if candidate is not None:
            modeled_candidate_terminal_ids.add(candidate.terminal.pk)
        if candidate is not None and candidate.has_active_path:
            handoffs_with_active_path.append(handoff)
        else:
            handoffs_without_active_path.append(handoff)

    target_power_port_issues = tuple(
        issue
        for handoff in modeled_handoffs
        for issue in (_handoff_power_port_issue(power_system, handoff),)
        if issue is not None
    )
    scoped_power_ports = _scoped_power_ports(power_system)
    internal_bus_coverage = _internal_bus_attachment_coverage(power_system, scoped_power_ports)
    modeled_power_port_ids = _modeled_power_port_ids(modeled_handoffs, internal_bus_coverage.attachments)
    unmodeled_power_ports = tuple(
        power_port for power_port in scoped_power_ports if power_port.pk not in modeled_power_port_ids
    )
    findings = _build_findings(
        rack_boundary_candidates=rack_boundary_candidates,
        modeled_candidate_terminal_ids=modeled_candidate_terminal_ids,
        handoffs_without_active_path=tuple(handoffs_without_active_path),
        target_power_port_issues=target_power_port_issues,
        unmodeled_power_ports=unmodeled_power_ports,
        internal_bus_coverage=internal_bus_coverage,
    )

    return PowerSystemCompletenessSummary(
        power_system=power_system,
        rack_boundary_candidates=rack_boundary_candidates,
        modeled_handoffs=modeled_handoffs,
        handoffs_with_active_path=tuple(handoffs_with_active_path),
        handoffs_without_active_path=tuple(handoffs_without_active_path),
        target_power_port_issues=target_power_port_issues,
        scoped_power_ports=scoped_power_ports,
        unmodeled_power_ports=unmodeled_power_ports,
        internal_bus_coverage=internal_bus_coverage,
        findings=findings,
    )


def build_completeness_findings(power_system) -> tuple[dict, ...]:
    return build_power_system_completeness_summary(power_system).findings


build_completeness_summary = build_power_system_completeness_summary


def _rack_boundary_candidates(snapshot) -> tuple[RackBoundaryCandidate, ...]:
    candidates = []
    terminals = sorted(
        snapshot.terminals_by_id.values(),
        key=lambda terminal: (terminal.node.name, terminal.position_index or 0, terminal.name, terminal.pk),
    )
    for terminal in terminals:
        node = snapshot.nodes_by_id.get(terminal.node_id)
        if node is None or node.node_kind not in RACK_BOUNDARY_NODE_KINDS:
            continue
        if terminal.direction not in (
            TerminalDirectionChoices.DIRECTION_SINK,
            TerminalDirectionChoices.DIRECTION_BIDIRECTIONAL,
        ):
            continue

        inbound_segment_ids = snapshot.inbound_segments_by_terminal_id.get(terminal.pk, set())
        candidates.append(
            RackBoundaryCandidate(
                node=node,
                terminal=terminal,
                has_active_path=bool(inbound_segment_ids),
                inbound_segment_count=len(inbound_segment_ids),
            )
        )

    return tuple(candidates)


def _candidates_by_node_id(candidates):
    candidates_by_node_id = {}
    for candidate in candidates:
        candidates_by_node_id.setdefault(candidate.node.pk, []).append(candidate)
    return {node_id: tuple(node_candidates) for node_id, node_candidates in candidates_by_node_id.items()}


def _candidate_for_handoff(handoff, candidate_by_terminal_id, candidates_by_node_id):
    if handoff.electrical_terminal_id:
        return candidate_by_terminal_id.get(handoff.electrical_terminal_id)

    if handoff.electrical_node_id:
        node_candidates = candidates_by_node_id.get(handoff.electrical_node_id, ())
        if len(node_candidates) == 1:
            return node_candidates[0]

    return None


def _handoffs(power_system) -> tuple:
    return tuple(
        PowerHandoffPoint.objects.filter(power_system=power_system)
        .select_related(
            "electrical_node",
            "electrical_terminal__node",
            "power_port__device",
            "power_port__device__rack",
        )
        .order_by("name", "pk")
    )


def _scoped_power_ports(power_system) -> tuple:
    power_ports = (
        PowerPort.objects.select_related("device", "device__rack")
        .filter(device__site=power_system.site)
        .order_by("device__name", "name", "pk")
    )
    if power_system.location_id:
        power_ports = power_ports.filter(
            Q(device__location=power_system.location)
            | Q(device__location__isnull=True, device__rack__location=power_system.location)
        )
    return tuple(power_ports)


def _internal_bus_attachment_coverage(power_system, scoped_power_ports) -> InternalBusAttachmentCoverage:
    buses = tuple(
        InternalPowerBus.objects.filter(power_system=power_system)
        .select_related("rack")
        .order_by("rack__name", "name", "pk")
    )
    attachments = tuple(
        InternalPowerBusAttachment.objects.filter(internal_power_bus__power_system=power_system)
        .select_related(
            "internal_power_bus",
            "internal_power_bus__rack",
            "power_port__device",
            "power_port__device__rack",
        )
        .order_by(
            "internal_power_bus__name",
            "attachment_role",
            "position_index",
            "power_port__device__name",
            "power_port__name",
            "pk",
        )
    )
    bus_rack_ids = {bus.rack_id for bus in buses if bus.rack_id}
    candidate_power_ports = tuple(
        power_port for power_port in scoped_power_ports if getattr(power_port.device, "rack_id", None) in bus_rack_ids
    )

    stale_attachments = tuple(
        issue
        for attachment in attachments
        for issue in (_internal_bus_attachment_issue(power_system, attachment),)
        if issue is not None
    )
    stale_attachment_ids = {issue.owner.pk for issue in stale_attachments}
    covered_power_port_ids = {
        attachment.power_port_id
        for attachment in attachments
        if attachment.pk not in stale_attachment_ids and attachment.power_port_id
    }
    covered_power_ports = tuple(
        power_port for power_port in candidate_power_ports if power_port.pk in covered_power_port_ids
    )
    uncovered_power_ports = tuple(
        power_port for power_port in candidate_power_ports if power_port.pk not in covered_power_port_ids
    )

    return InternalBusAttachmentCoverage(
        buses=buses,
        attachments=attachments,
        candidate_power_ports=candidate_power_ports,
        covered_power_ports=covered_power_ports,
        uncovered_power_ports=uncovered_power_ports,
        stale_attachments=stale_attachments,
        source_attachment_count=sum(
            1
            for attachment in attachments
            if attachment.attachment_role == InternalPowerBusAttachmentRoleChoices.ROLE_SOURCE
        ),
        load_attachment_count=sum(
            1
            for attachment in attachments
            if attachment.attachment_role == InternalPowerBusAttachmentRoleChoices.ROLE_LOAD
        ),
    )


def _modeled_power_port_ids(handoffs, attachments) -> set[int]:
    power_port_ids = {handoff.power_port_id for handoff in handoffs if handoff.power_port_id}
    power_port_ids.update(attachment.power_port_id for attachment in attachments if attachment.power_port_id)
    return power_port_ids


def _handoff_power_port_issue(power_system, handoff) -> TargetPowerPortIssue | None:
    power_port = getattr(handoff, "power_port", None)
    scope_issue = _power_port_scope_issue(power_system, power_port)
    if scope_issue is None:
        return None

    finding_type, message = scope_issue
    return TargetPowerPortIssue(
        owner=handoff,
        power_port=power_port,
        finding_type=finding_type,
        message=f"Power handoff {handoff} {message}",
    )


def _internal_bus_attachment_issue(power_system, attachment) -> TargetPowerPortIssue | None:
    power_port = getattr(attachment, "power_port", None)
    scope_issue = _power_port_scope_issue(power_system, power_port)
    if scope_issue is not None:
        finding_type, message = scope_issue
        return TargetPowerPortIssue(
            owner=attachment,
            power_port=power_port,
            finding_type=(
                "internal_bus_attachment_power_port_stale"
                if finding_type == "power_port_target_stale"
                else "internal_bus_attachment_power_port_missing"
            ),
            message=f"Internal bus attachment {attachment} {message}",
        )

    if power_port.device.rack_id != attachment.internal_power_bus.rack_id:
        return TargetPowerPortIssue(
            owner=attachment,
            power_port=power_port,
            finding_type="internal_bus_attachment_power_port_stale",
            message=(
                f"Internal bus attachment {attachment} targets {power_port}, "
                f"but that PowerPort is no longer in rack {attachment.internal_power_bus.rack}."
            ),
        )

    return None


def _power_port_scope_issue(power_system, power_port):
    if power_port is None:
        return (
            "power_port_target_missing",
            "does not target an existing NetBox PowerPort.",
        )

    device = getattr(power_port, "device", None)
    if device is None:
        return (
            "power_port_target_stale",
            f"targets {power_port}, but that PowerPort is not attached to a device.",
        )
    if device.site_id != power_system.site_id:
        return (
            "power_port_target_stale",
            f"targets {power_port}, but its device is no longer in site {power_system.site}.",
        )
    if power_system.location_id and _device_location_id(device) != power_system.location_id:
        return (
            "power_port_target_stale",
            f"targets {power_port}, but its device is no longer in location {power_system.location}.",
        )

    return None


def _device_location_id(device):
    if device.location_id:
        return device.location_id
    if device.rack_id:
        return device.rack.location_id
    return None


def _build_findings(
    *,
    rack_boundary_candidates,
    modeled_candidate_terminal_ids,
    handoffs_without_active_path,
    target_power_port_issues,
    unmodeled_power_ports,
    internal_bus_coverage,
) -> tuple[dict, ...]:
    findings = []

    for candidate in rack_boundary_candidates:
        if candidate.terminal.pk in modeled_candidate_terminal_ids:
            continue
        findings.append(
            _finding(
                "unmodeled_rack_boundary_candidate",
                (
                    f"Active rack-boundary terminal {candidate.terminal} on {candidate.node} "
                    "has no PowerHandoffPoint targeting a NetBox PowerPort."
                ),
                candidate.terminal,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                node_id=candidate.node.pk,
                terminal_id=candidate.terminal.pk,
            )
        )

    for handoff in handoffs_without_active_path:
        findings.append(
            _finding(
                "handoff_missing_active_path",
                f"Power handoff {handoff} does not match an active rack-boundary path.",
                handoff,
                severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
                handoff_id=handoff.pk,
                power_port_id=handoff.power_port_id,
            )
        )

    for issue in target_power_port_issues:
        findings.append(
            _finding(
                issue.finding_type,
                issue.message,
                issue.owner,
                severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
                power_port_id=getattr(issue.power_port, "pk", None),
            )
        )

    for power_port in unmodeled_power_ports:
        findings.append(
            _finding(
                "unmodeled_power_port",
                f"NetBox PowerPort {power_port} is in scope but has no plant handoff or internal bus attachment.",
                power_port,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                power_port_id=power_port.pk,
                device_id=power_port.device_id,
            )
        )

    for power_port in internal_bus_coverage.uncovered_power_ports:
        findings.append(
            _finding(
                "internal_bus_power_port_unattached",
                f"NetBox PowerPort {power_port} is in a rack with an internal power bus but has no bus attachment.",
                power_port,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                power_port_id=power_port.pk,
                device_id=power_port.device_id,
            )
        )

    for issue in internal_bus_coverage.stale_attachments:
        findings.append(
            _finding(
                issue.finding_type,
                issue.message,
                issue.owner,
                severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
                power_port_id=getattr(issue.power_port, "pk", None),
                attachment_id=issue.owner.pk,
            )
        )

    return tuple(findings)


def _finding(finding_type, message, obj, *, severity, **details):
    return {
        "finding_type": finding_type,
        "message": message,
        "object": obj,
        "severity": severity,
        **details,
    }
