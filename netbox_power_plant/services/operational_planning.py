from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping

from netbox_power_plant.choices import PowerFindingSeverityChoices
from netbox_power_plant.services.capacity import build_power_system_capacity_summary
from netbox_power_plant.services.scenarios import PowerOutageScenario, simulate_power_scenario


ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
KW_QUANT = Decimal("0.001")


@dataclass(frozen=True)
class HandoffPlanningLoad:
    handoff: object
    power_port_id: int | None
    node: object | None
    current_load_kw: Decimal
    reserved_load_kw: Decimal
    projected_load_kw: Decimal
    load_source: str | None = None
    missing_current_load_data: bool = False


@dataclass(frozen=True)
class ProjectedNodeCapacity:
    node: object
    current_load_kw: Decimal
    reserved_load_kw: Decimal
    projected_load_kw: Decimal
    capacity_kw: Decimal | None
    projected_headroom_kw: Decimal | None
    projected_utilization_pct: Decimal | None
    projected_reserve_margin_pct: Decimal | None


@dataclass(frozen=True)
class ProjectedSegmentCapacity:
    segment: object
    current_load_kw: Decimal
    reserved_load_kw: Decimal
    projected_load_kw: Decimal
    capacity_kw: Decimal | None
    projected_headroom_kw: Decimal | None
    projected_utilization_pct: Decimal | None


@dataclass(frozen=True)
class CapacityPlanningSummary:
    power_system: object
    capacity_summary: object
    handoff_loads: tuple[HandoffPlanningLoad, ...] = ()
    node_rollups: tuple[ProjectedNodeCapacity, ...] = ()
    segment_rollups: tuple[ProjectedSegmentCapacity, ...] = ()
    reserved_load_kw: Decimal = ZERO
    projected_load_kw: Decimal = ZERO
    projected_headroom_kw: Decimal | None = None
    projected_capacity_findings: tuple[dict, ...] = ()
    top_projected_capacity_findings: tuple[dict, ...] = field(default_factory=tuple)
    unmatched_reserved_kw_by_power_port_id: Mapping[int, Decimal] = field(default_factory=dict)

    @property
    def projected_capacity_finding_count(self) -> int:
        return len(self.projected_capacity_findings)


@dataclass(frozen=True)
class MaintenanceRedundancyLoss:
    handoff: object | None
    device: object | None
    rack: object | None
    node: object | None
    terminal: object | None
    redundancy_group: object
    matched_domains: tuple
    finding_types: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class MaintenanceImpactSummary:
    power_system: object
    scenario: PowerOutageScenario
    scenario_result: object
    impacted_handoffs: tuple = ()
    impacted_devices: tuple = ()
    impacted_racks: tuple = ()
    handoff_impacts: tuple = ()
    redundancy_losses: tuple[MaintenanceRedundancyLoss, ...] = ()
    findings: tuple[dict, ...] = ()

    @property
    def impacted_handoff_count(self) -> int:
        return len(self.impacted_handoffs)

    @property
    def impacted_device_count(self) -> int:
        return len(self.impacted_devices)

    @property
    def impacted_rack_count(self) -> int:
        return len(self.impacted_racks)

    @property
    def redundancy_loss_count(self) -> int:
        return len(self.redundancy_losses)


@dataclass(frozen=True)
class OperationalPlanningSummary:
    power_system: object
    capacity_plan: CapacityPlanningSummary
    maintenance_impact: MaintenanceImpactSummary


