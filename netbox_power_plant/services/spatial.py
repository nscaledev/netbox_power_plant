from __future__ import annotations

from dataclasses import dataclass


SPATIAL_SERVICE_NAME = 'netbox_power_plant.spatial'


@dataclass(frozen=True)
class SpatialAvailability:
    service_name: str
    models_importable: bool
    reason: str | None = None

    @property
    def is_available(self) -> bool:
        return self.models_importable

    @property
    def plugin_name(self) -> str:
        return self.service_name

    @property
    def is_importable(self) -> bool:
        return self.models_importable

    @property
    def is_enabled(self) -> bool:
        return self.models_importable


@dataclass(frozen=True)
class MappedObjectReference:
    object_type: str
    object_id: int
    object_name: str | None
    x: float | None
    y: float | None
    canvas_object_type: str | None
    placement: object | None = None
    frame_id: int | None = None
    frame_name: str | None = None
    width: float | None = None
    height: float | None = None
    rotation_degrees: float | None = None


@dataclass(frozen=True)
class SpatialPlacementReference:
    placement: object
    object: object | None
    object_type: str | None
    object_id: int | None
    object_name: str | None
    frame_id: int | None
    frame_name: str | None
    site_id: int | None
    location_id: int | None
    placement_scope_type: str | None
    x: float | None
    y: float | None
    width: float | None
    height: float | None
    rotation_degrees: float | None
    symbol_kind: str | None
    label_mode: str | None
    color: str | None
    z_index: int


@dataclass(frozen=True)
class ResolvedSpatialContext:
    availability: SpatialAvailability
    spatial_frame_id: int | None
    spatial_frame_name: str | None
    spatial_frame_url: str | None
    source_scope: str | None
    source_object_id: int | None
    site_id: int | None
    location_id: int | None
    assigned_image_id: int | None
    measurement_unit: str | None
    width: float | None
    height: float | None
    mapped_objects: tuple[MappedObjectReference, ...] = ()
    node_placements: tuple[SpatialPlacementReference, ...] = ()

    @property
    def has_spatial_frame(self) -> bool:
        return self.spatial_frame_id is not None

    @property
    def mapped_racks(self) -> tuple[MappedObjectReference, ...]:
        return tuple(reference for reference in self.mapped_objects if reference.object_type == 'rack')

    @property
    def mapped_devices(self) -> tuple[MappedObjectReference, ...]:
        return tuple(reference for reference in self.mapped_objects if reference.object_type == 'device')


def get_spatial_availability() -> SpatialAvailability:
    availability, _frame_model, _placement_model = _get_spatial_support()
    return availability


def get_spatial_context_for_power_system(power_system) -> ResolvedSpatialContext:
    availability, frame_model, placement_model = _get_spatial_support()
    if frame_model is None or placement_model is None:
        return _build_empty_context(power_system, availability)

    frame, source_scope, source_object_id = _resolve_frame_for_power_system(frame_model, power_system)
    placement_refs = _collect_placement_references(placement_model, power_system, frame)
    assigned_image = _first_attr(frame, ('assigned_image', 'background_image', 'image', 'underlay_image'))
    mapped_objects = tuple(
        MappedObjectReference(
            object_type=reference.object_type,
            object_id=reference.object_id,
            object_name=reference.object_name,
            x=reference.x,
            y=reference.y,
            canvas_object_type=_display_attr(reference.placement, ('canvas_object_type', 'placement_kind', 'shape', 'kind', 'symbol_kind')),
            placement=reference.placement,
            frame_id=reference.frame_id,
            frame_name=reference.frame_name,
            width=reference.width,
            height=reference.height,
            rotation_degrees=reference.rotation_degrees,
        )
        for reference in placement_refs
        if reference.object_type in {'rack', 'device'} and reference.object_id is not None
    )
    node_placements = tuple(
        reference
        for reference in placement_refs
        if reference.object_type == 'electrical_node' and _belongs_to_power_system(reference.object, power_system)
    )

    return ResolvedSpatialContext(
        availability=availability,
        spatial_frame_id=getattr(frame, 'pk', None),
        spatial_frame_name=str(frame) if frame is not None else None,
        spatial_frame_url=_safe_absolute_url(frame),
        source_scope=source_scope,
        source_object_id=source_object_id,
        site_id=getattr(power_system, 'site_id', getattr(getattr(power_system, 'site', None), 'pk', None)),
        location_id=getattr(power_system, 'location_id', getattr(getattr(power_system, 'location', None), 'pk', None)),
        assigned_image_id=getattr(assigned_image, 'pk', None),
        measurement_unit=_first_attr(frame, ('measurement_unit', 'units', 'unit')),
        width=_coerce_float(_first_attr(frame, ('width', 'canvas_width'))),
        height=_coerce_float(_first_attr(frame, ('height', 'canvas_height'))),
        mapped_objects=mapped_objects,
        node_placements=node_placements,
    )


