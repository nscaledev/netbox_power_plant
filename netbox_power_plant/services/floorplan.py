from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module

from django.conf import settings


FLOORPLAN_PLUGIN_NAME = 'netbox_floorplan'
FLOORPLAN_MODELS_MODULE = 'netbox_floorplan.models'


@dataclass(frozen=True)
class FloorplanAvailability:
    plugin_name: str
    is_importable: bool
    is_enabled: bool
    reason: str | None = None

    @property
    def is_available(self) -> bool:
        return self.is_importable and self.is_enabled


@dataclass(frozen=True)
class MappedRackReference:
    object_id: int
    object_name: str | None
    x: float | None
    y: float | None
    canvas_object_type: str | None


@dataclass(frozen=True)
class MappedDeviceReference:
    object_id: int
    object_name: str | None
    x: float | None
    y: float | None
    canvas_object_type: str | None


@dataclass(frozen=True)
class ResolvedFloorplanContext:
    availability: FloorplanAvailability
    floorplan_id: int | None
    floorplan_name: str | None
    floorplan_url: str | None
    source_scope: str | None
    source_object_id: int | None
    site_id: int | None
    location_id: int | None
    assigned_image_id: int | None
    measurement_unit: str | None
    width: float | None
    height: float | None
    mapped_racks: tuple[MappedRackReference, ...] = ()
    mapped_devices: tuple[MappedDeviceReference, ...] = ()

    @property
    def has_floorplan(self) -> bool:
        return self.floorplan_id is not None


def get_floorplan_availability() -> FloorplanAvailability:
    availability, _ = _get_floorplan_support()
    return availability


def get_floorplan_context_for_power_system(power_system) -> ResolvedFloorplanContext:
    availability, floorplan_model = _get_floorplan_support()
    if floorplan_model is None:
        return _build_empty_context(power_system, availability)

    floorplan, source_scope, source_object_id = _resolve_floorplan_for_power_system(floorplan_model, power_system)
    if floorplan is None:
        return _build_empty_context(power_system, availability)

    mapped_racks, mapped_devices = _collect_mapped_objects(floorplan.canvas)
    assigned_image = getattr(floorplan, 'assigned_image', None)
    return ResolvedFloorplanContext(
        availability=availability,
        floorplan_id=floorplan.pk,
        floorplan_name=str(floorplan),
        floorplan_url=_safe_absolute_url(floorplan),
        source_scope=source_scope,
        source_object_id=source_object_id,
        site_id=getattr(getattr(power_system, 'site', None), 'pk', None),
        location_id=getattr(getattr(power_system, 'location', None), 'pk', None),
        assigned_image_id=getattr(assigned_image, 'pk', None),
        measurement_unit=getattr(floorplan, 'measurement_unit', None),
        width=_coerce_float(getattr(floorplan, 'width', None)),
        height=_coerce_float(getattr(floorplan, 'height', None)),
        mapped_racks=mapped_racks,
        mapped_devices=mapped_devices,
    )


def list_mapped_racks(power_system) -> tuple[MappedRackReference, ...]:
    return get_floorplan_context_for_power_system(power_system).mapped_racks


def list_mapped_devices(power_system) -> tuple[MappedDeviceReference, ...]:
    return get_floorplan_context_for_power_system(power_system).mapped_devices


def has_floorplan_context(power_system) -> bool:
    return get_floorplan_context_for_power_system(power_system).has_floorplan


def _get_floorplan_support():
    floorplan_model, import_error = _load_floorplan_model()
    if floorplan_model is None:
        return FloorplanAvailability(
            plugin_name=FLOORPLAN_PLUGIN_NAME,
            is_importable=False,
            is_enabled=False,
            reason=import_error,
        ), None

    if not _is_plugin_enabled():
        return FloorplanAvailability(
            plugin_name=FLOORPLAN_PLUGIN_NAME,
            is_importable=True,
            is_enabled=False,
            reason='The floorplan plugin is importable but not enabled in settings.PLUGINS.',
        ), None

    return FloorplanAvailability(
        plugin_name=FLOORPLAN_PLUGIN_NAME,
        is_importable=True,
        is_enabled=True,
    ), floorplan_model


