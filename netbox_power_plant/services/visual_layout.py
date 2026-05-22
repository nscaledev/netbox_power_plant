from __future__ import annotations

from dataclasses import dataclass

from netbox_power_plant.choices import TopologyStateChoices
from netbox_power_plant.services.graph import PowerGraphBuilder


@dataclass(frozen=True)
class VisualTrace:
    key: str
    node_ids: tuple[int, ...]
    segment_ids: tuple[int, ...]


@dataclass(frozen=True)
class VisualNodeMarker:
    node_id: int
    label: str
    x: float
    y: float
    color: str
    kind: str | None
    trace_keys: tuple[str, ...]


@dataclass(frozen=True)
class VisualSegmentLine:
    segment_id: int
    label: str
    from_node_id: int
    to_node_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    trace_keys: tuple[str, ...]


@dataclass(frozen=True)
class VisualAssetMarker:
    object_type: str
    object_id: int
    label: str
    x: float
    y: float
    trace_keys: tuple[str, ...]


@dataclass(frozen=True)
class VisualHandoffMarker:
    handoff_id: int
    label: str
    target_label: str | None
    x: float
    y: float
    trace: VisualTrace


@dataclass(frozen=True)
class VisualLayoutMap:
    width: float
    height: float
    view_box: str
    unit_label: str | None
    nodes: tuple[VisualNodeMarker, ...]
    segments: tuple[VisualSegmentLine, ...]
    assets: tuple[VisualAssetMarker, ...]
    handoffs: tuple[VisualHandoffMarker, ...]

    @property
    def is_available(self) -> bool:
        return bool(self.width and self.height)


def build_visual_layout_map(layout) -> VisualLayoutMap | None:
    if not layout.has_spatial_frame:
        return None

    width = _positive_float(layout.spatial_context.width) or _max_coordinate(
        layout.placements,
        layout.mapped_assets,
        layout.delivery_overlays,
        axis='x',
    )
    height = _positive_float(layout.spatial_context.height) or _max_coordinate(
        layout.placements,
        layout.mapped_assets,
        layout.delivery_overlays,
        axis='y',
    )
    if not width or not height:
        return None

    snapshot = PowerGraphBuilder.build_for_power_system(
        layout.power_system,
        node_states=(TopologyStateChoices.STATE_ACTIVE,),
        path_states=(TopologyStateChoices.STATE_ACTIVE,),
    )
    traces_by_handoff_id = _build_traces(layout, snapshot)
    trace_keys_by_node_id, trace_keys_by_segment_id, trace_keys_by_asset = _index_trace_keys(
        layout,
        traces_by_handoff_id,
    )
    node_coordinates = {
        item.node.pk: (item.x, item.y)
        for item in layout.placements
        if item.node is not None and item.x is not None and item.y is not None
    }

    return VisualLayoutMap(
        width=width,
        height=height,
        view_box=f'0 0 {_format_number(width)} {_format_number(height)}',
        unit_label=layout.spatial_context.measurement_unit,
        nodes=tuple(_build_node_marker(item, trace_keys_by_node_id) for item in layout.placements if _has_xy(item)),
        segments=tuple(_iter_segment_lines(snapshot, node_coordinates, trace_keys_by_segment_id)),
        assets=tuple(_build_asset_marker(item, trace_keys_by_asset) for item in layout.mapped_assets if _has_xy(item)),
        handoffs=tuple(_iter_handoff_markers(layout, traces_by_handoff_id)),
    )


def _build_traces(layout, snapshot):
    traces_by_handoff_id = {}
    for row in layout.delivery_overlays:
        node_id = getattr(getattr(row.delivery_point, 'electrical_node', None), 'pk', None)
        if node_id is None and getattr(row.delivery_point, 'electrical_terminal', None) is not None:
            node_id = row.delivery_point.electrical_terminal.node_id
        if node_id is None:
            continue

        upstream_node_ids = snapshot.upstream_node_ids(node_id) | {node_id}
        upstream_segment_ids = {
            segment.pk
            for segment in snapshot.segments_by_id.values()
            if segment.from_terminal.node_id in upstream_node_ids and segment.to_terminal.node_id in upstream_node_ids
        }
        trace_key = f'handoff-{row.delivery_point.pk}'
        traces_by_handoff_id[row.delivery_point.pk] = VisualTrace(
            key=trace_key,
            node_ids=tuple(sorted(upstream_node_ids)),
            segment_ids=tuple(sorted(upstream_segment_ids)),
        )
    return traces_by_handoff_id


