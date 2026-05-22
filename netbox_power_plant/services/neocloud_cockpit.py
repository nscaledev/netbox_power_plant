from __future__ import annotations

from dataclasses import asdict

from netbox_power_plant.models import ElectricalNode, ElectricalSegment, PowerDomain
from netbox_power_plant.services.capacity import build_node_capacity_path_rollup
from netbox_power_plant.services.cross_plugin import correlate_power_and_fabric_risk
from netbox_power_plant.services.impact import domain_lost, node_offline, segment_cut


SCENARIO_NODE_OFFLINE = 'node_offline'
SCENARIO_SEGMENT_CUT = 'segment_cut'
SCENARIO_DOMAIN_LOST = 'domain_lost'

SUPPORTED_SCENARIOS = (SCENARIO_NODE_OFFLINE, SCENARIO_SEGMENT_CUT, SCENARIO_DOMAIN_LOST)


def build_neocloud_cockpit_workflow(power_system, *, scenario_type: str, target_id: int) -> dict:
    impact_report = _impact_report(power_system, scenario_type=scenario_type, target_id=target_id)
    correlation = correlate_power_and_fabric_risk(impact_report)
    capacity_rollups = tuple(
        build_node_capacity_path_rollup(node).to_dict()
        for node in _target_rack_nodes(power_system, impact_report)
    )

    return {
        'power_system': impact_report.get('power_system'),
        'scenario_type': scenario_type,
        'target': impact_report.get('target'),
        'impact': impact_report,
        'capacity_rollups': capacity_rollups,
        'cross_plugin_risk': asdict(correlation),
        'operator_summary': {
            'critical_rack_count': impact_report.get('summary', {}).get('critical_rack_count', 0),
            'degraded_rack_count': impact_report.get('summary', {}).get('degraded_rack_count', 0),
            'joint_power_fabric_rack_count': correlation.summary['joint_rack_count'],
            'fabric_correlation_available': correlation.plugin_available,
        },
    }


def _impact_report(power_system, *, scenario_type, target_id):
    if scenario_type == SCENARIO_NODE_OFFLINE:
        return node_offline(power_system, ElectricalNode.objects.get(pk=target_id))
    if scenario_type == SCENARIO_SEGMENT_CUT:
        return segment_cut(power_system, ElectricalSegment.objects.get(pk=target_id))
    if scenario_type == SCENARIO_DOMAIN_LOST:
        return domain_lost(power_system, PowerDomain.objects.get(pk=target_id))
    raise ValueError(f'Unsupported neocloud cockpit scenario: {scenario_type}')


def _target_rack_nodes(power_system, impact_report):
    node_ids = {
        handoff['electrical_node']['id']
        for rack in impact_report.get('racks', ())
        for handoff in rack.get('handoffs', ())
        if handoff.get('severity') != 'unaffected' and handoff.get('electrical_node')
    }
    if not node_ids:
        return ()
    return tuple(
        ElectricalNode.objects
        .filter(power_system=power_system, pk__in=node_ids)
        .select_related('power_system', 'site', 'location', 'parent_node')
        .order_by('name', 'pk')
    )
