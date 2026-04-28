from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from netbox_power_plant.services.layout import build_power_system_layout_view


@dataclass(frozen=True)
class LayoutValidationFinding:
    finding_type: str
    message: str
    object: object | None = None
    related_object: object | None = None


@dataclass(frozen=True)
class LayoutHealthSummary:
    power_system: object
    layout: object
    findings: tuple[LayoutValidationFinding, ...]
    finding_counts: dict[str, int]
    availability_reason: str | None
    mapped_delivery_count: int
    unmapped_delivery_count: int
    orphan_mapped_asset_count: int
    mis_scoped_placement_count: int
    redundancy_gap_count: int

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def has_floorplan(self) -> bool:
        return self.layout.has_floorplan

    @property
    def is_available(self) -> bool:
        return self.layout.floorplan_context.availability.is_available

    @property
    def is_healthy(self) -> bool:
        return self.is_available and self.finding_count == 0

    @property
    def top_findings(self) -> tuple[LayoutValidationFinding, ...]:
        return self.findings[:5]


def run_layout_checks(power_system, layout=None) -> tuple[LayoutValidationFinding, ...]:
    from netbox_power_plant.models import ElectricalNodePlacement

    layout = layout or build_power_system_layout_view(power_system)
    findings = []

    if layout.floorplan_context.availability.is_available and not layout.has_floorplan:
        findings.append(LayoutValidationFinding(
            finding_type='missing_floorplan_context',
            message='No site or location floorplan is resolved for this power system.',
            object=power_system,
        ))

    if layout.has_floorplan:
        for overlay in layout.delivery_overlays:
            if not overlay.is_mapped_on_floorplan:
                findings.append(LayoutValidationFinding(
                    finding_type='unmapped_rack_delivery_point',
                    message=f'Rack delivery point {overlay.delivery_point.name} is not represented on the resolved floorplan.',
                    object=overlay.delivery_point,
                ))
            elif not overlay.is_redundancy_compliant:
                findings.append(LayoutValidationFinding(
                    finding_type='redundancy_gap_visible_in_layout',
                    message=f'Rack delivery point {overlay.delivery_point.name} is visible in layout but remains noncompliant for redundancy.',
                    object=overlay.delivery_point,
                ))

        for asset in layout.mapped_assets:
            if asset.matched_delivery_points:
                continue
            findings.append(LayoutValidationFinding(
                finding_type='orphan_floorplan_mapping',
                message=f'{asset.object_type.title()} mapping {asset.object_name or asset.object_id} has no matching power delivery object.',
                object=asset,
            ))

    for placement in ElectricalNodePlacement.objects.filter(power_system=power_system).select_related('site', 'location', 'electrical_node'):
        if not _is_mis_scoped_placement(power_system, placement):
            continue
        findings.append(LayoutValidationFinding(
            finding_type='mis_scoped_node_placement',
            message=f'Electrical node placement {placement.name} does not match the resolved power system scope.',
            object=placement,
            related_object=placement.electrical_node,
        ))

    return tuple(findings)


def build_layout_health_summary(power_system) -> LayoutHealthSummary:
    layout = build_power_system_layout_view(power_system)
    findings = run_layout_checks(power_system, layout=layout)
    counts = Counter(finding.finding_type for finding in findings)
    return LayoutHealthSummary(
        power_system=power_system,
        layout=layout,
        findings=findings,
        finding_counts=dict(counts),
        availability_reason=layout.floorplan_context.availability.reason,
        mapped_delivery_count=layout.mapped_delivery_count,
        unmapped_delivery_count=counts.get('unmapped_rack_delivery_point', 0),
        orphan_mapped_asset_count=counts.get('orphan_floorplan_mapping', 0),
        mis_scoped_placement_count=counts.get('mis_scoped_node_placement', 0),
        redundancy_gap_count=counts.get('redundancy_gap_visible_in_layout', 0),
    )


def _is_mis_scoped_placement(power_system, placement) -> bool:
    if placement.site_id != power_system.site_id:
        return True

    power_system_location_id = power_system.location_id
    if power_system_location_id:
        return placement.location_id != power_system_location_id or placement.placement_scope_type != 'location'

    return placement.location_id is not None or placement.placement_scope_type != 'site'