def list_mapped_racks(power_system) -> tuple[MappedObjectReference, ...]:
    return get_spatial_context_for_power_system(power_system).mapped_racks


def list_mapped_devices(power_system) -> tuple[MappedObjectReference, ...]:
    return get_spatial_context_for_power_system(power_system).mapped_devices


def has_spatial_context(power_system) -> bool:
    return get_spatial_context_for_power_system(power_system).has_spatial_frame


def _build_empty_context(power_system, availability):
    return ResolvedSpatialContext(
        availability=availability,
        spatial_frame_id=None,
        spatial_frame_name=None,
        spatial_frame_url=None,
        source_scope=None,
        source_object_id=None,
        site_id=getattr(power_system, 'site_id', getattr(getattr(power_system, 'site', None), 'pk', None)),
        location_id=getattr(power_system, 'location_id', getattr(getattr(power_system, 'location', None), 'pk', None)),
        assigned_image_id=None,
        measurement_unit=None,
        width=None,
        height=None,
        mapped_objects=(),
        node_placements=(),
    )


def _get_spatial_support():
    frame_model, placement_model, import_error = _load_spatial_models()
    if frame_model is None or placement_model is None:
        return SpatialAvailability(
            service_name=SPATIAL_SERVICE_NAME,
            models_importable=False,
            reason=import_error or 'Native spatial models are not available yet.',
        ), None, None

    return SpatialAvailability(
        service_name=SPATIAL_SERVICE_NAME,
        models_importable=True,
    ), frame_model, placement_model


def _load_spatial_models():
    try:
        from netbox_power_plant.models import SpatialFrame, SpatialPlacement
    except Exception as exc:
        return None, None, f'Native spatial models could not be imported: {exc}'

    return SpatialFrame, SpatialPlacement, None


def _resolve_frame_for_power_system(frame_model, power_system):
    location = getattr(power_system, 'location', None)
    if location is not None:
        frame = _first_model_object(frame_model, location=location)
        if frame is not None:
            return frame, 'location', getattr(location, 'pk', None)

    site = getattr(power_system, 'site', None)
    if site is not None:
        frame = _first_model_object(frame_model, site=site, location__isnull=True)
        if frame is None:
            frame = _first_model_object(frame_model, site=site)
        if frame is not None:
            return frame, 'site', getattr(site, 'pk', None)

    return None, None, None


def _first_model_object(model, **filters):
    queryset = _filter_model(model, **filters)
    if queryset is None:
        return None
    try:
        return queryset.order_by('pk').first()
    except Exception:
        try:
            return queryset.first()
        except Exception:
            return None


def _collect_placement_references(placement_model, power_system, frame):
    queryset = _placement_queryset(placement_model, power_system, frame)
    if queryset is None:
        return ()

    try:
        queryset = queryset.select_related('frame', 'spatial_frame', 'site', 'location', 'electrical_node', 'rack', 'device')
    except Exception:
        pass

    try:
        queryset = queryset.order_by('z_index', 'pk')
    except Exception:
        pass

    return tuple(_build_placement_reference(placement) for placement in queryset)


def _placement_queryset(placement_model, power_system, frame):
    if frame is not None:
        frame_field = _first_model_field(placement_model, ('frame', 'spatial_frame'))
        if frame_field:
            return _filter_model(placement_model, **{frame_field: frame})

    filters = {}
    if _model_has_field(placement_model, 'power_system'):
        filters['power_system'] = power_system
    elif _model_has_field(placement_model, 'site'):
        filters['site'] = getattr(power_system, 'site', None)
        if getattr(power_system, 'location', None) is not None and _model_has_field(placement_model, 'location'):
            filters['location'] = getattr(power_system, 'location', None)

    if not filters:
        return ()

    return _filter_model(placement_model, **filters)


def _filter_model(model, **filters):
    try:
        supported_filters = {
            key: value
            for key, value in filters.items()
            if value is not None and _supports_filter(model, key)
        }
        return model.objects.filter(**supported_filters)
    except Exception:
        return None