def _load_floorplan_model():
    try:
        models_module = import_module(FLOORPLAN_MODELS_MODULE)
    except Exception as exc:
        return None, f'The floorplan plugin could not be imported: {exc}'

    floorplan_model = getattr(models_module, 'Floorplan', None)
    if floorplan_model is None:
        return None, 'The floorplan plugin is missing the Floorplan model export.'

    return floorplan_model, None


def _is_plugin_enabled() -> bool:
    plugins = tuple(getattr(settings, 'PLUGINS', ()) or ())
    return FLOORPLAN_PLUGIN_NAME in plugins


def _resolve_floorplan_for_power_system(floorplan_model, power_system):
    location = getattr(power_system, 'location', None)
    if location is not None:
        floorplan = _first_floorplan(floorplan_model, location=location)
        if floorplan is not None:
            return floorplan, 'location', getattr(location, 'pk', None)

    site = getattr(power_system, 'site', None)
    if site is not None:
        floorplan = _first_floorplan(floorplan_model, site=site)
        if floorplan is not None:
            return floorplan, 'site', getattr(site, 'pk', None)

    return None, None, None


def _first_floorplan(floorplan_model, **filters):
    return floorplan_model.objects.filter(**filters).order_by('pk').first()


def _build_empty_context(power_system, availability):
    return ResolvedFloorplanContext(
        availability=availability,
        floorplan_id=None,
        floorplan_name=None,
        floorplan_url=None,
        source_scope=None,
        source_object_id=None,
        site_id=getattr(getattr(power_system, 'site', None), 'pk', None),
        location_id=getattr(getattr(power_system, 'location', None), 'pk', None),
        assigned_image_id=None,
        measurement_unit=None,
        width=None,
        height=None,
        mapped_racks=(),
        mapped_devices=(),
    )


def _collect_mapped_objects(canvas):
    rack_refs = {}
    device_refs = {}

    # Keep canvas parsing isolated in this adapter so the rest of the plugin stays decoupled.
    for canvas_object in _walk_canvas_objects(canvas):
        custom_meta = canvas_object.get('custom_meta')
        if not isinstance(custom_meta, dict):
            continue

        object_type = custom_meta.get('object_type')
        object_id = _coerce_int(custom_meta.get('object_id'))
        if object_type not in {'rack', 'device'} or object_id is None:
            continue

        reference_kwargs = {
            'object_id': object_id,
            'object_name': custom_meta.get('object_name'),
            'x': _coerce_float(canvas_object.get('left')),
            'y': _coerce_float(canvas_object.get('top')),
            'canvas_object_type': canvas_object.get('type'),
        }
        if object_type == 'rack':
            _upsert_reference(rack_refs, object_id, MappedRackReference(**reference_kwargs))
        else:
            _upsert_reference(device_refs, object_id, MappedDeviceReference(**reference_kwargs))

    return tuple(rack_refs.values()), tuple(device_refs.values())


def _walk_canvas_objects(node):
    if isinstance(node, list):
        for item in node:
            yield from _walk_canvas_objects(item)
        return

    if not isinstance(node, dict):
        return

    yield node
    objects = node.get('objects')
    if isinstance(objects, list):
        for item in objects:
            yield from _walk_canvas_objects(item)


def _upsert_reference(reference_map, object_id, new_reference):
    current_reference = reference_map.get(object_id)
    if current_reference is None:
        reference_map[object_id] = new_reference
        return

    if current_reference.x is None and new_reference.x is not None:
        reference_map[object_id] = new_reference
        return

    if current_reference.y is None and new_reference.y is not None:
        reference_map[object_id] = new_reference


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


def _safe_absolute_url(floorplan):
    try:
        return floorplan.get_absolute_url()
    except Exception:
        return None