def build_capacity_planning_summary(
    power_system,
    *,
    reserved_kw_by_power_port_id: Mapping[int, Decimal | int | float | str] | None = None,
) -> CapacityPlanningSummary:
    capacity_summary = build_power_system_capacity_summary(power_system)
    reserved_by_port_id = _normalize_reserved_kw_by_power_port_id(reserved_kw_by_power_port_id)

    handoff_loads = _build_handoff_planning_loads(capacity_summary, reserved_by_port_id)
    matched_power_port_ids = {load.power_port_id for load in handoff_loads if load.power_port_id is not None}
    unmatched_reserved_kw_by_power_port_id = {
        power_port_id: reserved_kw
        for power_port_id, reserved_kw in reserved_by_port_id.items()
        if power_port_id not in matched_power_port_ids
    }

    direct_reserved_by_node_id = _direct_reserved_kw_by_node_id(handoff_loads)
    descendant_reserved_by_node_id = _descendant_reserved_kw_by_node_id(capacity_summary, direct_reserved_by_node_id)
    projected_node_rollups = _build_projected_node_rollups(
        capacity_summary,
        direct_reserved_by_node_id,
        descendant_reserved_by_node_id,
    )
    projected_segment_rollups = _build_projected_segment_rollups(
        capacity_summary,
        direct_reserved_by_node_id,
        descendant_reserved_by_node_id,
    )

    reserved_load_kw = sum((load.reserved_load_kw for load in handoff_loads), ZERO)
    projected_load_kw = capacity_summary.total_load_kw + reserved_load_kw
    projected_headroom_kw = _headroom(capacity_summary.total_capacity_kw, projected_load_kw)
    projected_capacity_findings = _build_projected_capacity_findings(
        projected_node_rollups,
        projected_segment_rollups,
        unmatched_reserved_kw_by_power_port_id,
    )

    return CapacityPlanningSummary(
        power_system=power_system,
        capacity_summary=capacity_summary,
        handoff_loads=handoff_loads,
        node_rollups=projected_node_rollups,
        segment_rollups=projected_segment_rollups,
        reserved_load_kw=reserved_load_kw,
        projected_load_kw=projected_load_kw,
        projected_headroom_kw=projected_headroom_kw,
        projected_capacity_findings=projected_capacity_findings,
        top_projected_capacity_findings=tuple(sorted(projected_capacity_findings, key=_finding_sort_key)[:5]),
        unmatched_reserved_kw_by_power_port_id=unmatched_reserved_kw_by_power_port_id,
    )


def build_maintenance_impact_summary(
    power_system,
    *,
    scenario: PowerOutageScenario | None = None,
    electrical_node_ids: Iterable[int] = (),
    electrical_terminal_ids: Iterable[int] = (),
    electrical_segment_ids: Iterable[int] = (),
    power_domain_ids: Iterable[int] = (),
    power_handoff_point_ids: Iterable[int] = (),
    internal_power_bus_ids: Iterable[int] = (),
) -> MaintenanceImpactSummary:
    scenario = _build_scenario(
        scenario,
        electrical_node_ids=electrical_node_ids,
        electrical_terminal_ids=electrical_terminal_ids,
        electrical_segment_ids=electrical_segment_ids,
        power_domain_ids=power_domain_ids,
        power_handoff_point_ids=power_handoff_point_ids,
        internal_power_bus_ids=internal_power_bus_ids,
    )
    scenario_result = simulate_power_scenario(power_system, scenario, include_capacity=False)
    redundancy_losses = _build_redundancy_losses(scenario_result)

    return MaintenanceImpactSummary(
        power_system=power_system,
        scenario=scenario,
        scenario_result=scenario_result,
        impacted_handoffs=scenario_result.impacted_handoffs,
        impacted_devices=scenario_result.impacted_devices,
        impacted_racks=scenario_result.impacted_racks,
        handoff_impacts=scenario_result.handoff_impacts,
        redundancy_losses=redundancy_losses,
        findings=scenario_result.findings,
    )


def build_operational_planning_summary(
    power_system,
    *,
    reserved_kw_by_power_port_id: Mapping[int, Decimal | int | float | str] | None = None,
    scenario: PowerOutageScenario | None = None,
    electrical_node_ids: Iterable[int] = (),
    electrical_terminal_ids: Iterable[int] = (),
    electrical_segment_ids: Iterable[int] = (),
    power_domain_ids: Iterable[int] = (),
    power_handoff_point_ids: Iterable[int] = (),
    internal_power_bus_ids: Iterable[int] = (),
) -> OperationalPlanningSummary:
    return OperationalPlanningSummary(
        power_system=power_system,
        capacity_plan=build_capacity_planning_summary(
            power_system,
            reserved_kw_by_power_port_id=reserved_kw_by_power_port_id,
        ),
        maintenance_impact=build_maintenance_impact_summary(
            power_system,
            scenario=scenario,
            electrical_node_ids=electrical_node_ids,
            electrical_terminal_ids=electrical_terminal_ids,
            electrical_segment_ids=electrical_segment_ids,
            power_domain_ids=power_domain_ids,
            power_handoff_point_ids=power_handoff_point_ids,
            internal_power_bus_ids=internal_power_bus_ids,
        ),
    )


