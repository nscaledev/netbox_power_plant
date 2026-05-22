from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from netbox_power_plant.choices import (
    CapacityReservationStatusChoices,
    InternalPowerBusAttachmentRoleChoices,
    PhaseModeChoices,
    PowerFindingSeverityChoices,
)
from netbox_power_plant.models import (
    CapacityReservation,
    ElectricalNode,
    ElectricalSegment,
    InternalPowerBus,
    PowerHandoffPoint,
)
from netbox_power_plant.services.graph import PowerGraphBuilder


ZERO = Decimal('0')
ONE_HUNDRED = Decimal('100')
THREE_PHASE_FACTOR = Decimal('1.732')


@dataclass(frozen=True)
class HandoffLoad:
    handoff: PowerHandoffPoint
    node: ElectricalNode | None
    load_kw: Decimal | None
    load_source: str | None
    missing_load_data: bool


@dataclass(frozen=True)
class NodeCapacityRollup:
    node: ElectricalNode
    direct_load_kw: Decimal = ZERO
    descendant_load_kw: Decimal = ZERO
    total_load_kw: Decimal = ZERO
    direct_reserved_kw: Decimal = ZERO
    descendant_reserved_kw: Decimal = ZERO
    total_reserved_kw: Decimal = ZERO
    capacity_kw: Decimal | None = None
    available_capacity_kw: Decimal | None = None
    headroom_kw: Decimal | None = None
    utilization_pct: Decimal | None = None
    reserve_margin_pct: Decimal | None = None


@dataclass(frozen=True)
class SegmentCapacityRollup:
    segment: ElectricalSegment
    load_kw: Decimal = ZERO
    capacity_kw: Decimal | None = None
    headroom_kw: Decimal | None = None
    utilization_pct: Decimal | None = None


@dataclass(frozen=True)
class BusCapacityRollup:
    bus: InternalPowerBus
    load_kw: Decimal = ZERO
    attachment_count: int = 0
    missing_load_count: int = 0


@dataclass(frozen=True)
class PowerSystemCapacitySummary:
    power_system: object
    total_load_kw: Decimal = ZERO
    total_reserved_kw: Decimal = ZERO
    total_capacity_kw: Decimal | None = None
    headroom_kw: Decimal | None = None
    handoff_loads: tuple[HandoffLoad, ...] = ()
    node_rollups: tuple[NodeCapacityRollup, ...] = ()
    segment_rollups: tuple[SegmentCapacityRollup, ...] = ()
    bus_rollups: tuple[BusCapacityRollup, ...] = ()
    findings: tuple[dict, ...] = ()
    top_findings: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def finding_count(self) -> int:
        return len(self.findings)


@dataclass(frozen=True)
class NodeCapacityPathHop:
    hop_index: int
    node: ElectricalNode
    segment: ElectricalSegment | None = None
    capacity_kw: Decimal | None = None
    derated_capacity_kw: Decimal | None = None
    reserve_margin_kw: Decimal = ZERO
    direct_load_kw: Decimal = ZERO
    descendant_load_kw: Decimal = ZERO
    total_load_kw: Decimal = ZERO
    reserved_kw: Decimal = ZERO
    total_reserved_kw: Decimal = ZERO
    node_available_kw: Decimal | None = None
    segment_capacity_kw: Decimal | None = None
    segment_load_kw: Decimal = ZERO
    segment_available_kw: Decimal | None = None
    available_kw: Decimal | None = None
    bottleneck_type: str | None = None
    reservation_breakdown: tuple[dict, ...] = ()
    load_breakdown: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        return {
            'hop_index': self.hop_index,
            'node_id': self.node.pk,
            'node': str(self.node),
            'segment_id': self.segment.pk if self.segment else None,
            'segment': str(self.segment) if self.segment else None,
            'capacity_kw': self.capacity_kw,
            'derated_capacity_kw': self.derated_capacity_kw,
            'reserve_margin_kw': self.reserve_margin_kw,
            'direct_load_kw': self.direct_load_kw,
            'descendant_load_kw': self.descendant_load_kw,
            'total_load_kw': self.total_load_kw,
            'reserved_kw': self.reserved_kw,
            'total_reserved_kw': self.total_reserved_kw,
            'node_available_kw': self.node_available_kw,
            'segment_capacity_kw': self.segment_capacity_kw,
            'segment_load_kw': self.segment_load_kw,
            'segment_available_kw': self.segment_available_kw,
            'available_kw': self.available_kw,
            'bottleneck_type': self.bottleneck_type,
            'reservation_breakdown': self.reservation_breakdown,
            'load_breakdown': self.load_breakdown,
        }


