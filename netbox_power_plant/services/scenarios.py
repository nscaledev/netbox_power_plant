from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from netbox_power_plant.choices import PowerFindingSeverityChoices, TopologyStateChoices
from netbox_power_plant.services.capacity import build_power_system_capacity_summary
from netbox_power_plant.services.graph import PowerGraphBuilder, PowerGraphSnapshot
from netbox_power_plant.services.rack_delivery import (
    _assess_redundancy_group,
    _collect_upstream_domain_ids,
    _iter_power_handoff_terminals,
)


@dataclass(frozen=True)
class PowerOutageScenario:
    electrical_nodes: tuple = ()
    electrical_terminals: tuple = ()
    electrical_segments: tuple = ()
    power_domains: tuple = ()
    power_handoff_points: tuple = ()
    internal_power_buses: tuple = ()
    electrical_node_ids: tuple[int, ...] = ()
    electrical_terminal_ids: tuple[int, ...] = ()
    electrical_segment_ids: tuple[int, ...] = ()
    power_domain_ids: tuple[int, ...] = ()
    power_handoff_point_ids: tuple[int, ...] = ()
    internal_power_bus_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ScenarioHandoffImpact:
    handoff: object
    node: object | None
    terminal: object | None
    device: object | None
    rack: object | None
    remaining_upstream_domains: tuple = ()
    impact_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioRedundancyViolation:
    handoff: object | None
    node: object | None
    terminal: object | None
    redundancy_group: object
    matched_domains: tuple
    finding_types: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class ScenarioResult:
    power_system: object
    scenario: PowerOutageScenario
    handoff_impacts: tuple[ScenarioHandoffImpact, ...] = ()
    impacted_handoffs: tuple = ()
    impacted_devices: tuple = ()
    impacted_racks: tuple = ()
    remaining_domains_by_handoff: dict = field(default_factory=dict)
    redundancy_violations: tuple[ScenarioRedundancyViolation, ...] = ()
    capacity_summary: object | None = None
    findings: tuple[dict, ...] = ()

    @property
    def impacted_handoff_count(self) -> int:
        return len(self.impacted_handoffs)

    @property
    def redundancy_violation_count(self) -> int:
        return len(self.redundancy_violations)


def simulate_power_scenario(power_system, scenario: PowerOutageScenario, *, include_capacity=True) -> ScenarioResult:
    disabled = _normalized_disabled_ids(scenario)
    disabled.update(_cascade_disabled_ids(power_system, disabled))

    snapshot = _scenario_snapshot(power_system, disabled)
    domains_by_id = {
        domain.pk: domain
        for domain in power_system.power_domains.order_by('priority', 'code', 'name')
        if domain.pk not in disabled['power_domain_ids']
    }
    handoff_rows = _handoff_rows(power_system, snapshot, domains_by_id, disabled)

    impacts = []
    violations = []
    findings = []
    remaining_domains_by_handoff = {}

    for handoff in _handoffs(power_system):
        node, terminal = _handoff_target(handoff)
        row = _match_handoff_row(handoff, handoff_rows)
        remaining_domains = row['upstream_domains'] if row else ()
        reasons = _handoff_impact_reasons(handoff, node, terminal, row, disabled)
        remaining_domains_by_handoff[handoff.pk] = remaining_domains

        if reasons:
            impacts.append(ScenarioHandoffImpact(
                handoff=handoff,
                node=node,
                terminal=terminal,
                device=handoff.power_port.device if handoff.power_port_id else None,
                rack=(
                    handoff.power_port.device.rack
                    if handoff.power_port_id and handoff.power_port.device.rack_id
                    else None
                ),
                remaining_upstream_domains=remaining_domains,
                impact_reasons=tuple(reasons),
            ))
            findings.append(_finding(
                'scenario_handoff_unreachable',
                f'Power handoff {handoff} is impacted by the scenario: {", ".join(reasons)}.',
                handoff,
                severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
                handoff_id=handoff.pk,
                reasons=tuple(reasons),
                remaining_domain_ids=tuple(domain.pk for domain in remaining_domains),
            ))

        for violation in _redundancy_violations_for_handoff(handoff, node, terminal, row, remaining_domains):
            violations.append(violation)
            for finding_type in violation.finding_types:
                findings.append(_finding(
                    f'scenario_{finding_type}',
                    violation.message,
                    handoff,
                    severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                    handoff_id=handoff.pk,
                    terminal_id=terminal.pk if terminal else None,
                    node_id=node.pk if node else None,
                    redundancy_group=violation.redundancy_group,
                    matched_domains=violation.matched_domains,
                    remaining_domain_ids=tuple(domain.pk for domain in remaining_domains),
                ))

    impacted_handoffs = tuple(impact.handoff for impact in impacts)
    impacted_devices = _unique_objects(impact.device for impact in impacts if impact.device is not None)
    impacted_racks = _unique_objects(impact.rack for impact in impacts if impact.rack is not None)

    return ScenarioResult(
        power_system=power_system,
        scenario=scenario,
        handoff_impacts=tuple(impacts),
        impacted_handoffs=impacted_handoffs,
        impacted_devices=impacted_devices,
        impacted_racks=impacted_racks,
        remaining_domains_by_handoff=remaining_domains_by_handoff,
        redundancy_violations=tuple(violations),
        capacity_summary=build_power_system_capacity_summary(power_system) if include_capacity else None,
        findings=tuple(findings),
    )