def _build_handoff_planning_loads(capacity_summary, reserved_by_port_id):
    loads = []
    for handoff_load in capacity_summary.handoff_loads:
        handoff = handoff_load.handoff
        power_port_id = handoff.power_port_id
        current_load_kw = handoff_load.load_kw if handoff_load.load_kw is not None else ZERO
        reserved_load_kw = reserved_by_port_id.get(power_port_id, ZERO)
        loads.append(
            HandoffPlanningLoad(
                handoff=handoff,
                power_port_id=power_port_id,
                node=handoff_load.node,
                current_load_kw=current_load_kw,
                reserved_load_kw=reserved_load_kw,
                projected_load_kw=current_load_kw + reserved_load_kw,
                load_source=handoff_load.load_source,
                missing_current_load_data=handoff_load.missing_load_data,
            )
        )
    return tuple(loads)


def _direct_reserved_kw_by_node_id(handoff_loads):
    reserved_by_node_id = {}
    for load in handoff_loads:
        if load.node is None or load.reserved_load_kw == ZERO:
            continue
        reserved_by_node_id[load.node.pk] = reserved_by_node_id.get(load.node.pk, ZERO) + load.reserved_load_kw
    return reserved_by_node_id


def _descendant_reserved_kw_by_node_id(capacity_summary, direct_reserved_by_node_id):
    nodes = [rollup.node for rollup in capacity_summary.node_rollups]
    children_by_parent_id = {}
    for node in nodes:
        if node.parent_node_id:
            children_by_parent_id.setdefault(node.parent_node_id, []).append(node)

    cache = {}

    def reserved_below(node):
        if node.pk in cache:
            return cache[node.pk]
        total = ZERO
        for child in children_by_parent_id.get(node.pk, ()):
            total += direct_reserved_by_node_id.get(child.pk, ZERO)
            total += reserved_below(child)
        cache[node.pk] = total
        return total

    return {node.pk: reserved_below(node) for node in nodes}


def _build_projected_node_rollups(
    capacity_summary,
    direct_reserved_by_node_id,
    descendant_reserved_by_node_id,
):
    rollups = []
    for rollup in capacity_summary.node_rollups:
        direct_reserved_kw = direct_reserved_by_node_id.get(rollup.node.pk, ZERO)
        descendant_reserved_kw = descendant_reserved_by_node_id.get(rollup.node.pk, ZERO)
        reserved_load_kw = direct_reserved_kw + descendant_reserved_kw
        projected_load_kw = rollup.total_load_kw + reserved_load_kw
        projected_headroom_kw = _headroom(rollup.capacity_kw, projected_load_kw)
        rollups.append(
            ProjectedNodeCapacity(
                node=rollup.node,
                current_load_kw=rollup.total_load_kw,
                reserved_load_kw=reserved_load_kw,
                projected_load_kw=projected_load_kw,
                capacity_kw=rollup.capacity_kw,
                projected_headroom_kw=projected_headroom_kw,
                projected_utilization_pct=_utilization_pct(projected_load_kw, rollup.capacity_kw),
                projected_reserve_margin_pct=_reserve_margin_pct(projected_headroom_kw, rollup.capacity_kw),
            )
        )
    return tuple(rollups)


def _build_projected_segment_rollups(
    capacity_summary,
    direct_reserved_by_node_id,
    descendant_reserved_by_node_id,
):
    rollups = []
    for rollup in capacity_summary.segment_rollups:
        to_node_id = rollup.segment.to_terminal.node_id
        reserved_load_kw = direct_reserved_by_node_id.get(to_node_id, ZERO) + descendant_reserved_by_node_id.get(
            to_node_id, ZERO
        )
        projected_load_kw = rollup.load_kw + reserved_load_kw
        rollups.append(
            ProjectedSegmentCapacity(
                segment=rollup.segment,
                current_load_kw=rollup.load_kw,
                reserved_load_kw=reserved_load_kw,
                projected_load_kw=projected_load_kw,
                capacity_kw=rollup.capacity_kw,
                projected_headroom_kw=_headroom(rollup.capacity_kw, projected_load_kw),
                projected_utilization_pct=_utilization_pct(projected_load_kw, rollup.capacity_kw),
            )
        )
    return tuple(rollups)