@dataclass(frozen=True)
class NodeCapacityPathRollup:
    node: ElectricalNode
    hops: tuple[NodeCapacityPathHop, ...] = ()
    first_bottleneck: NodeCapacityPathHop | None = None
    system_summary: dict = field(default_factory=dict)

    @property
    def available_kw(self) -> Decimal | None:
        if self.first_bottleneck is None:
            return None
        return self.first_bottleneck.available_kw

    def to_dict(self) -> dict:
        return {
            'node_id': self.node.pk,
            'node': str(self.node),
            'available_kw': self.available_kw,
            'system_summary': self.system_summary,
            'first_bottleneck': self.first_bottleneck.to_dict() if self.first_bottleneck else None,
            'hops': [hop.to_dict() for hop in self.hops],
        }


def build_power_system_capacity_summary(power_system) -> PowerSystemCapacitySummary:
    nodes = tuple(
        power_system.electrical_nodes.select_related('parent_node').order_by('name', 'pk')
    )
    direct_loads = {node.pk: ZERO for node in nodes}
    findings = []

    handoff_loads = []
    for handoff in _handoffs(power_system):
        node = handoff.electrical_node or (handoff.electrical_terminal.node if handoff.electrical_terminal_id else None)
        load_kw, load_source = _power_port_load_kw(handoff.power_port)
        missing_load_data = load_kw is None
        if node is not None and load_kw is not None:
            direct_loads[node.pk] = direct_loads.get(node.pk, ZERO) + load_kw
        if missing_load_data:
            findings.append(_finding(
                'missing_load_data',
                f'Power handoff {handoff} has no allocated or maximum draw on {handoff.power_port}.',
                handoff,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                handoff_id=handoff.pk,
            ))
        handoff_loads.append(HandoffLoad(
            handoff=handoff,
            node=node,
            load_kw=load_kw,
            load_source=load_source,
            missing_load_data=missing_load_data,
        ))

    descendant_loads = _descendant_loads(nodes, direct_loads)
    direct_reservations = _active_reserved_kw_by_node_id(node.pk for node in nodes)
    descendant_reservations = _descendant_loads(nodes, direct_reservations)
    node_rollups = []
    for node in nodes:
        capacity_kw = _node_capacity_kw(node)
        direct_load_kw = direct_loads.get(node.pk, ZERO)
        descendant_load_kw = descendant_loads.get(node.pk, ZERO)
        total_load_kw = direct_load_kw + descendant_load_kw
        direct_reserved_kw = direct_reservations.get(node.pk, ZERO)
        descendant_reserved_kw = descendant_reservations.get(node.pk, ZERO)
        total_reserved_kw = direct_reserved_kw + descendant_reserved_kw
        available_capacity_kw = _available_capacity_after_reservations(capacity_kw, total_reserved_kw)
        effective_load_kw = total_load_kw + total_reserved_kw
        headroom_kw = _headroom(capacity_kw, effective_load_kw)
        utilization_pct = _utilization_pct(effective_load_kw, capacity_kw)
        reserve_margin_pct = _reserve_margin_pct(headroom_kw, capacity_kw)

        if total_load_kw > ZERO and capacity_kw is None:
            findings.append(_finding(
                'missing_capacity_data',
                f'Electrical node {node} has load but no usable or installed capacity.',
                node,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                load_kw=total_load_kw,
            ))
        elif capacity_kw is not None and effective_load_kw > capacity_kw:
            findings.append(_finding(
                'capacity_exceeded',
                f'Electrical node {node} load and reservations {effective_load_kw} kW exceed capacity {capacity_kw} kW.',
                node,
                severity=PowerFindingSeverityChoices.SEVERITY_CRITICAL,
                load_kw=total_load_kw,
                reserved_kw=total_reserved_kw,
                capacity_kw=capacity_kw,
            ))
        elif (
            capacity_kw is not None
            and node.reserve_margin_pct is not None
            and reserve_margin_pct is not None
            and reserve_margin_pct < node.reserve_margin_pct
        ):
            findings.append(_finding(
                'reserve_margin_breached',
                (
                    f'Electrical node {node} reserve margin {reserve_margin_pct}% '
                    f'is below required {node.reserve_margin_pct}%.'
                ),
                node,
                severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
                load_kw=total_load_kw,
                reserved_kw=total_reserved_kw,
                capacity_kw=capacity_kw,
                reserve_margin_pct=reserve_margin_pct,
                required_reserve_margin_pct=node.reserve_margin_pct,
            ))

        node_rollups.append(NodeCapacityRollup(
            node=node,
            direct_load_kw=direct_load_kw,
            descendant_load_kw=descendant_load_kw,
            total_load_kw=total_load_kw,
            direct_reserved_kw=direct_reserved_kw,
            descendant_reserved_kw=descendant_reserved_kw,
            total_reserved_kw=total_reserved_kw,
            capacity_kw=capacity_kw,
            available_capacity_kw=available_capacity_kw,
            headroom_kw=headroom_kw,
            utilization_pct=utilization_pct,
            reserve_margin_pct=reserve_margin_pct,
        ))

    segment_rollups = []
    for segment in _segments(power_system):
        to_node_id = segment.to_terminal.node_id
        load_kw = direct_loads.get(to_node_id, ZERO) + descendant_loads.get(to_node_id, ZERO)
        capacity_kw = _segment_capacity_kw(segment)
        headroom_kw = _headroom(capacity_kw, load_kw)
        utilization_pct = _utilization_pct(load_kw, capacity_kw)

        if load_kw > ZERO and capacity_kw is None:
            findings.append(_finding(
                'missing_capacity_data',
                f'Electrical segment {segment} has load but no usable ampacity and voltage.',
                segment,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                load_kw=load_kw,
            ))
        elif capacity_kw is not None and load_kw > capacity_kw:
            findings.append(_finding(
                'capacity_exceeded',
                f'Electrical segment {segment} load {load_kw} kW exceeds capacity {capacity_kw} kW.',
                segment,
                severity=PowerFindingSeverityChoices.SEVERITY_CRITICAL,
                load_kw=load_kw,
                capacity_kw=capacity_kw,
            ))

        segment_rollups.append(SegmentCapacityRollup(
            segment=segment,
            load_kw=load_kw,
            capacity_kw=capacity_kw,
            headroom_kw=headroom_kw,
            utilization_pct=utilization_pct,
        ))

    bus_rollups = []
    for bus in _buses(power_system):
        load_kw = ZERO
        attachment_count = 0
        missing_load_count = 0
        for attachment in bus.attachments.all():
            if attachment.attachment_role != InternalPowerBusAttachmentRoleChoices.ROLE_LOAD:
                continue
            attachment_count += 1
            attachment_load_kw, _ = _power_port_load_kw(attachment.power_port)
            if attachment_load_kw is None:
                missing_load_count += 1
                findings.append(_finding(
                    'missing_load_data',
                    (
                        f'Internal power bus attachment {attachment} has no allocated or maximum draw '
                        f'on {attachment.power_port}.'
                    ),
                    attachment,
                    severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                    bus_id=bus.pk,
                ))
            else:
                load_kw += attachment_load_kw
        bus_rollups.append(BusCapacityRollup(
            bus=bus,
            load_kw=load_kw,
            attachment_count=attachment_count,
            missing_load_count=missing_load_count,
        ))

    root_nodes = tuple(node for node in nodes if node.parent_node_id is None)
    root_capacity_kw = _sum_known(_node_capacity_kw(node) for node in root_nodes)
    root_reserved_kw = _sum_known(
        direct_reservations.get(node.pk, ZERO) + descendant_reservations.get(node.pk, ZERO)
        for node in root_nodes
    ) or ZERO
    total_load_kw = _sum_known(load.load_kw for load in handoff_loads) or ZERO
    headroom_kw = _headroom(root_capacity_kw, total_load_kw + root_reserved_kw)
    top_findings = tuple(sorted(findings, key=_finding_sort_key)[:5])

    return PowerSystemCapacitySummary(
        power_system=power_system,
        total_load_kw=total_load_kw,
        total_reserved_kw=root_reserved_kw,
        total_capacity_kw=root_capacity_kw,
        headroom_kw=headroom_kw,
        handoff_loads=tuple(handoff_loads),
        node_rollups=tuple(node_rollups),
        segment_rollups=tuple(segment_rollups),
        bus_rollups=tuple(bus_rollups),
        findings=tuple(findings),
        top_findings=top_findings,
    )


