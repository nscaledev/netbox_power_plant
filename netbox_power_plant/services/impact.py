from __future__ import annotations

from collections import Counter, defaultdict

from django.db.models import Q
from django.utils import timezone

from netbox_power_plant.choices import CapacityReservationStatusChoices
from netbox_power_plant.models import CapacityReservation, ElectricalNode, ElectricalSegment, PowerDomain
from netbox_power_plant.services.scenarios import PowerOutageScenario, simulate_power_scenario


SEVERITY_CRITICAL = 'critical'
SEVERITY_DEGRADED = 'degraded'
SEVERITY_UNAFFECTED = 'unaffected'

_SEVERITY_RANK = {
    SEVERITY_UNAFFECTED: 0,
    SEVERITY_DEGRADED: 1,
    SEVERITY_CRITICAL: 2,
}


def node_offline(power_system, node) -> dict:
    node = _resolve_node(power_system, node)
    return _build_impact_report(
        power_system,
        PowerOutageScenario(electrical_nodes=(node,)),
        scenario_type='node_offline',
        target=_object_ref(node),
    )


def segment_cut(power_system, segment) -> dict:
    segment = _resolve_segment(power_system, segment)
    return _build_impact_report(
        power_system,
        PowerOutageScenario(electrical_segments=(segment,)),
        scenario_type='segment_cut',
        target=_object_ref(segment),
    )


def domain_lost(power_system, domain) -> dict:
    domain = _resolve_domain(power_system, domain)
    return _build_impact_report(
        power_system,
        PowerOutageScenario(power_domains=(domain,)),
        scenario_type='domain_lost',
        target=_object_ref(domain),
    )


def _build_impact_report(power_system, scenario, *, scenario_type: str, target: dict) -> dict:
    baseline = simulate_power_scenario(power_system, PowerOutageScenario(), include_capacity=False)
    result = simulate_power_scenario(power_system, scenario, include_capacity=False)

    critical_handoff_ids = {impact.handoff.pk for impact in result.handoff_impacts}
    degraded_by_handoff_id = defaultdict(list)
    for violation in result.redundancy_violations:
        if violation.handoff is not None and violation.handoff.pk not in critical_handoff_ids:
            degraded_by_handoff_id[violation.handoff.pk].append(violation)

    racks = {}
    handoff_details = []
    handoffs = tuple(_handoffs(power_system))
    reservations_by_rack_id = _active_reservations_by_rack_id(
        handoff.power_port.device.rack_id
        for handoff in handoffs
        if handoff.power_port_id and handoff.power_port.device.rack_id
    )
    for handoff in handoffs:
        rack = handoff.power_port.device.rack if handoff.power_port_id and handoff.power_port.device.rack_id else None
        rack_key = rack.pk if rack is not None else None
        severity = _handoff_severity(handoff, critical_handoff_ids, degraded_by_handoff_id)
        impact_reasons = _handoff_reasons(handoff, result, degraded_by_handoff_id)
        baseline_domains = baseline.remaining_domains_by_handoff.get(handoff.pk, ())
        remaining_domains = result.remaining_domains_by_handoff.get(handoff.pk, ())
        lost_domains = _lost_domains(baseline_domains, remaining_domains)
        detail = {
            'severity': severity,
            'handoff': _object_ref(handoff),
            'device': _object_ref(handoff.power_port.device) if handoff.power_port_id else None,
            'power_port': _object_ref(handoff.power_port) if handoff.power_port_id else None,
            'tenant': _object_ref(getattr(handoff.power_port.device, 'tenant', None))
            if handoff.power_port_id
            else None,
            'rack': _object_ref(rack),
            'electrical_node': _object_ref(handoff.electrical_node)
            if handoff.electrical_node_id
            else None,
            'electrical_terminal': _object_ref(handoff.electrical_terminal)
            if handoff.electrical_terminal_id
            else None,
            'baseline_domains': tuple(_object_ref(domain) for domain in baseline_domains),
            'lost_domains': tuple(_object_ref(domain) for domain in lost_domains),
            'remaining_domains': tuple(_object_ref(domain) for domain in remaining_domains),
            'redundancy': _redundancy_evidence(handoff, degraded_by_handoff_id.get(handoff.pk, ())),
            'impact_reasons': tuple(impact_reasons),
        }
        handoff_details.append(detail)

        if rack_key not in racks:
            racks[rack_key] = {
                'rack': _object_ref(rack) if rack is not None else None,
                'severity': SEVERITY_UNAFFECTED,
                'tenant': _object_ref(getattr(rack, 'tenant', None)) if rack is not None else None,
                'reservations': reservations_by_rack_id.get(rack_key, ()),
                'handoffs': [],
            }
        racks[rack_key]['severity'] = _max_severity(racks[rack_key]['severity'], severity)
        racks[rack_key]['handoffs'].append(detail)

    rack_rows = tuple(
        {
            **rack,
            'handoff_count': len(rack['handoffs']),
            'affected_handoff_count': len([
                handoff for handoff in rack['handoffs'] if handoff['severity'] != SEVERITY_UNAFFECTED
            ]),
        }
        for rack in sorted(
            racks.values(),
            key=lambda item: (
                -_SEVERITY_RANK[item['severity']],
                (item['rack'] or {}).get('name') or '',
                (item['rack'] or {}).get('id') or 0,
            ),
        )
    )
    severity_counts = Counter(rack['severity'] for rack in rack_rows)

    return {
        'power_system': _object_ref(power_system),
        'scenario_type': scenario_type,
        'target': target,
        'summary': {
            'rack_count': len(rack_rows),
            'critical_rack_count': severity_counts[SEVERITY_CRITICAL],
            'degraded_rack_count': severity_counts[SEVERITY_DEGRADED],
            'unaffected_rack_count': severity_counts[SEVERITY_UNAFFECTED],
            'critical_handoff_count': len([
                handoff for handoff in handoff_details if handoff['severity'] == SEVERITY_CRITICAL
            ]),
            'degraded_handoff_count': len([
                handoff for handoff in handoff_details if handoff['severity'] == SEVERITY_DEGRADED
            ]),
            'lost_domain_count': len({
                domain['id']
                for handoff in handoff_details
                for domain in handoff['lost_domains']
            }),
        },
        'racks': rack_rows,
    }