def _build_projected_capacity_findings(
    projected_node_rollups,
    projected_segment_rollups,
    unmatched_reserved_kw_by_power_port_id,
):
    findings = []
    for rollup in projected_node_rollups:
        if rollup.projected_load_kw > ZERO and rollup.capacity_kw is None:
            findings.append(
                _finding(
                    "projected_missing_capacity_data",
                    f"Electrical node {rollup.node} has projected load but no usable or installed capacity.",
                    rollup.node,
                    severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                    current_load_kw=rollup.current_load_kw,
                    reserved_load_kw=rollup.reserved_load_kw,
                    projected_load_kw=rollup.projected_load_kw,
                )
            )
        elif rollup.capacity_kw is not None and rollup.projected_load_kw > rollup.capacity_kw:
            findings.append(
                _finding(
                    "projected_capacity_exceeded",
                    (
                        f"Electrical node {rollup.node} projected load {rollup.projected_load_kw} kW "
                        f"exceeds capacity {rollup.capacity_kw} kW."
                    ),
                    rollup.node,
                    severity=PowerFindingSeverityChoices.SEVERITY_CRITICAL,
                    current_load_kw=rollup.current_load_kw,
                    reserved_load_kw=rollup.reserved_load_kw,
                    projected_load_kw=rollup.projected_load_kw,
                    capacity_kw=rollup.capacity_kw,
                )
            )
        elif (
            rollup.capacity_kw is not None
            and rollup.node.reserve_margin_pct is not None
            and rollup.projected_reserve_margin_pct is not None
            and rollup.projected_reserve_margin_pct < rollup.node.reserve_margin_pct
        ):
            findings.append(
                _finding(
                    "projected_reserve_margin_breached",
                    (
                        f"Electrical node {rollup.node} projected reserve margin "
                        f"{rollup.projected_reserve_margin_pct}% is below required "
                        f"{rollup.node.reserve_margin_pct}%."
                    ),
                    rollup.node,
                    severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
                    current_load_kw=rollup.current_load_kw,
                    reserved_load_kw=rollup.reserved_load_kw,
                    projected_load_kw=rollup.projected_load_kw,
                    capacity_kw=rollup.capacity_kw,
                    projected_reserve_margin_pct=rollup.projected_reserve_margin_pct,
                    required_reserve_margin_pct=rollup.node.reserve_margin_pct,
                )
            )

    for rollup in projected_segment_rollups:
        if rollup.projected_load_kw > ZERO and rollup.capacity_kw is None:
            findings.append(
                _finding(
                    "projected_missing_capacity_data",
                    f"Electrical segment {rollup.segment} has projected load but no usable ampacity and voltage.",
                    rollup.segment,
                    severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                    current_load_kw=rollup.current_load_kw,
                    reserved_load_kw=rollup.reserved_load_kw,
                    projected_load_kw=rollup.projected_load_kw,
                )
            )
        elif rollup.capacity_kw is not None and rollup.projected_load_kw > rollup.capacity_kw:
            findings.append(
                _finding(
                    "projected_capacity_exceeded",
                    (
                        f"Electrical segment {rollup.segment} projected load {rollup.projected_load_kw} kW "
                        f"exceeds capacity {rollup.capacity_kw} kW."
                    ),
                    rollup.segment,
                    severity=PowerFindingSeverityChoices.SEVERITY_CRITICAL,
                    current_load_kw=rollup.current_load_kw,
                    reserved_load_kw=rollup.reserved_load_kw,
                    projected_load_kw=rollup.projected_load_kw,
                    capacity_kw=rollup.capacity_kw,
                )
            )

    for power_port_id, reserved_kw in unmatched_reserved_kw_by_power_port_id.items():
        findings.append(
            _finding(
                "unmatched_reserved_power_port",
                f"Power port {power_port_id} has {reserved_kw} kW reserved but no handoff in this power system.",
                None,
                severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
                power_port_id=power_port_id,
                reserved_load_kw=reserved_kw,
            )
        )

    return tuple(findings)


def _build_scenario(
    scenario,
    *,
    electrical_node_ids,
    electrical_terminal_ids,
    electrical_segment_ids,
    power_domain_ids,
    power_handoff_point_ids,
    internal_power_bus_ids,
):
    if scenario is None:
        return PowerOutageScenario(
            electrical_node_ids=_ids(electrical_node_ids),
            electrical_terminal_ids=_ids(electrical_terminal_ids),
            electrical_segment_ids=_ids(electrical_segment_ids),
            power_domain_ids=_ids(power_domain_ids),
            power_handoff_point_ids=_ids(power_handoff_point_ids),
            internal_power_bus_ids=_ids(internal_power_bus_ids),
        )

    return PowerOutageScenario(
        electrical_nodes=scenario.electrical_nodes,
        electrical_terminals=scenario.electrical_terminals,
        electrical_segments=scenario.electrical_segments,
        power_domains=scenario.power_domains,
        power_handoff_points=scenario.power_handoff_points,
        internal_power_buses=scenario.internal_power_buses,
        electrical_node_ids=_merge_ids(scenario.electrical_node_ids, electrical_node_ids),
        electrical_terminal_ids=_merge_ids(scenario.electrical_terminal_ids, electrical_terminal_ids),
        electrical_segment_ids=_merge_ids(scenario.electrical_segment_ids, electrical_segment_ids),
        power_domain_ids=_merge_ids(scenario.power_domain_ids, power_domain_ids),
        power_handoff_point_ids=_merge_ids(scenario.power_handoff_point_ids, power_handoff_point_ids),
        internal_power_bus_ids=_merge_ids(scenario.internal_power_bus_ids, internal_power_bus_ids),
    )