def build_capacity_findings(power_system) -> tuple[dict, ...]:
    return build_power_system_capacity_summary(power_system).findings


def build_node_capacity_path_rollup(node: ElectricalNode, *, as_of=None) -> NodeCapacityPathRollup:
    as_of = as_of or timezone.localdate()
    snapshot = PowerGraphBuilder.build_for_power_system(node.power_system)
    upstream_node_ids = snapshot.upstream_node_ids(node.pk)
    relevant_node_ids = {node.pk, *upstream_node_ids}
    system_summary = build_power_system_capacity_summary(node.power_system)
    node_rollups_by_id = {rollup.node.pk: rollup for rollup in system_summary.node_rollups}
    segment_rollups_by_id = {rollup.segment.pk: rollup for rollup in system_summary.segment_rollups}
    reservations_by_node_id = _active_reserved_kw_by_node_id(relevant_node_ids, as_of=as_of)
    reservation_rows_by_node_id = _active_reservations_by_node_id(relevant_node_ids, as_of=as_of)
    loads_by_node_id = _handoff_load_breakdown_by_node_id(system_summary.handoff_loads)

    hops = []
    visited_edges = set()
    queue = [(node.pk, 0, None)]

    while queue:
        node_id, hop_index, segment = queue.pop(0)
        hop_node = snapshot.nodes_by_id.get(node_id)
        if hop_node is None:
            continue

        hops.append(_build_node_capacity_path_hop(
            hop_index=hop_index,
            node=hop_node,
            segment=segment,
            node_rollup=node_rollups_by_id.get(node_id),
            segment_rollup=segment_rollups_by_id.get(segment.pk) if segment else None,
            reserved_kw=reservations_by_node_id.get(node_id, ZERO),
            reservation_rows=reservation_rows_by_node_id.get(node_id, ()),
            load_rows=loads_by_node_id.get(node_id, ()),
        ))

        inbound_edges = []
        for upstream_id in snapshot.inbound_neighbors.get(node_id, ()):
            if upstream_id not in upstream_node_ids:
                continue
            for inbound_segment in _segments_between(snapshot, upstream_id, node_id):
                edge_key = (upstream_id, node_id, inbound_segment.pk)
                if edge_key in visited_edges:
                    continue
                visited_edges.add(edge_key)
                inbound_edges.append((upstream_id, inbound_segment))

        inbound_edges.sort(key=lambda edge: (
            snapshot.nodes_by_id[edge[0]].name,
            snapshot.nodes_by_id[edge[0]].pk,
            edge[1].name,
            edge[1].pk,
        ))
        queue.extend((upstream_id, hop_index + 1, inbound_segment) for upstream_id, inbound_segment in inbound_edges)

    first_bottleneck = _first_bottleneck(hops)
    return NodeCapacityPathRollup(
        node=node,
        hops=tuple(hops),
        first_bottleneck=first_bottleneck,
        system_summary=_capacity_system_summary(system_summary),
    )


