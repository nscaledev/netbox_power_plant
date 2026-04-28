from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from netbox_power_plant.choices import (
    PhaseModeChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TopologyStateChoices,
)
from netbox_power_plant.services.graph import PowerGraphBuilder
from netbox_power_plant.services.rack_delivery import build_rack_delivery_summary


def validate_topology_terminal(terminal):
    errors = {}

    if terminal.node.phase_mode == PhaseModeChoices.MODE_DC and terminal.supply_type != SupplyTypeChoices.SUPPLY_DC:
        errors['supply_type'] = _('DC nodes may only expose DC terminals.')

    if terminal.node.phase_mode in (PhaseModeChoices.MODE_SINGLE_PHASE, PhaseModeChoices.MODE_THREE_PHASE) and terminal.supply_type == SupplyTypeChoices.SUPPLY_DC:
        errors['supply_type'] = _('AC nodes may not expose DC terminals.')

    if errors:
        raise ValidationError(errors)


def validate_topology_segment(segment):
    errors = {}
    from_node = segment.from_terminal.node
    to_node = segment.to_terminal.node

    if from_node.power_system_id != segment.power_system_id:
        errors['from_terminal'] = _('The source terminal must belong to the selected power system.')

    if to_node.power_system_id != segment.power_system_id:
        errors['to_terminal'] = _('The destination terminal must belong to the selected power system.')

    if segment.power_domain_id and segment.power_domain.power_system_id != segment.power_system_id:
        errors['power_domain'] = _('The selected power domain must belong to the selected power system.')

    if segment.from_terminal_id == segment.to_terminal_id and segment.segment_kind != SegmentKindChoices.KIND_INTERNAL_TIE:
        errors['to_terminal'] = _('Only internal tie segments may loop back to the same terminal.')

    if segment.from_terminal.direction == TerminalDirectionChoices.DIRECTION_SINK:
        errors['from_terminal'] = _('Sink terminals cannot originate a segment.')

    if segment.to_terminal.direction == TerminalDirectionChoices.DIRECTION_SOURCE:
        errors['to_terminal'] = _('Source terminals cannot terminate a segment.')

    if (
        segment.from_terminal.supply_type != SupplyTypeChoices.SUPPLY_MIXED
        and segment.to_terminal.supply_type != SupplyTypeChoices.SUPPLY_MIXED
        and segment.from_terminal.supply_type != segment.to_terminal.supply_type
    ):
        errors['to_terminal'] = _('Segment endpoints must share the same supply type unless one endpoint is mixed.')

    if errors:
        raise ValidationError(errors)


def run_topology_checks(power_system):
    snapshot = PowerGraphBuilder.build_for_power_system(
        power_system,
        node_states=(TopologyStateChoices.STATE_ACTIVE,),
        path_states=(TopologyStateChoices.STATE_ACTIVE,),
    )
    findings = []

    for node_id in sorted(snapshot.nodes_by_id):
        node = snapshot.nodes_by_id[node_id]
        terminal_ids = snapshot.node_terminal_ids.get(node_id, set())
        if not terminal_ids:
            findings.append({
                'finding_type': 'missing_terminal',
                'message': _('Active nodes must expose at least one terminal.'),
                'object': node,
            })

    orphan_terminal_ids = snapshot.orphan_terminal_ids()
    for terminal_id in sorted(orphan_terminal_ids):
        terminal = snapshot.terminals_by_id[terminal_id]
        findings.append({
            'finding_type': 'orphan_terminal',
            'message': _('Terminals on active nodes must participate in at least one active segment.'),
            'object': terminal,
        })

    isolated_node_ids = snapshot.isolated_node_ids()
    for node_id in sorted(isolated_node_ids):
        node = snapshot.nodes_by_id[node_id]
        if snapshot.node_terminal_ids.get(node_id):
            findings.append({
                'finding_type': 'isolated_node',
                'message': _('Active nodes with terminals must connect to at least one neighbor node.'),
                'object': node,
            })

    cycle_node_ids = snapshot.cycle_node_ids()
    if cycle_node_ids:
        findings.append({
            'finding_type': 'cycle_detected',
            'message': _('Topology graph contains at least one directed cycle.'),
            'node_ids': sorted(cycle_node_ids),
        })

    rack_delivery_summary = build_rack_delivery_summary(power_system)
    for row in rack_delivery_summary.rows:
        for assessment in row.assessments:
            if assessment.is_compliant:
                continue
            if 'distinct_path_count_not_met' in assessment.finding_types:
                findings.append({
                    'finding_type': 'distinct_path_count_not_met',
                    'message': _('Rack delivery does not satisfy the minimum distinct path count for the redundancy group.'),
                    'object': row.terminal,
                    'node': row.node,
                    'redundancy_group': assessment.redundancy_group,
                    'matched_domains': assessment.matched_domains,
                })
            if 'domain_isolation_not_met' in assessment.finding_types:
                findings.append({
                    'finding_type': 'domain_isolation_not_met',
                    'message': _('Rack delivery paths collapse before maintaining the required domain isolation.'),
                    'object': row.terminal,
                    'node': row.node,
                    'redundancy_group': assessment.redundancy_group,
                    'matched_domains': assessment.matched_domains,
                })

    return {
        'power_system_id': power_system.pk,
        'finding_count': len(findings),
        'findings': findings,
    }