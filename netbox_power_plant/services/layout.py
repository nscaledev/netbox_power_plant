from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from netbox_power_plant.services.floorplan import get_floorplan_context_for_power_system
from netbox_power_plant.services.rack_delivery import build_rack_delivery_summary


@dataclass(frozen=True)
class LayoutPlacementItem:
    placement: object
    node: object
    scope_label: str
    x: float
    y: float
    width: float | None
    height: float | None
    rotation_degrees: float
    symbol_kind: str
    label_mode: str
    color: str
    z_index: int


@dataclass(frozen=True)
class LayoutDeliveryOverlayItem:
    delivery_point: object
    target_type: str
    target_name: str
    x: float | None
    y: float | None
    is_mapped_on_floorplan: bool
    upstream_domains: tuple
    is_redundancy_compliant: bool
    assessment_summary: str


@dataclass(frozen=True)
class LayoutMappedAssetItem:
    object_type: str
    object_id: int
    object_name: str | None
    x: float | None
    y: float | None
    canvas_object_type: str | None
    matched_delivery_points: tuple


@dataclass(frozen=True)
class PowerSystemLayoutViewModel:
    power_system: object
    floorplan_context: object
    placements: tuple[LayoutPlacementItem, ...]
    mapped_assets: tuple[LayoutMappedAssetItem, ...]
    delivery_overlays: tuple[LayoutDeliveryOverlayItem, ...]
    inferred_only_rows: tuple
    mapped_delivery_count: int
    unmapped_delivery_count: int

    @property
    def has_floorplan(self) -> bool:
        return self.floorplan_context.has_floorplan


def build_power_system_layout_view(power_system) -> PowerSystemLayoutViewModel:
    from netbox_power_plant.models import ElectricalNodePlacement

    floorplan_context = get_floorplan_context_for_power_system(power_system)
    delivery_summary = build_rack_delivery_summary(power_system)
    placements = tuple(
        LayoutPlacementItem(
            placement=placement,
            node=placement.electrical_node,
            scope_label=_describe_scope(placement),
            x=float(placement.x),
            y=float(placement.y),
            width=float(placement.width) if placement.width is not None else None,
            height=float(placement.height) if placement.height is not None else None,
            rotation_degrees=float(placement.rotation_degrees),
            symbol_kind=placement.get_symbol_kind_display(),
            label_mode=placement.get_label_mode_display(),
            color=placement.color or '',
            z_index=placement.z_index,
        )
        for placement in ElectricalNodePlacement.objects.filter(power_system=power_system)
        .select_related('electrical_node', 'site', 'location')
        .order_by('z_index', 'electrical_node__name', 'name')
    )

    mapped_references = {
        ('rack', mapped_rack.object_id): mapped_rack
        for mapped_rack in floorplan_context.mapped_racks
    }
    mapped_references.update({
        ('device', mapped_device.object_id): mapped_device
        for mapped_device in floorplan_context.mapped_devices
    })

    delivery_overlays = []
    matched_delivery_points_by_asset = defaultdict(list)
    inferred_only_rows = []
    for row in delivery_summary.rows:
        if not row.delivery_points:
            inferred_only_rows.append(row)
            continue

        for delivery_point in row.delivery_points:
            target_type, target_id, target_name = _resolve_delivery_target(delivery_point)
            mapped_reference = mapped_references.get((target_type, target_id))
            overlay = LayoutDeliveryOverlayItem(
                delivery_point=delivery_point,
                target_type=target_type,
                target_name=target_name,
                x=getattr(mapped_reference, 'x', None),
                y=getattr(mapped_reference, 'y', None),
                is_mapped_on_floorplan=mapped_reference is not None,
                upstream_domains=row.upstream_domains,
                is_redundancy_compliant=row.is_redundancy_compliant,
                assessment_summary=row.assessment_summary,
            )
            delivery_overlays.append(overlay)
            if mapped_reference is not None:
                matched_delivery_points_by_asset[(target_type, target_id)].append(delivery_point)

    mapped_assets = tuple(
        LayoutMappedAssetItem(
            object_type=object_type,
            object_id=mapped_reference.object_id,
            object_name=mapped_reference.object_name,
            x=mapped_reference.x,
            y=mapped_reference.y,
            canvas_object_type=mapped_reference.canvas_object_type,
            matched_delivery_points=tuple(matched_delivery_points_by_asset.get((object_type, mapped_reference.object_id), ())),
        )
        for object_type, references in (
            ('rack', floorplan_context.mapped_racks),
            ('device', floorplan_context.mapped_devices),
        )
        for mapped_reference in references
    )

    mapped_delivery_count = sum(1 for overlay in delivery_overlays if overlay.is_mapped_on_floorplan)
    return PowerSystemLayoutViewModel(
        power_system=power_system,
        floorplan_context=floorplan_context,
        placements=placements,
        mapped_assets=mapped_assets,
        delivery_overlays=tuple(delivery_overlays),
        inferred_only_rows=tuple(inferred_only_rows),
        mapped_delivery_count=mapped_delivery_count,
        unmapped_delivery_count=len(delivery_overlays) - mapped_delivery_count,
    )


def _describe_scope(placement):
    if placement.location is not None:
        return f'{placement.site.name} / {placement.location.name}'
    return placement.site.name


def _resolve_delivery_target(delivery_point):
    if delivery_point.rack is not None:
        return 'rack', delivery_point.rack_id, str(delivery_point.rack)
    if delivery_point.device is not None:
        return 'device', delivery_point.device_id, str(delivery_point.device)
    if delivery_point.power_port is not None:
        return 'device', delivery_point.power_port.device_id, str(delivery_point.power_port)
    return 'unknown', None, delivery_point.name