build_node_capacity_rollup = build_node_capacity_path_rollup


def _handoffs(power_system):
    return power_system.power_handoff_points.select_related(
        'electrical_node',
        'electrical_terminal__node',
        'power_port__device',
    ).order_by('name', 'pk')


def _segments(power_system):
    return power_system.electrical_segments.select_related(
        'from_terminal__node',
        'to_terminal__node',
    ).order_by('name', 'pk')


def _buses(power_system):
    return power_system.internal_power_buses.prefetch_related(
        'attachments__power_port__device',
    ).order_by('name', 'pk')


def _power_port_load_kw(power_port) -> tuple[Decimal | None, str | None]:
    allocated_draw = getattr(power_port, 'allocated_draw', None)
    if allocated_draw is not None:
        return (_to_decimal(allocated_draw) / Decimal('1000')).quantize(Decimal('0.001')), 'allocated_draw'

    maximum_draw = getattr(power_port, 'maximum_draw', None)
    if maximum_draw is not None:
        return (_to_decimal(maximum_draw) / Decimal('1000')).quantize(Decimal('0.001')), 'maximum_draw'

    return None, None


def _node_capacity_kw(node) -> Decimal | None:
    return node.usable_capacity_kw if node.usable_capacity_kw is not None else node.installed_capacity_kw


