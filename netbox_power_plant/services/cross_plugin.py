from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import NoReverseMatch
from django.utils import timezone

from netbox_power_plant.models import PowerHandoffPoint
from netbox_power_plant.services.impact import SEVERITY_CRITICAL, SEVERITY_DEGRADED


@dataclass(frozen=True)
class CrossPluginInvalidationResult:
    plugin_available: bool
    fabric_count: int = 0
    token: str | None = None
    reason: str = ''


@dataclass(frozen=True)
class CrossPluginRiskResult:
    plugin_available: bool
    reason: str
    power_system: dict | None
    scenario_type: str
    target: dict | None
    summary: dict
    racks: tuple[dict, ...]


def invalidate_handoff_topology_caches(handoff: PowerHandoffPoint | None) -> CrossPluginInvalidationResult:
    if handoff is None or not apps.is_installed('netbox_plant_graph'):
        return CrossPluginInvalidationResult(plugin_available=False, reason='netbox_plant_graph_not_installed')

    try:
        from netbox_plant_graph.models import Endpoint, Fabric, FabricNode
    except Exception:
        return CrossPluginInvalidationResult(plugin_available=False, reason='netbox_plant_graph_import_failed')

    fabric_ids = set()
    if handoff.power_system_id:
        power_system = handoff.power_system
        fabric_ids.update(
            Fabric.objects.filter(scope_site_id=power_system.site_id).values_list('pk', flat=True)
        )
        if power_system.location_id:
            fabric_ids.update(
                Fabric.objects.filter(scope_location_id=power_system.location_id).values_list('pk', flat=True)
            )

    if handoff.power_port_id:
        source_type_ids = [
            ContentType.objects.get_for_model(handoff.power_port, for_concrete_model=False).pk,
            ContentType.objects.get_for_model(handoff.power_port.device, for_concrete_model=False).pk,
        ]
        source_ids = [handoff.power_port_id, handoff.power_port.device_id]
        fabric_ids.update(
            FabricNode.objects.filter(
                source_type_id__in=source_type_ids,
                source_id__in=source_ids,
            ).values_list('fabric_id', flat=True)
        )
        fabric_ids.update(
            Endpoint.objects.filter(
                source_type_id__in=source_type_ids,
                source_id__in=source_ids,
            ).values_list('fabric_id', flat=True)
        )

    token = timezone.now().isoformat()
    for fabric in Fabric.objects.filter(pk__in=fabric_ids):
        metadata = dict(fabric.metadata or {})
        if metadata.get('graph_revision'):
            metadata['previous_graph_revision'] = metadata['graph_revision']
        metadata['graph_revision'] = token
        metadata['power_plant_handoff_cache_token'] = token
        fabric.metadata = metadata
        fabric.save(update_fields=('metadata',))

    return CrossPluginInvalidationResult(
        plugin_available=True,
        fabric_count=len(fabric_ids),
        token=token,
        reason='cache_token_updated' if fabric_ids else 'no_related_fabric',
    )


def correlate_power_and_fabric_risk(power_impact_report: dict) -> CrossPluginRiskResult:
    """
    Combine power blast-radius rack state with modeled fabric objects in netbox_plant_graph.

    The graph plugin is optional. When absent, the result preserves the power
    impact context and marks fabric correlation unavailable instead of failing.
    """
    if not apps.is_installed('netbox_plant_graph'):
        return _risk_result(
            power_impact_report,
            plugin_available=False,
            reason='netbox_plant_graph_not_installed',
            racks=(),
        )

    try:
        Fabric = apps.get_model('netbox_plant_graph', 'Fabric')
        FabricNode = apps.get_model('netbox_plant_graph', 'FabricNode')
        Endpoint = apps.get_model('netbox_plant_graph', 'Endpoint')
    except LookupError:
        return _risk_result(
            power_impact_report,
            plugin_available=False,
            reason='netbox_plant_graph_models_unavailable',
            racks=(),
        )

    rack_rows = []
    for rack in power_impact_report.get('racks', ()):
        if rack.get('severity') not in {SEVERITY_CRITICAL, SEVERITY_DEGRADED}:
            continue
        correlation = _fabric_correlation_for_power_rack(rack, Fabric, FabricNode, Endpoint)
        if not correlation['fabric_objects']:
            continue
        rack_rows.append({
            'rack': rack.get('rack'),
            'power_severity': rack.get('severity'),
            'power_affected_handoff_count': rack.get('affected_handoff_count', 0),
            'power_lost_domains': _unique_domain_refs(
                domain
                for handoff in rack.get('handoffs', ())
                for domain in handoff.get('lost_domains', ())
            ),
            'fabric_risk': correlation,
            'joint_risk': _joint_risk_level(rack.get('severity'), correlation),
            'tenant': rack.get('tenant'),
            'reservations': rack.get('reservations', ()),
        })

    return _risk_result(
        power_impact_report,
        plugin_available=True,
        reason='correlated' if rack_rows else 'no_power_impacted_racks_with_fabric_objects',
        racks=tuple(sorted(
            rack_rows,
            key=lambda row: (
                -_joint_risk_rank(row['joint_risk']),
                (row['rack'] or {}).get('name') or '',
                (row['rack'] or {}).get('id') or 0,
            ),
        )),
    )