def build_scenario_findings(power_system, scenario: PowerOutageScenario) -> tuple[dict, ...]:
    return simulate_power_scenario(power_system, scenario, include_capacity=False).findings


def _normalized_disabled_ids(scenario):
    return {
        'electrical_node_ids': _ids(scenario.electrical_nodes, scenario.electrical_node_ids),
        'electrical_terminal_ids': _ids(scenario.electrical_terminals, scenario.electrical_terminal_ids),
        'electrical_segment_ids': _ids(scenario.electrical_segments, scenario.electrical_segment_ids),
        'power_domain_ids': _ids(scenario.power_domains, scenario.power_domain_ids),
        'power_handoff_point_ids': _ids(scenario.power_handoff_points, scenario.power_handoff_point_ids),
        'internal_power_bus_ids': _ids(scenario.internal_power_buses, scenario.internal_power_bus_ids),
        'power_port_ids': set(),
    }


def _cascade_disabled_ids(power_system, disabled):
    from netbox_power_plant.models import ElectricalSegment, ElectricalTerminal, InternalPowerBusAttachment

    terminal_ids = set(disabled['electrical_terminal_ids'])
    if disabled['electrical_node_ids']:
        terminal_ids.update(
            ElectricalTerminal.objects.filter(node_id__in=disabled['electrical_node_ids']).values_list('pk', flat=True)
        )

    segment_ids = set(disabled['electrical_segment_ids'])
    if terminal_ids:
        segment_ids.update(
            ElectricalSegment.objects.filter(power_system=power_system).filter(
                from_terminal_id__in=terminal_ids,
            ).values_list('pk', flat=True)
        )
        segment_ids.update(
            ElectricalSegment.objects.filter(power_system=power_system).filter(
                to_terminal_id__in=terminal_ids,
            ).values_list('pk', flat=True)
        )
    if disabled['power_domain_ids']:
        segment_ids.update(
            ElectricalSegment.objects.filter(
                power_system=power_system,
                power_domain_id__in=disabled['power_domain_ids'],
            ).values_list('pk', flat=True)
        )

    power_port_ids = set()
    if disabled['internal_power_bus_ids']:
        power_port_ids.update(
            InternalPowerBusAttachment.objects.filter(
                internal_power_bus_id__in=disabled['internal_power_bus_ids'],
            ).values_list('power_port_id', flat=True)
        )

    return {
        'electrical_terminal_ids': terminal_ids,
        'electrical_segment_ids': segment_ids,
        'power_port_ids': power_port_ids,
    }


def _scenario_snapshot(power_system, disabled):
    base = PowerGraphBuilder.build_for_power_system(
        power_system,
        node_states=(TopologyStateChoices.STATE_ACTIVE,),
        path_states=(TopologyStateChoices.STATE_ACTIVE,),
    )
    nodes_by_id = {
        node_id: node
        for node_id, node in base.nodes_by_id.items()
        if node_id not in disabled['electrical_node_ids']
    }
    terminals_by_id = {
        terminal_id: terminal
        for terminal_id, terminal in base.terminals_by_id.items()
        if terminal_id not in disabled['electrical_terminal_ids'] and terminal.node_id in nodes_by_id
    }
    segments_by_id = {
        segment_id: segment
        for segment_id, segment in base.segments_by_id.items()
        if (
            segment_id not in disabled['electrical_segment_ids']
            and segment.power_domain_id not in disabled['power_domain_ids']
            and segment.from_terminal_id in terminals_by_id
            and segment.to_terminal_id in terminals_by_id
        )
    }

    inbound_neighbors = defaultdict(set)
    outbound_neighbors = defaultdict(set)
    inbound_segments_by_terminal_id = defaultdict(set)
    outbound_segments_by_terminal_id = defaultdict(set)
    node_terminal_ids = defaultdict(set)

    for terminal in terminals_by_id.values():
        node_terminal_ids[terminal.node_id].add(terminal.pk)

    for segment in segments_by_id.values():
        source_node_id = segment.from_terminal.node_id
        destination_node_id = segment.to_terminal.node_id
        outbound_neighbors[source_node_id].add(destination_node_id)
        inbound_neighbors[destination_node_id].add(source_node_id)
        outbound_segments_by_terminal_id[segment.from_terminal_id].add(segment.pk)
        inbound_segments_by_terminal_id[segment.to_terminal_id].add(segment.pk)

    return PowerGraphSnapshot(
        power_system_id=power_system.pk,
        nodes_by_id=nodes_by_id,
        terminals_by_id=terminals_by_id,
        segments_by_id=segments_by_id,
        inbound_neighbors=dict(inbound_neighbors),
        outbound_neighbors=dict(outbound_neighbors),
        inbound_segments_by_terminal_id=dict(inbound_segments_by_terminal_id),
        outbound_segments_by_terminal_id=dict(outbound_segments_by_terminal_id),
        node_terminal_ids=dict(node_terminal_ids),
    )