def _segment_capacity_kw(segment) -> Decimal | None:
    ampacity = segment.derated_ampacity_a if segment.derated_ampacity_a is not None else segment.ampacity_a
    voltage = segment.voltage_nominal
    if ampacity is None or voltage is None:
        return None

    factor = THREE_PHASE_FACTOR
    if segment.from_terminal.node.phase_mode == PhaseModeChoices.MODE_SINGLE_PHASE:
        factor = Decimal('1')
    return ((ampacity * voltage * factor) / Decimal('1000')).quantize(Decimal('0.001'))


def _node_path_segment_capacity_kw(segment) -> Decimal | None:
    ampacity = segment.derated_ampacity_a if segment.derated_ampacity_a is not None else segment.ampacity_a
    voltage = segment.voltage_nominal
    if ampacity is None or voltage is None:
        return None
    return ((ampacity * voltage) / Decimal('1000')).quantize(Decimal('0.001'))


def _active_reserved_kw_by_node_id(node_ids, *, as_of=None):
    node_ids = tuple(node_ids)
    if not node_ids:
        return {}

    as_of = as_of or timezone.localdate()
    rows = (
        CapacityReservation.objects
        .filter(
            node_id__in=node_ids,
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=as_of))
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=as_of))
        .values('node_id')
        .annotate(reserved_kw=Sum('reserved_kw'))
    )
    return {row['node_id']: row['reserved_kw'] or ZERO for row in rows}


def _active_reservations_by_node_id(node_ids, *, as_of=None):
    node_ids = tuple(node_ids)
    if not node_ids:
        return {}

    as_of = as_of or timezone.localdate()
    reservations = (
        CapacityReservation.objects
        .filter(
            node_id__in=node_ids,
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        .filter(Q(valid_from__isnull=True) | Q(valid_from__lte=as_of))
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=as_of))
        .select_related('tenant', 'rack', 'node__parent_node')
        .order_by('node__name', 'tenant__name', 'rack__name', 'name', 'pk')
    )
    rows_by_node_id = {}
    for reservation in reservations:
        row = _reservation_payload(reservation)
        rows_by_node_id.setdefault(reservation.node_id, []).append(row)
        node = reservation.node
        seen = {node.pk}
        while node.parent_node_id and node.parent_node_id not in seen:
            node = node.parent_node
            seen.add(node.pk)
            rows_by_node_id.setdefault(node.pk, []).append({**row, 'scope': 'descendant'})
    return {node_id: tuple(rows) for node_id, rows in rows_by_node_id.items()}