def _fabric_correlation_for_power_rack(rack, Fabric, FabricNode, Endpoint):
    del Fabric
    device_ids = {
        handoff['device']['id']
        for handoff in rack.get('handoffs', ())
        if handoff.get('device') and handoff.get('device', {}).get('id') is not None
    }
    power_port_ids = {
        handoff['power_port']['id']
        for handoff in rack.get('handoffs', ())
        if handoff.get('power_port') and handoff.get('power_port', {}).get('id') is not None
    }
    if not device_ids and not power_port_ids:
        return _empty_fabric_correlation()

    from dcim.models import Device, PowerPort

    content_type_filters = []
    if device_ids:
        content_type_filters.append((
            ContentType.objects.get_for_model(Device, for_concrete_model=False).pk,
            device_ids,
        ))
    if power_port_ids:
        content_type_filters.append((
            ContentType.objects.get_for_model(PowerPort, for_concrete_model=False).pk,
            power_port_ids,
        ))

    fabric_nodes = []
    endpoints = []
    for content_type_id, source_ids in content_type_filters:
        fabric_nodes.extend(
            FabricNode.objects
            .filter(source_type_id=content_type_id, source_id__in=source_ids)
            .select_related('fabric')
            .order_by('fabric__name', 'address', 'pk')
        )
        endpoints.extend(
            Endpoint.objects
            .filter(source_type_id=content_type_id, source_id__in=source_ids)
            .select_related('fabric', 'node')
            .order_by('fabric__name', 'address', 'pk')
        )

    fabrics = _unique_objects([node.fabric for node in fabric_nodes] + [endpoint.fabric for endpoint in endpoints])
    active_finding_count = _active_fabric_finding_count(fabrics, tuple(fabric_nodes), tuple(endpoints))
    stale_fabrics = tuple(
        fabric for fabric in fabrics if not (getattr(fabric, 'metadata', None) or {}).get('graph_revision')
    )
    return {
        'risk_present': bool(fabric_nodes or endpoints),
        'reason': _fabric_risk_reason(active_finding_count, stale_fabrics, fabric_nodes, endpoints),
        'fabrics': tuple(_object_ref(fabric) for fabric in fabrics),
        'fabric_objects': tuple(
            [_fabric_object_payload('fabric_node', node) for node in fabric_nodes]
            + [_fabric_object_payload('endpoint', endpoint) for endpoint in endpoints]
        ),
        'active_finding_count': active_finding_count,
        'stale_fabric_count': len(stale_fabrics),
    }


def _active_fabric_finding_count(fabrics, fabric_nodes, endpoints):
    try:
        Summary = apps.get_model('netbox_plant_graph', 'UnresolvedStateSummary')
    except LookupError:
        return 0

    fabric_ids = [fabric.pk for fabric in fabrics]
    if not fabric_ids:
        return 0
    queryset = Summary.objects.filter(fabric_id__in=fabric_ids)
    if _model_has_field(Summary, 'active'):
        queryset = queryset.filter(active=True)

    object_filters = []
    for obj in (*fabric_nodes, *endpoints):
        content_type_id = ContentType.objects.get_for_model(obj, for_concrete_model=False).pk
        object_filters.append((content_type_id, obj.pk))

    has_owner_fields = _model_has_field(Summary, 'owner_object_type') and _model_has_field(Summary, 'owner_object_id')
    has_rep_fields = (
        _model_has_field(Summary, 'representative_object_type')
        and _model_has_field(Summary, 'representative_object_id')
    )
    if not object_filters or not (has_owner_fields or has_rep_fields):
        return queryset.count()

    filtered_count = 0
    for content_type_id, object_id in object_filters:
        if has_owner_fields:
            filtered_count += queryset.filter(owner_object_type_id=content_type_id, owner_object_id=object_id).count()
        if has_rep_fields:
            filtered_count += queryset.filter(
                representative_object_type_id=content_type_id,
                representative_object_id=object_id,
            ).count()
    return filtered_count


