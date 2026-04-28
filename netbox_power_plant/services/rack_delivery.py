from dataclasses import dataclass

from netbox_power_plant.choices import NodeKindChoices, TerminalDirectionChoices, TopologyStateChoices
from netbox_power_plant.services.graph import PowerGraphBuilder


RACK_BOUNDARY_NODE_KINDS = {
    NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
    NodeKindChoices.KIND_RACK_PDU,
}


@dataclass(frozen=True)
class RackDeliveryAssessment:
    redundancy_group: object
    matched_domains: tuple
    is_compliant: bool
    finding_types: tuple
    summary: str


@dataclass(frozen=True)
class RackDeliverySummaryRow:
    node: object
    terminal: object
    delivery_points: tuple
    upstream_domains: tuple
    distinct_path_count: int
    assessments: tuple
    is_redundancy_compliant: bool
    assessment_summary: str


@dataclass(frozen=True)
class RackDeliverySummary:
    power_system: object
    rows: tuple
    delivery_count: int
    compliant_count: int
    noncompliant_count: int


def build_rack_delivery_summary(power_system):
    from netbox_power_plant.models import RackDeliveryPoint

    snapshot = PowerGraphBuilder.build_for_power_system(
        power_system,
        node_states=(TopologyStateChoices.STATE_ACTIVE,),
        path_states=(TopologyStateChoices.STATE_ACTIVE,),
    )
    domains = list(power_system.power_domains.order_by('priority', 'code', 'name'))
    domains_by_id = {domain.pk: domain for domain in domains}
    redundancy_groups = list(power_system.redundancy_groups.prefetch_related('power_domains').order_by('name'))
    delivery_points = list(
        RackDeliveryPoint.objects.filter(power_system=power_system)
        .select_related('rack', 'device', 'electrical_node', 'electrical_terminal', 'expected_redundancy_group')
        .order_by('name', 'feed_label', 'pk')
    )
    rows = []

    for node, terminal in _iter_rack_delivery_terminals(snapshot):
        upstream_domain_ids = _collect_upstream_domain_ids(snapshot, terminal)
        upstream_domains = tuple(
            domains_by_id[domain_id]
            for domain_id in sorted(upstream_domain_ids)
            if domain_id in domains_by_id
        )
        assessments = tuple(
            _assess_redundancy_group(group, upstream_domain_ids)
            for group in redundancy_groups
            if group.power_domains.exists()
        )
        is_redundancy_compliant = all(assessment.is_compliant for assessment in assessments)
        assessment_summary = '; '.join(assessment.summary for assessment in assessments) if assessments else 'No redundancy groups defined.'
        rows.append(RackDeliverySummaryRow(
            node=node,
            terminal=terminal,
            delivery_points=(),
            upstream_domains=upstream_domains,
            distinct_path_count=len(upstream_domains),
            assessments=assessments,
            is_redundancy_compliant=is_redundancy_compliant,
            assessment_summary=assessment_summary,
        ))

    rows = _attach_delivery_points(rows, delivery_points)

    compliant_count = sum(1 for row in rows if row.is_redundancy_compliant)
    noncompliant_count = len(rows) - compliant_count
    return RackDeliverySummary(
        power_system=power_system,
        rows=tuple(rows),
        delivery_count=len(rows),
        compliant_count=compliant_count,
        noncompliant_count=noncompliant_count,
    )


def _iter_rack_delivery_terminals(snapshot):
    terminals = sorted(
        snapshot.terminals_by_id.values(),
        key=lambda terminal: (terminal.node.name, terminal.position_index or 0, terminal.name),
    )
    for terminal in terminals:
        node = snapshot.nodes_by_id.get(terminal.node_id)
        if node is None or node.node_kind not in RACK_BOUNDARY_NODE_KINDS:
            continue
        if terminal.direction not in (TerminalDirectionChoices.DIRECTION_SINK, TerminalDirectionChoices.DIRECTION_BIDIRECTIONAL):
            continue
        yield node, terminal