def _available_capacity_after_reservations(capacity_kw, reserved_kw):
    if capacity_kw is None:
        return None
    return capacity_kw - reserved_kw


def _build_node_capacity_path_hop(
    *,
    hop_index,
    node,
    segment,
    node_rollup,
    segment_rollup,
    reserved_kw,
    reservation_rows,
    load_rows,
):
    capacity_kw = _node_capacity_kw(node)
    derated_capacity_kw = _apply_node_derating(capacity_kw, node.derating_factor)
    reserve_margin_kw = _reserve_margin_kw(derated_capacity_kw, node.reserve_margin_pct)
    direct_load_kw = node_rollup.direct_load_kw if node_rollup is not None else ZERO
    descendant_load_kw = node_rollup.descendant_load_kw if node_rollup is not None else ZERO
    total_load_kw = node_rollup.total_load_kw if node_rollup is not None else ZERO
    total_reserved_kw = node_rollup.total_reserved_kw if node_rollup is not None else reserved_kw
    node_available_kw = _subtract_known(derated_capacity_kw, reserve_margin_kw, total_load_kw, total_reserved_kw)
    segment_capacity_kw = _node_path_segment_capacity_kw(segment) if segment else None
    segment_load_kw = segment_rollup.load_kw if segment_rollup is not None else ZERO
    segment_available_kw = _subtract_known(segment_capacity_kw, segment_load_kw)
    available_kw = _min_known(node_available_kw, segment_available_kw)
    bottleneck_type = _bottleneck_type(node_available_kw, segment_available_kw, available_kw)

    return NodeCapacityPathHop(
        hop_index=hop_index,
        node=node,
        segment=segment,
        capacity_kw=capacity_kw,
        derated_capacity_kw=derated_capacity_kw,
        reserve_margin_kw=reserve_margin_kw,
        direct_load_kw=direct_load_kw,
        descendant_load_kw=descendant_load_kw,
        total_load_kw=total_load_kw,
        reserved_kw=reserved_kw,
        total_reserved_kw=total_reserved_kw,
        node_available_kw=node_available_kw,
        segment_capacity_kw=segment_capacity_kw,
        segment_load_kw=segment_load_kw,
        segment_available_kw=segment_available_kw,
        available_kw=available_kw,
        bottleneck_type=bottleneck_type,
        reservation_breakdown=tuple(reservation_rows),
        load_breakdown=tuple(load_rows),
    )


def _segments_between(snapshot, from_node_id, to_node_id):
    segments = [
        segment
        for segment in snapshot.segments_by_id.values()
        if segment.from_terminal.node_id == from_node_id and segment.to_terminal.node_id == to_node_id
    ]
    return sorted(segments, key=lambda segment: (segment.name, segment.pk))


def _apply_node_derating(capacity_kw, derating_factor):
    if capacity_kw is None:
        return None
    if derating_factor is None:
        return capacity_kw
    return (capacity_kw * derating_factor).quantize(Decimal('0.001'))


def _reserve_margin_kw(capacity_kw, reserve_margin_pct):
    if capacity_kw is None or reserve_margin_pct is None:
        return ZERO
    return ((capacity_kw * reserve_margin_pct) / ONE_HUNDRED).quantize(Decimal('0.001'))


def _subtract_known(capacity_kw, *values):
    if capacity_kw is None:
        return None
    total = sum((value for value in values if value is not None), ZERO)
    return capacity_kw - total


def _min_known(*values):
    known = [value for value in values if value is not None]
    if not known:
        return None
    return min(known)


def _bottleneck_type(node_available_kw, segment_available_kw, available_kw):
    if available_kw is None:
        return None
    if segment_available_kw is not None and segment_available_kw == available_kw:
        return 'segment'
    if node_available_kw is not None and node_available_kw == available_kw:
        return 'node'
    return None


def _first_bottleneck(hops):
    known_hops = [hop for hop in hops if hop.available_kw is not None]
    if not known_hops:
        return None
    minimum_available_kw = min(hop.available_kw for hop in known_hops)
    return next(hop for hop in known_hops if hop.available_kw == minimum_available_kw)