def _model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.get_fields())


def _fabric_risk_reason(active_finding_count, stale_fabrics, fabric_nodes, endpoints):
    if active_finding_count:
        return 'active_fabric_findings_on_rack_objects'
    if stale_fabrics:
        return 'fabric_graph_revision_missing'
    if endpoints:
        return 'rack_power_handoffs_have_modeled_fabric_endpoints'
    if fabric_nodes:
        return 'rack_devices_have_modeled_fabric_nodes'
    return 'no_fabric_objects'


def _empty_fabric_correlation():
    return {
        'risk_present': False,
        'reason': 'no_power_handoff_devices',
        'fabrics': (),
        'fabric_objects': (),
        'active_finding_count': 0,
        'stale_fabric_count': 0,
    }


def _joint_risk_level(power_severity, correlation):
    if power_severity == SEVERITY_CRITICAL and correlation['active_finding_count']:
        return 'critical'
    if power_severity == SEVERITY_CRITICAL:
        return 'high'
    if correlation['active_finding_count']:
        return 'high'
    return 'elevated'


def _joint_risk_rank(level):
    return {'critical': 3, 'high': 2, 'elevated': 1}.get(level, 0)


def _risk_result(power_impact_report, *, plugin_available, reason, racks):
    return CrossPluginRiskResult(
        plugin_available=plugin_available,
        reason=reason,
        power_system=power_impact_report.get('power_system'),
        scenario_type=power_impact_report.get('scenario_type', ''),
        target=power_impact_report.get('target'),
        summary={
            'power_critical_rack_count': power_impact_report.get('summary', {}).get('critical_rack_count', 0),
            'power_degraded_rack_count': power_impact_report.get('summary', {}).get('degraded_rack_count', 0),
            'joint_rack_count': len(racks),
            'plugin_available': plugin_available,
            'reason': reason,
        },
        racks=tuple(racks),
    )


def _fabric_object_payload(kind, obj):
    return {
        'kind': kind,
        'object': _object_ref(obj),
        'fabric': _object_ref(obj.fabric),
        'source': _object_ref(getattr(obj, 'source', None)),
        'address': getattr(obj, 'address', ''),
    }


def _unique_domain_refs(domains):
    seen = set()
    unique = []
    for domain in domains:
        domain_id = domain.get('id')
        if domain_id in seen:
            continue
        seen.add(domain_id)
        unique.append(domain)
    return tuple(unique)


def _unique_objects(objects):
    seen = set()
    unique = []
    for obj in objects:
        if obj.pk in seen:
            continue
        seen.add(obj.pk)
        unique.append(obj)
    return tuple(unique)


def _object_ref(obj):
    if obj is None:
        return None
    url = None
    if hasattr(obj, 'get_absolute_url'):
        try:
            url = obj.get_absolute_url()
        except NoReverseMatch:
            url = None
    return {
        'id': obj.pk,
        'display': str(obj),
        'name': getattr(obj, 'name', str(obj)),
        'url': url,
    }


@receiver(post_save, sender=PowerHandoffPoint, dispatch_uid='netbox_power_plant_handoff_cross_plugin_save')
def invalidate_handoff_topology_caches_on_save(sender, instance, **kwargs):
    del sender, kwargs
    invalidate_handoff_topology_caches(instance)


@receiver(post_delete, sender=PowerHandoffPoint, dispatch_uid='netbox_power_plant_handoff_cross_plugin_delete')
def invalidate_handoff_topology_caches_on_delete(sender, instance, **kwargs):
    del sender, kwargs
    invalidate_handoff_topology_caches(instance)