def _collect_upstream_domain_ids(snapshot, terminal):
    relevant_node_ids = snapshot.upstream_node_ids(terminal.node_id) | {terminal.node_id}
    domain_ids = set()

    for segment in snapshot.segments_by_id.values():
        from_node_id = segment.from_terminal.node_id
        to_node_id = segment.to_terminal.node_id
        if from_node_id not in relevant_node_ids or to_node_id not in relevant_node_ids:
            continue
        if segment.power_domain_id:
            domain_ids.add(segment.power_domain_id)

    return domain_ids


def _assess_redundancy_group(group, upstream_domain_ids):
    group_domains = tuple(group.power_domains.order_by('priority', 'code', 'name'))
    matched_domains = tuple(domain for domain in group_domains if domain.pk in upstream_domain_ids)
    finding_types = []
    messages = []

    if len(matched_domains) < group.min_distinct_paths:
        finding_types.append('distinct_path_count_not_met')
        messages.append(
            f'{group.name}: requires {group.min_distinct_paths} distinct paths, found {len(matched_domains)}.'
        )

    if group.requires_domain_isolation and len(matched_domains) < min(group.min_distinct_paths, len(group_domains)):
        finding_types.append('domain_isolation_not_met')
        messages.append(f'{group.name}: upstream paths collapse before maintaining domain isolation.')

    if messages:
        summary = ' '.join(messages)
    else:
        summary = f'{group.name}: compliant.'

    return RackDeliveryAssessment(
        redundancy_group=group,
        matched_domains=matched_domains,
        is_compliant=not finding_types,
        finding_types=tuple(finding_types),
        summary=summary,
    )


def _attach_delivery_points(rows, delivery_points):
    row_delivery_points = {index: [] for index in range(len(rows))}
    terminal_row_indices = {}
    node_row_indices = {}

    for index, row in enumerate(rows):
        if row.terminal is not None:
            terminal_row_indices[row.terminal.pk] = index
        if row.node is not None:
            node_row_indices.setdefault(row.node.pk, []).append(index)

    unmatched_delivery_points = []
    for delivery_point in delivery_points:
        matched_index = None
        if delivery_point.electrical_terminal_id:
            matched_index = terminal_row_indices.get(delivery_point.electrical_terminal_id)
        elif delivery_point.electrical_node_id:
            candidate_indices = node_row_indices.get(delivery_point.electrical_node_id, [])
            if len(candidate_indices) == 1:
                matched_index = candidate_indices[0]

        if matched_index is None:
            unmatched_delivery_points.append(delivery_point)
            continue

        row_delivery_points[matched_index].append(delivery_point)

    updated_rows = []
    for index, row in enumerate(rows):
        delivery_points_for_row = tuple(row_delivery_points[index])
        assessment_summary = row.assessment_summary
        if delivery_points_for_row:
            assessment_summary = f'{assessment_summary} Modeled delivery point present.'
        else:
            assessment_summary = f'{assessment_summary} Inferred from active topology only.'
        updated_rows.append(RackDeliverySummaryRow(
            node=row.node,
            terminal=row.terminal,
            delivery_points=delivery_points_for_row,
            upstream_domains=row.upstream_domains,
            distinct_path_count=row.distinct_path_count,
            assessments=row.assessments,
            is_redundancy_compliant=row.is_redundancy_compliant,
            assessment_summary=assessment_summary,
        ))

    for delivery_point in unmatched_delivery_points:
        target_summary = _describe_delivery_point_target(delivery_point)
        updated_rows.append(RackDeliverySummaryRow(
            node=delivery_point.electrical_node,
            terminal=delivery_point.electrical_terminal,
            delivery_points=(delivery_point,),
            upstream_domains=(),
            distinct_path_count=0,
            assessments=(),
            is_redundancy_compliant=False,
            assessment_summary=f'Modeled delivery point for {target_summary} has no matching active derived rack-boundary path.',
        ))

    return tuple(updated_rows)


def _describe_delivery_point_target(delivery_point):
    if delivery_point.rack is not None:
        return str(delivery_point.rack)
    if delivery_point.device is not None:
        return str(delivery_point.device)
    return delivery_point.name