def _descendant_loads(nodes, direct_loads):
    children_by_parent = {}
    for node in nodes:
        if node.parent_node_id:
            children_by_parent.setdefault(node.parent_node_id, []).append(node)

    cache = {}

    def load_below(node):
        if node.pk in cache:
            return cache[node.pk]
        total = ZERO
        for child in children_by_parent.get(node.pk, ()):
            total += direct_loads.get(child.pk, ZERO)
            total += load_below(child)
        cache[node.pk] = total
        return total

    return {node.pk: load_below(node) for node in nodes}


def _headroom(capacity_kw, load_kw):
    if capacity_kw is None:
        return None
    return capacity_kw - load_kw


def _utilization_pct(load_kw, capacity_kw):
    if capacity_kw is None or capacity_kw <= ZERO:
        return None
    return ((load_kw / capacity_kw) * ONE_HUNDRED).quantize(Decimal('0.01'))


def _reserve_margin_pct(headroom_kw, capacity_kw):
    if headroom_kw is None or capacity_kw is None or capacity_kw <= ZERO:
        return None
    return ((headroom_kw / capacity_kw) * ONE_HUNDRED).quantize(Decimal('0.01'))


def _sum_known(values):
    known = [value for value in values if value is not None]
    if not known:
        return None
    return sum(known, ZERO)


def _finding(finding_type, message, obj, *, severity, **details):
    return {
        'finding_type': finding_type,
        'message': message,
        'object': obj,
        'severity': severity,
        **details,
    }


def _finding_sort_key(finding):
    severity_order = {
        PowerFindingSeverityChoices.SEVERITY_CRITICAL: 0,
        PowerFindingSeverityChoices.SEVERITY_ERROR: 1,
        PowerFindingSeverityChoices.SEVERITY_WARNING: 2,
        PowerFindingSeverityChoices.SEVERITY_INFO: 3,
    }
    return severity_order.get(finding.get('severity'), 9), finding.get('finding_type', ''), finding.get('message', '')


def _handoff_load_breakdown_by_node_id(handoff_loads):
    rows_by_node_id = {}
    for load in handoff_loads:
        if load.node is None:
            continue
        row = {
            'handoff': _object_ref(load.handoff),
            'device': _object_ref(load.handoff.power_port.device) if load.handoff.power_port_id else None,
            'power_port': _object_ref(load.handoff.power_port) if load.handoff.power_port_id else None,
            'load_kw': load.load_kw,
            'load_source': load.load_source,
            'missing_load_data': load.missing_load_data,
            'scope': 'direct',
        }
        rows_by_node_id.setdefault(load.node.pk, []).append(row)
        node = load.node
        seen = {node.pk}
        while node.parent_node_id and node.parent_node_id not in seen:
            node = node.parent_node
            seen.add(node.pk)
            rows_by_node_id.setdefault(node.pk, []).append({**row, 'scope': 'descendant'})
    return {node_id: tuple(rows) for node_id, rows in rows_by_node_id.items()}


def _reservation_payload(reservation):
    return {
        'reservation': _object_ref(reservation),
        'tenant': _object_ref(reservation.tenant),
        'rack': _object_ref(reservation.rack),
        'reserved_kw': reservation.reserved_kw,
        'status': reservation.status,
        'valid_from': reservation.valid_from,
        'valid_until': reservation.valid_until,
        'scope': 'direct',
    }


def _capacity_system_summary(summary):
    return {
        'power_system': _object_ref(summary.power_system),
        'total_load_kw': summary.total_load_kw,
        'total_reserved_kw': summary.total_reserved_kw,
        'total_capacity_kw': summary.total_capacity_kw,
        'headroom_kw': summary.headroom_kw,
        'finding_count': summary.finding_count,
    }


def _object_ref(obj):
    if obj is None:
        return None
    return {
        'id': obj.pk,
        'display': str(obj),
        'name': getattr(obj, 'name', str(obj)),
    }


def _to_decimal(value):
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
