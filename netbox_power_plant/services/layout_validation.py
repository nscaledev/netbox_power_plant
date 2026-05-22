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
    def has_spatial_frame(self) -> bool:
        return self.layout.has_spatial_frame

    @property
    def is_available(self) -> bool:
        return self.layout.spatial_context.availability.is_available

    @property
    def is_healthy(self) -> bool:
        return self.finding_count == 0

    @property
    def top_findings(self) -> tuple[LayoutValidationFinding, ...]:
        return self.findings[:5]


def run_layout_checks(power_system, layout=None) -> tuple[LayoutValidationFinding, ...]:
    layout = layout or build_power_system_layout_view(power_system)
    findings = []

    for overlay in layout.delivery_overlays:
        if not overlay.is_mapped_on_spatial:
            findings.append(LayoutValidationFinding(
                finding_type='unmapped_delivery_handoff',
                message=f'Power handoff point {overlay.delivery_point.name} has no matching spatial placement.',
                object=overlay.delivery_point,
            ))
        elif not overlay.is_redundancy_compliant:
            findings.append(LayoutValidationFinding(
                finding_type='redundancy_gap_visible_in_layout',
                message=f'Power handoff point {overlay.delivery_point.name} is visible in layout but remains noncompliant for redundancy.',
                object=overlay.delivery_point,
            ))

    for asset in layout.mapped_assets:
        if asset.matched_delivery_points:
            continue
        findings.append(LayoutValidationFinding(
            finding_type='orphan_spatial_placement',
            message=f'{asset.object_type.title()} spatial placement {asset.object_name or asset.object_id} has no matching power handoff point.',
            object=asset,
        ))

    for item in layout.placements:
        if not _is_mis_scoped_placement(power_system, item):
            continue
        findings.append(LayoutValidationFinding(
            finding_type='spatial_placement_scope_mismatch',
            message=f'Spatial placement {getattr(item.placement, "name", item.object_name or "unnamed")} does not match the resolved power system scope.',
            object=item.placement,
            related_object=item.node,
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
        availability_reason=layout.spatial_context.availability.reason,
        mapped_delivery_count=layout.mapped_delivery_count,
        unmapped_delivery_count=counts.get('unmapped_delivery_handoff', 0),
        orphan_mapped_asset_count=counts.get('orphan_spatial_placement', 0),
        mis_scoped_placement_count=counts.get('spatial_placement_scope_mismatch', 0),
        redundancy_gap_count=counts.get('redundancy_gap_visible_in_layout', 0),
    )


def _is_mis_scoped_placement(power_system, placement) -> bool:
    site_id = getattr(placement, 'site_id', None)
    location_id = getattr(placement, 'location_id', None)
    placement_scope_type = getattr(placement, 'placement_scope_type', None)
    if site_id is not None and site_id != power_system.site_id:
        return True

    power_system_location_id = power_system.location_id
    if power_system_location_id:
        return location_id not in (None, power_system_location_id) or placement_scope_type not in (None, 'location')

    return location_id is not None or placement_scope_type not in (None, 'site')
