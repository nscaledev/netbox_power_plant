from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from netbox_power_plant.services.rack_delivery import build_power_handoff_summary
from netbox_power_plant.services.spatial import get_spatial_context_for_power_system


@dataclass(frozen=True)
class LayoutPlacementItem:
    placement: object
    node: object | None
    scope_label: str
    x: float | None
    y: float | None
    width: float | None
    height: float | None
    rotation_degrees: float | None
    symbol_kind: str | None
    label_mode: str | None
    color: str
    z_index: int
    object_type: str | None = None
    object_name: str | None = None
    site_id: int | None = None
    location_id: int | None = None
    placement_scope_type: str | None = None


@dataclass(frozen=True)
class LayoutDeliveryOverlayItem:
    delivery_point: object
    target_type: str
    target_name: str | None
    x: float | None
    y: float | None
    is_mapped_on_spatial: bool
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
    spatial_context: object
    placements: tuple[LayoutPlacementItem, ...]
    mapped_assets: tuple[LayoutMappedAssetItem, ...]
    delivery_overlays: tuple[LayoutDeliveryOverlayItem, ...]
    inferred_only_rows: tuple
    mapped_delivery_count: int
    unmapped_delivery_count: int

    @property
    def has_spatial_frame(self) -> bool:
        return self.spatial_context.has_spatial_frame


def build_power_system_layout_view(power_system) -> PowerSystemLayoutViewModel:
    spatial_context = get_spatial_context_for_power_system(power_system)
    delivery_summary = build_power_handoff_summary(power_system)
    placements = _build_layout_placements(power_system, spatial_context)

    mapped_references = {
        ('rack', mapped_rack.object_id): mapped_rack
        for mapped_rack in spatial_context.mapped_racks
    }
    mapped_references.update({
        ('device', mapped_device.object_id): mapped_device
        for mapped_device in spatial_context.mapped_devices
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
                is_mapped_on_spatial=mapped_reference is not None,
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
            ('rack', spatial_context.mapped_racks),
            ('device', spatial_context.mapped_devices),
        )
        for mapped_reference in references
    )

    mapped_delivery_count = sum(1 for overlay in delivery_overlays if overlay.is_mapped_on_spatial)
    return PowerSystemLayoutViewModel(
        power_system=power_system,
        spatial_context=spatial_context,
        placements=placements,
        mapped_assets=mapped_assets,
        delivery_overlays=tuple(delivery_overlays),
        inferred_only_rows=tuple(inferred_only_rows),
        mapped_delivery_count=mapped_delivery_count,
        unmapped_delivery_count=len(delivery_overlays) - mapped_delivery_count,
    )


def _build_layout_placements(power_system, spatial_context):
    if spatial_context.availability.is_available and spatial_context.has_spatial_frame:
        return tuple(
            LayoutPlacementItem(
                placement=reference.placement,
                node=reference.object,
                scope_label=_describe_spatial_scope(reference, spatial_context),
                x=reference.x,
                y=reference.y,
                width=reference.width,
                height=reference.height,
                rotation_degrees=reference.rotation_degrees,
                symbol_kind=reference.symbol_kind,
                label_mode=reference.label_mode,
                color=reference.color or '',
                z_index=reference.z_index,
                object_type=reference.object_type,
                object_name=reference.object_name,
                site_id=reference.site_id,
                location_id=reference.location_id,
                placement_scope_type=reference.placement_scope_type,
            )
            for reference in spatial_context.node_placements
        )

    return _build_legacy_layout_placements(power_system)


def _build_legacy_layout_placements(power_system):
    try:
        from netbox_power_plant.models import ElectricalNodePlacement
    except Exception:
        return ()

    return tuple(
        LayoutPlacementItem(
            placement=placement,
            node=placement.electrical_node,
            scope_label=_describe_legacy_scope(placement),
            x=float(placement.x),
            y=float(placement.y),
            width=float(placement.width) if placement.width is not None else None,
            height=float(placement.height) if placement.height is not None else None,
            rotation_degrees=float(placement.rotation_degrees),
            symbol_kind=placement.get_symbol_kind_display(),
            label_mode=placement.get_label_mode_display(),
            color=placement.color or '',
            z_index=placement.z_index,
            object_type='electrical_node',
            object_name=str(placement.electrical_node),
            site_id=placement.site_id,
            location_id=placement.location_id,
            placement_scope_type=placement.placement_scope_type,
        )
        for placement in ElectricalNodePlacement.objects.filter(power_system=power_system)
        .select_related('electrical_node', 'site', 'location')
        .order_by('z_index', 'electrical_node__name', 'name')
    )


def _describe_spatial_scope(reference, spatial_context):
    if reference.frame_name:
        return reference.frame_name
    if reference.location_id:
        return f'Location #{reference.location_id}'
    if reference.site_id:
        return f'Site #{reference.site_id}'
    if spatial_context.source_scope:
        return spatial_context.source_scope.title()
    return 'Spatial scope'


def _describe_scope(placement):
    return _describe_legacy_scope(placement)


def _describe_legacy_scope(placement):
    if placement.location is not None:
        return f'{placement.site.name} / {placement.location.name}'
    return placement.site.name


def _resolve_delivery_target(delivery_point):
    power_port = getattr(delivery_point, 'power_port', None)
    device = getattr(power_port, 'device', None)
    if device is None:
        return 'device', None, None
    if getattr(device, 'rack_id', None):
        return 'rack', device.rack_id, device.rack.name
    return 'device', device.pk, str(power_port)