def _build_placement_reference(placement) -> SpatialPlacementReference:
    obj, object_type, object_id = _resolve_placed_object(placement)
    frame = _first_attr(placement, ('frame', 'spatial_frame'))
    site = _first_attr(placement, ('site',))
    location = _first_attr(placement, ('location',))
    if site is None:
        site = _first_attr(frame, ('site',))
    if location is None:
        location = _first_attr(frame, ('location',))

    return SpatialPlacementReference(
        placement=placement,
        object=obj,
        object_type=object_type,
        object_id=object_id,
        object_name=_object_name(obj, placement),
        frame_id=getattr(frame, 'pk', None),
        frame_name=str(frame) if frame is not None else None,
        site_id=getattr(site, 'pk', getattr(placement, 'site_id', None)),
        location_id=getattr(location, 'pk', getattr(placement, 'location_id', None)),
        placement_scope_type=_display_attr(placement, ('placement_scope_type', 'scope_type', 'scope')),
        x=_coerce_float(_first_attr(placement, ('x', 'x_coordinate', 'left'))),
        y=_coerce_float(_first_attr(placement, ('y', 'y_coordinate', 'top'))),
        width=_coerce_float(_first_attr(placement, ('width',))),
        height=_coerce_float(_first_attr(placement, ('height',))),
        rotation_degrees=_coerce_float(_first_attr(placement, ('rotation_degrees', 'rotation'))),
        symbol_kind=_display_attr(placement, ('symbol_kind', 'placement_kind', 'shape', 'kind')),
        label_mode=_display_attr(placement, ('label_mode',)),
        color=_display_attr(placement, ('color',)),
        z_index=_coerce_int(_first_attr(placement, ('z_index',))) or 0,
    )


def _resolve_placed_object(placement):
    for attr_name, object_type in (
        ('electrical_node', 'electrical_node'),
        ('rack', 'rack'),
        ('device', 'device'),
        ('power_handoff_point', 'power_handoff_point'),
    ):
        obj = getattr(placement, attr_name, None)
        object_id = getattr(placement, f'{attr_name}_id', None) or getattr(obj, 'pk', None)
        if obj is not None or object_id is not None:
            return obj, object_type, _coerce_int(object_id)

    for attr_name in ('content_object', 'assigned_object', 'mapped_object', 'object', 'target'):
        obj = getattr(placement, attr_name, None)
        if obj is not None:
            return obj, _object_type_for_object(obj), getattr(obj, 'pk', None)

    object_id = _coerce_int(_first_attr(placement, ('object_id', 'assigned_object_id', 'mapped_object_id')))
    object_type = _normalize_object_type(_first_attr(placement, ('object_type', 'assigned_object_type', 'mapped_object_type', 'content_type')))
    return None, object_type, object_id


def _object_type_for_object(obj):
    meta = getattr(obj, '_meta', None)
    model_name = getattr(meta, 'model_name', None)
    if model_name:
        return model_name
    class_name = obj.__class__.__name__
    return ''.join(
        f'_{char.lower()}' if char.isupper() else char
        for char in class_name
    ).strip('_')


def _normalize_object_type(value):
    if value is None:
        return None

    model = getattr(value, 'model', None)
    if model:
        return str(model).replace('-', '_').lower()

    model_name = getattr(value, 'model_name', None)
    if model_name:
        return str(model_name).replace('-', '_').lower()

    return str(value).replace('-', '_').lower()


def _object_name(obj, placement):
    if obj is not None:
        return str(obj)
    return _display_attr(placement, ('object_name', 'name', 'label'))


def _belongs_to_power_system(obj, power_system):
    if obj is None:
        return False
    object_power_system_id = getattr(obj, 'power_system_id', None)
    if object_power_system_id is not None:
        return object_power_system_id == getattr(power_system, 'pk', None)
    object_power_system = getattr(obj, 'power_system', None)
    if object_power_system is not None:
        return getattr(object_power_system, 'pk', None) == getattr(power_system, 'pk', None)
    return True


def _first_model_field(model, field_names):
    for field_name in field_names:
        if _model_has_field(model, field_name):
            return field_name
    return None


def _model_has_field(model, field_name):
    meta = getattr(model, '_meta', None)
    if meta is None:
        return True
    try:
        meta.get_field(field_name)
        return True
    except Exception:
        return hasattr(model, field_name)


def _supports_filter(model, filter_name):
    field_name = filter_name.split('__', 1)[0]
    return _model_has_field(model, field_name)


def _first_attr(obj, attr_names):
    if obj is None:
        return None
    for attr_name in attr_names:
        value = getattr(obj, attr_name, None)
        if value is not None:
            return value
    return None


def _display_attr(obj, attr_names):
    value = _first_attr(obj, attr_names)
    if value is None:
        return None
    return str(value)


def _coerce_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_absolute_url(obj):
    if obj is None:
        return None
    try:
        return obj.get_absolute_url()
    except Exception:
        return None