def _handoff_rows(power_system, snapshot, domains_by_id, disabled):
    rows = []
    redundancy_groups = list(power_system.redundancy_groups.prefetch_related('power_domains').order_by('name'))
    for node, terminal in _iter_power_handoff_terminals(snapshot):
        upstream_domain_ids = _collect_upstream_domain_ids(snapshot, terminal)
        upstream_domains = tuple(
            domains_by_id[domain_id]
            for domain_id in sorted(upstream_domain_ids)
            if domain_id in domains_by_id
        )
        rows.append({
            'node': node,
            'terminal': terminal,
            'upstream_domains': upstream_domains,
            'assessments': tuple(
                _assess_redundancy_group(group, upstream_domain_ids)
                for group in redundancy_groups
                if group.power_domains.exists()
            ),
        })
    return tuple(rows)


def _handoffs(power_system):
    return power_system.power_handoff_points.select_related(
        'electrical_node',
        'electrical_terminal__node',
        'power_port__device__rack',
        'expected_redundancy_group',
    ).order_by('name', 'feed_label', 'pk')


def _handoff_target(handoff):
    terminal = handoff.electrical_terminal
    node = handoff.electrical_node or (terminal.node if terminal is not None else None)
    return node, terminal


def _match_handoff_row(handoff, rows):
    for row in rows:
        if handoff.electrical_terminal_id and row['terminal'].pk == handoff.electrical_terminal_id:
            return row
        if (
            not handoff.electrical_terminal_id
            and handoff.electrical_node_id
            and row['node'].pk == handoff.electrical_node_id
        ):
            return row
    return None


def _handoff_impact_reasons(handoff, node, terminal, row, disabled):
    reasons = []
    if handoff.pk in disabled['power_handoff_point_ids']:
        reasons.append('handoff_out_of_service')
    if handoff.power_port_id in disabled['power_port_ids']:
        reasons.append('internal_power_bus_out_of_service')
    if node is not None and node.pk in disabled['electrical_node_ids']:
        reasons.append('node_out_of_service')
    if terminal is not None and terminal.pk in disabled['electrical_terminal_ids']:
        reasons.append('terminal_out_of_service')
    if row is None:
        reasons.append('unreachable')
    elif not row['upstream_domains']:
        reasons.append('unreachable')
        reasons.append('no_upstream_domain')
    return reasons


def _redundancy_violations_for_handoff(handoff, node, terminal, row, remaining_domains):
    group = handoff.expected_redundancy_group
    if group is None:
        return ()
    if row is None:
        matched_domains = ()
        finding_types = ('distinct_path_count_not_met',)
        if group.requires_domain_isolation:
            finding_types = finding_types + ('domain_isolation_not_met',)
        return (ScenarioRedundancyViolation(
            handoff=handoff,
            node=node,
            terminal=terminal,
            redundancy_group=group,
            matched_domains=matched_domains,
            finding_types=finding_types,
            message=f'Power handoff {handoff} is unreachable in the scenario.',
        ),)

    for assessment in row['assessments']:
        if assessment.redundancy_group.pk == group.pk and not assessment.is_compliant:
            return (ScenarioRedundancyViolation(
                handoff=handoff,
                node=node,
                terminal=terminal,
                redundancy_group=group,
                matched_domains=assessment.matched_domains,
                finding_types=assessment.finding_types,
                message=assessment.summary,
            ),)

    del remaining_domains
    return ()


def _finding(finding_type, message, obj, *, severity, **details):
    return {
        'finding_type': finding_type,
        'message': message,
        'object': obj,
        'severity': severity,
        **details,
    }


def _ids(objects, explicit_ids):
    ids = {obj.pk for obj in objects if getattr(obj, 'pk', None) is not None}
    ids.update(explicit_ids or ())
    return ids


def _unique_objects(objects):
    seen = set()
    unique = []
    for obj in objects:
        if obj.pk in seen:
            continue
        seen.add(obj.pk)
        unique.append(obj)
    return tuple(unique)