def _handoff_severity(handoff, critical_handoff_ids, degraded_by_handoff_id) -> str:
    if handoff.pk in critical_handoff_ids:
        return SEVERITY_CRITICAL
    if handoff.pk in degraded_by_handoff_id:
        return SEVERITY_DEGRADED
    return SEVERITY_UNAFFECTED


def _handoff_reasons(handoff, result, degraded_by_handoff_id):
    reasons = []
    for impact in result.handoff_impacts:
        if impact.handoff.pk == handoff.pk:
            reasons.extend(impact.impact_reasons)
    for violation in degraded_by_handoff_id.get(handoff.pk, ()):
        reasons.extend(violation.finding_types)
    return tuple(dict.fromkeys(reasons))


def _lost_domains(baseline_domains, remaining_domains):
    remaining_ids = {domain.pk for domain in remaining_domains}
    return tuple(domain for domain in baseline_domains if domain.pk not in remaining_ids)


def _redundancy_evidence(handoff, violations):
    group = handoff.expected_redundancy_group
    if group is None:
        return {
            'compliant': None,
            'redundancy_group': None,
            'reason': 'no_redundancy_group_assigned',
            'finding_types': (),
            'matched_domains': (),
        }

    if violations:
        finding_types = tuple(dict.fromkeys(
            finding_type
            for violation in violations
            for finding_type in violation.finding_types
        ))
        matched_domains = tuple(dict.fromkeys(
            domain
            for violation in violations
            for domain in violation.matched_domains
        ))
        return {
            'compliant': False,
            'redundancy_group': _object_ref(group),
            'reason': '; '.join(violation.message for violation in violations),
            'finding_types': finding_types,
            'matched_domains': tuple(_object_ref(domain) for domain in matched_domains),
        }

    return {
        'compliant': True,
        'redundancy_group': _object_ref(group),
        'reason': 'expected_redundancy_group_remains_compliant',
        'finding_types': (),
        'matched_domains': (),
    }


def _max_severity(left: str, right: str) -> str:
    return left if _SEVERITY_RANK[left] >= _SEVERITY_RANK[right] else right


def _handoffs(power_system):
    return power_system.power_handoff_points.select_related(
        'electrical_node',
        'electrical_terminal__node',
        'power_port__device__rack',
        'power_port__device__tenant',
        'expected_redundancy_group',
    ).order_by('power_port__device__rack__name', 'power_port__device__name', 'name', 'pk')


def _active_reservations_by_rack_id(rack_ids, *, as_of=None):
    rack_ids = tuple({rack_id for rack_id in rack_ids if rack_id is not None})
    if not rack_ids:
        return {}

    as_of = as_of or timezone.localdate()
    reservations = (
        CapacityReservation.objects
        .filter(
            rack_id__in=rack_ids,
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=as_of))
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=as_of))
        .select_related('tenant', 'rack', 'node')
        .order_by('rack__name', 'tenant__name', 'name', 'pk')
    )
    reservations_by_rack_id = {}
    for reservation in reservations:
        reservations_by_rack_id.setdefault(reservation.rack_id, []).append({
            'reservation': _object_ref(reservation),
            'node': _object_ref(reservation.node),
            'tenant': _object_ref(reservation.tenant),
            'reserved_kw': reservation.reserved_kw,
            'status': reservation.status,
            'valid_from': reservation.valid_from,
            'valid_until': reservation.valid_until,
        })
    return {rack_id: tuple(rows) for rack_id, rows in reservations_by_rack_id.items()}


def _resolve_node(power_system, node):
    if isinstance(node, ElectricalNode):
        resolved = node
    else:
        resolved = ElectricalNode.objects.get(pk=node)
    if resolved.power_system_id != power_system.pk:
        raise ValueError('Electrical node does not belong to the selected power system.')
    return resolved


def _resolve_segment(power_system, segment):
    if isinstance(segment, ElectricalSegment):
        resolved = segment
    else:
        resolved = ElectricalSegment.objects.get(pk=segment)
    if resolved.power_system_id != power_system.pk:
        raise ValueError('Electrical segment does not belong to the selected power system.')
    return resolved


def _resolve_domain(power_system, domain):
    if isinstance(domain, PowerDomain):
        resolved = domain
    else:
        resolved = PowerDomain.objects.get(pk=domain)
    if resolved.power_system_id != power_system.pk:
        raise ValueError('Power domain does not belong to the selected power system.')
    return resolved


def _object_ref(obj):
    if obj is None:
        return None
    return {
        'id': obj.pk,
        'display': str(obj),
        'name': getattr(obj, 'name', str(obj)),
        'url': obj.get_absolute_url() if hasattr(obj, 'get_absolute_url') else None,
    }