def _build_redundancy_losses(scenario_result):
    handoff_impacts_by_handoff_id = {impact.handoff.pk: impact for impact in scenario_result.handoff_impacts}
    losses = []
    for violation in scenario_result.redundancy_violations:
        impact = handoff_impacts_by_handoff_id.get(violation.handoff.pk) if violation.handoff else None
        device = impact.device if impact is not None else _device_for_handoff(violation.handoff)
        losses.append(
            MaintenanceRedundancyLoss(
                handoff=violation.handoff,
                device=device,
                rack=impact.rack if impact is not None else _rack_for_device(device),
                node=violation.node,
                terminal=violation.terminal,
                redundancy_group=violation.redundancy_group,
                matched_domains=violation.matched_domains,
                finding_types=violation.finding_types,
                message=violation.message,
            )
        )
    return tuple(losses)


def _device_for_handoff(handoff):
    if handoff is None or not handoff.power_port_id:
        return None
    return handoff.power_port.device


def _rack_for_device(device):
    if device is None or not getattr(device, "rack_id", None):
        return None
    return device.rack


def _normalize_reserved_kw_by_power_port_id(reserved_kw_by_power_port_id):
    if not reserved_kw_by_power_port_id:
        return {}

    normalized = {}
    for power_port_id, reserved_kw in reserved_kw_by_power_port_id.items():
        if reserved_kw is None:
            continue
        normalized_reserved_kw = _to_decimal(reserved_kw).quantize(KW_QUANT)
        if normalized_reserved_kw < ZERO:
            raise ValueError("Reserved load must be zero or greater.")
        if normalized_reserved_kw == ZERO:
            continue
        normalized[int(power_port_id)] = normalized_reserved_kw
    return normalized


def _headroom(capacity_kw, load_kw):
    if capacity_kw is None:
        return None
    return capacity_kw - load_kw


def _utilization_pct(load_kw, capacity_kw):
    if capacity_kw is None or capacity_kw <= ZERO:
        return None
    return ((load_kw / capacity_kw) * ONE_HUNDRED).quantize(Decimal("0.01"))


def _reserve_margin_pct(headroom_kw, capacity_kw):
    if headroom_kw is None or capacity_kw is None or capacity_kw <= ZERO:
        return None
    return ((headroom_kw / capacity_kw) * ONE_HUNDRED).quantize(Decimal("0.01"))


def _finding(finding_type, message, obj, *, severity, **details):
    return {
        "finding_type": finding_type,
        "message": message,
        "object": obj,
        "severity": severity,
        **details,
    }


def _finding_sort_key(finding):
    severity_order = {
        PowerFindingSeverityChoices.SEVERITY_CRITICAL: 0,
        PowerFindingSeverityChoices.SEVERITY_ERROR: 1,
        PowerFindingSeverityChoices.SEVERITY_WARNING: 2,
        PowerFindingSeverityChoices.SEVERITY_INFO: 3,
    }
    return severity_order.get(finding.get("severity"), 9), finding.get("finding_type", ""), finding.get("message", "")


def _ids(values):
    return tuple(int(value) for value in values or ())


def _merge_ids(*values):
    ids = set()
    for value in values:
        ids.update(_ids(value))
    return tuple(sorted(ids))


def _to_decimal(value):
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


OperatorCapacityPlan = CapacityPlanningSummary
MaintenanceImpactPlan = MaintenanceImpactSummary
OperationalPlan = OperationalPlanningSummary
build_operator_capacity_plan = build_capacity_planning_summary
build_maintenance_impact_plan = build_maintenance_impact_summary
build_operational_plan = build_operational_planning_summary