def _index_trace_keys(layout, traces_by_handoff_id):
    trace_keys_by_node_id = {}
    trace_keys_by_segment_id = {}
    trace_keys_by_asset = {}

    for overlay in layout.delivery_overlays:
        trace = traces_by_handoff_id.get(overlay.delivery_point.pk)
        if trace is None:
            continue
        for node_id in trace.node_ids:
            trace_keys_by_node_id.setdefault(node_id, set()).add(trace.key)
        for segment_id in trace.segment_ids:
            trace_keys_by_segment_id.setdefault(segment_id, set()).add(trace.key)
        power_port = getattr(overlay.delivery_point, 'power_port', None)
        target_type = overlay.target_type
        target_id = getattr(power_port, 'device_id', None)
        if overlay.target_type == 'rack':
            target_id = getattr(getattr(power_port, 'device', None), 'rack_id', None)
        if target_type and target_id:
            trace_keys_by_asset.setdefault((target_type, target_id), set()).add(trace.key)

    return (
        {key: tuple(sorted(value)) for key, value in trace_keys_by_node_id.items()},
        {key: tuple(sorted(value)) for key, value in trace_keys_by_segment_id.items()},
        {key: tuple(sorted(value)) for key, value in trace_keys_by_asset.items()},
    )


def _build_node_marker(item, trace_keys_by_node_id):
    return VisualNodeMarker(
        node_id=item.node.pk,
        label=item.object_name or item.node.name,
        x=item.x,
        y=item.y,
        color=item.color or '#0d6efd',
        kind=item.symbol_kind,
        trace_keys=trace_keys_by_node_id.get(item.node.pk, ()),
    )


def _iter_segment_lines(snapshot, node_coordinates, trace_keys_by_segment_id):
    for segment in sorted(
        snapshot.segments_by_id.values(),
        key=lambda item: (item.from_terminal.node.name, item.name, item.pk),
    ):
        from_node_id = segment.from_terminal.node_id
        to_node_id = segment.to_terminal.node_id
        if from_node_id not in node_coordinates or to_node_id not in node_coordinates:
            continue
        x1, y1 = node_coordinates[from_node_id]
        x2, y2 = node_coordinates[to_node_id]
        yield VisualSegmentLine(
            segment_id=segment.pk,
            label=segment.name,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            trace_keys=trace_keys_by_segment_id.get(segment.pk, ()),
        )


def _build_asset_marker(item, trace_keys_by_asset):
    return VisualAssetMarker(
        object_type=item.object_type,
        object_id=item.object_id,
        label=item.object_name or f'{item.object_type} #{item.object_id}',
        x=item.x,
        y=item.y,
        trace_keys=trace_keys_by_asset.get((item.object_type, item.object_id), ()),
    )


def _iter_handoff_markers(layout, traces_by_handoff_id):
    for item in layout.delivery_overlays:
        if not item.is_mapped_on_spatial or item.x is None or item.y is None:
            continue
        trace = traces_by_handoff_id.get(item.delivery_point.pk)
        if trace is None:
            continue
        yield VisualHandoffMarker(
            handoff_id=item.delivery_point.pk,
            label=item.delivery_point.feed_label or item.delivery_point.name,
            target_label=item.target_name,
            x=item.x,
            y=item.y,
            trace=trace,
        )


def _max_coordinate(placements, assets, handoffs, *, axis):
    coordinates = []
    for item in (*placements, *assets, *handoffs):
        value = getattr(item, axis, None)
        if value is not None:
            coordinates.append(value)
    if not coordinates:
        return None
    return max(coordinates) + 10


def _has_xy(item):
    return item.x is not None and item.y is not None


def _positive_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _format_number(value):
    return f'{value:g}'
