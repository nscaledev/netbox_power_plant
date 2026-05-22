from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalSpaceKindChoices,
    PlantExtractionMethodChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
    SpatialPlacementKindChoices,
)
from netbox_power_plant.models import (
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_cad_materialization import (
    MADISON_CAD_CURRENT_BUILDING_PLACEMENT_KEY,
    MADISON_CAD_CURRENT_BUILDING_SPACE_KEY,
    MADISON_CAD_SITE_FRAME_KEY,
    MADISON_CAD_SITE_SPACE_KEY,
    MADISON_CAD_SOURCE_DOCUMENT_KEY,
    madison_cad_object_slug,
)


MADISON_CAD_FIRST_FLOOR_SPACE_KEY = "madison-current-building-first-floor"
MADISON_CAD_DATA_HALL_1_SPACE_KEY = "madison-data-hall-1-candidate-zone"
MADISON_CAD_DATA_HALL_2_SPACE_KEY = "madison-data-hall-2-candidate-zone"
MADISON_CAD_GENERATOR_YARD_SPACE_KEY = "madison-generator-yard-candidate-zone"
MADISON_CAD_ELECTRICAL_PLANT_SPACE_KEY = "madison-electrical-plant-candidate-zone"


@dataclass(frozen=True)
class MadisonCadApprovalOverrides:
    source_units: str = ""
    site_width: Decimal | None = None
    site_height: Decimal | None = None
    building_origin_x: Decimal | None = None
    building_origin_y: Decimal | None = None
    building_width: Decimal | None = None
    building_height: Decimal | None = None
    notes: str = ""


@dataclass(frozen=True)
class MadisonCadApprovalResult:
    site: Site
    source_document: PlantSourceDocument
    site_frame: SpatialFrame
    site_space: PhysicalSpace
    current_building_space: PhysicalSpace
    current_building_placement: SpatialPlacement
    decomposition_spaces: tuple[PhysicalSpace, ...]
    provenance_records: tuple[PlantProvenance, ...]
    approved_at: object
    approved_by: str


def approve_madison_cad_underlay(
    site,
    *,
    overrides: MadisonCadApprovalOverrides | None = None,
    reviewer=None,
) -> MadisonCadApprovalResult:
    resolved_site = _resolve_site(site)
    approved_at = timezone.now()
    approved_by = _reviewer_name(reviewer)
    values = _approval_values(resolved_site, overrides or MadisonCadApprovalOverrides())

    with transaction.atomic():
        _apply_source_document_approval(values, approved_at=approved_at, approved_by=approved_by)
        _apply_site_frame_approval(values, approved_at=approved_at, approved_by=approved_by)
        _apply_site_space_approval(values, approved_at=approved_at, approved_by=approved_by)
        _apply_current_building_approval(values, approved_at=approved_at, approved_by=approved_by)
        decomposition_spaces = _seed_decomposition_spaces(values, approved_at=approved_at, approved_by=approved_by)
        provenance_records = _promote_provenance(values, decomposition_spaces, approved_at=approved_at, approved_by=approved_by)

    return MadisonCadApprovalResult(
        site=resolved_site,
        source_document=values.source_document,
        site_frame=values.site_frame,
        site_space=values.site_space,
        current_building_space=values.current_building_space,
        current_building_placement=values.current_building_placement,
        decomposition_spaces=tuple(decomposition_spaces),
        provenance_records=tuple(provenance_records),
        approved_at=approved_at,
        approved_by=approved_by,
    )


@dataclass(frozen=True)
class _ApprovalObjectsAndValues:
    site: Site
    source_document: PlantSourceDocument
    site_frame: SpatialFrame
    site_space: PhysicalSpace
    current_building_space: PhysicalSpace
    current_building_placement: SpatialPlacement
    source_units: str
    site_width: Decimal
    site_height: Decimal
    building_origin_x: Decimal
    building_origin_y: Decimal
    building_width: Decimal
    building_height: Decimal
    notes: str


def _approval_values(site, overrides):
    source_document = _get_required(
        PlantSourceDocument,
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SOURCE_DOCUMENT_KEY),
    )
    site_frame = _get_required(
        SpatialFrame,
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SITE_FRAME_KEY),
    )
    site_space = _get_required(
        PhysicalSpace,
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SITE_SPACE_KEY),
    )
    current_building_space = _get_required(
        PhysicalSpace,
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_SPACE_KEY),
    )
    current_building_placement = _get_required(
        SpatialPlacement,
        spatial_frame__site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_PLACEMENT_KEY),
    )

    source_units = overrides.source_units or source_document.metadata.get("source_units", "")
    return _ApprovalObjectsAndValues(
        site=site,
        source_document=source_document,
        site_frame=site_frame,
        site_space=site_space,
        current_building_space=current_building_space,
        current_building_placement=current_building_placement,
        source_units=source_units,
        site_width=_first_decimal(overrides.site_width, site_frame.width),
        site_height=_first_decimal(overrides.site_height, site_frame.height),
        building_origin_x=_first_decimal(overrides.building_origin_x, current_building_placement.x),
        building_origin_y=_first_decimal(overrides.building_origin_y, current_building_placement.y),
        building_width=_first_decimal(overrides.building_width, current_building_placement.width),
        building_height=_first_decimal(overrides.building_height, current_building_placement.depth),
        notes=overrides.notes,
    )


def _apply_source_document_approval(values, *, approved_at, approved_by):
    metadata = _approved_metadata(
        values.source_document.metadata,
        values=values,
        approved_at=approved_at,
        approved_by=approved_by,
    )
    metadata["calibration_status"] = "approved"
    metadata["source_units"] = values.source_units
    values.source_document.metadata = metadata
    values.source_document.full_clean()
    values.source_document.save()


def _apply_site_frame_approval(values, *, approved_at, approved_by):
    values.site_frame.width = values.site_width
    values.site_frame.height = values.site_height
    values.site_frame.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
    values.site_frame.metadata = _approved_metadata(
        values.site_frame.metadata,
        values=values,
        approved_at=approved_at,
        approved_by=approved_by,
    )
    values.site_frame.full_clean()
    values.site_frame.save()


def _apply_site_space_approval(values, *, approved_at, approved_by):
    values.site_space.boundary_geometry = _rectangle_boundary(
        Decimal("0.000"),
        Decimal("0.000"),
        values.site_width,
        values.site_height,
        coordinate_source="operator_approved_madison_cad_coordinate_plane",
    )
    values.site_space.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
    values.site_space.metadata = _approved_metadata(
        values.site_space.metadata,
        values=values,
        approved_at=approved_at,
        approved_by=approved_by,
    )
    values.site_space.full_clean()
    values.site_space.save()


def _apply_current_building_approval(values, *, approved_at, approved_by):
    boundary = _rectangle_boundary(
        values.building_origin_x,
        values.building_origin_y,
        values.building_width,
        values.building_height,
        coordinate_source="operator_approved_madison_cad_current_building",
    )
    values.current_building_space.boundary_geometry = boundary
    values.current_building_space.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
    values.current_building_space.metadata = _approved_metadata(
        values.current_building_space.metadata,
        values=values,
        approved_at=approved_at,
        approved_by=approved_by,
    )
    values.current_building_space.full_clean()
    values.current_building_space.save()

    values.current_building_placement.x = values.building_origin_x
    values.current_building_placement.y = values.building_origin_y
    values.current_building_placement.width = values.building_width
    values.current_building_placement.depth = values.building_height
    values.current_building_placement.anchor = SpatialAnchorChoices.ANCHOR_LOWER_LEFT
    values.current_building_placement.placement_kind = SpatialPlacementKindChoices.KIND_PHYSICAL
    values.current_building_placement.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
    values.current_building_placement.metadata = _approved_metadata(
        values.current_building_placement.metadata,
        values=values,
        approved_at=approved_at,
        approved_by=approved_by,
    )
    values.current_building_placement.full_clean()
    values.current_building_placement.save()


def _seed_decomposition_spaces(values, *, approved_at, approved_by):
    first_floor = _upsert_space(
        values,
        MADISON_CAD_FIRST_FLOOR_SPACE_KEY,
        name=f"{values.site.name} Madison First Floor",
        parent_space=values.current_building_space,
        space_kind=PhysicalSpaceKindChoices.KIND_FLOOR,
        boundary_geometry=_rectangle_boundary(
            values.building_origin_x,
            values.building_origin_y,
            values.building_width,
            values.building_height,
            coordinate_source="operator_approved_madison_cad_current_building",
        ),
        confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        source_ref="madison:cad:first-floor",
        metadata={"decomposition_role": "first_floor"},
        approved_at=approved_at,
        approved_by=approved_by,
    )
    data_hall_1 = _upsert_space(
        values,
        MADISON_CAD_DATA_HALL_1_SPACE_KEY,
        name=f"{values.site.name} Madison Data Hall 1 Candidate Zone",
        parent_space=first_floor,
        space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        source_ref="madison:cad:data-hall-1-candidate",
        metadata={"decomposition_role": "data_hall", "data_hall": "1", "boundary_status": "pending_detailed_cad_extraction"},
        approved_at=approved_at,
        approved_by=approved_by,
    )
    data_hall_2 = _upsert_space(
        values,
        MADISON_CAD_DATA_HALL_2_SPACE_KEY,
        name=f"{values.site.name} Madison Data Hall 2 Candidate Zone",
        parent_space=first_floor,
        space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        source_ref="madison:cad:data-hall-2-candidate",
        metadata={"decomposition_role": "data_hall", "data_hall": "2", "boundary_status": "pending_detailed_cad_extraction"},
        approved_at=approved_at,
        approved_by=approved_by,
    )
    generator_yard = _upsert_space(
        values,
        MADISON_CAD_GENERATOR_YARD_SPACE_KEY,
        name=f"{values.site.name} Madison Generator Yard Candidate Zone",
        parent_space=values.site_space,
        space_kind=PhysicalSpaceKindChoices.KIND_YARD,
        confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        source_ref="madison:cad:generator-yard-candidate",
        metadata={"decomposition_role": "generator_yard", "boundary_status": "pending_detailed_cad_extraction"},
        approved_at=approved_at,
        approved_by=approved_by,
    )
    electrical_plant = _upsert_space(
        values,
        MADISON_CAD_ELECTRICAL_PLANT_SPACE_KEY,
        name=f"{values.site.name} Madison Electrical Plant Candidate Zone",
        parent_space=first_floor,
        space_kind=PhysicalSpaceKindChoices.KIND_ELECTRICAL_ROOM,
        confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        source_ref="madison:cad:electrical-plant-candidate",
        metadata={"decomposition_role": "electrical_plant", "boundary_status": "pending_detailed_cad_extraction"},
        approved_at=approved_at,
        approved_by=approved_by,
    )
    return (first_floor, data_hall_1, data_hall_2, generator_yard, electrical_plant)


def _upsert_space(
    values,
    key,
    *,
    name,
    parent_space,
    space_kind,
    source_ref,
    metadata,
    approved_at,
    approved_by,
    boundary_geometry=None,
    confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
):
    space, _created = PhysicalSpace.objects.get_or_create(
        slug=madison_cad_object_slug(values.site, key),
        defaults={
            "name": name[:100],
            "site": values.site,
        },
    )
    space.name = name[:100]
    space.site = values.site
    space.location = None
    space.spatial_frame = values.site_frame
    space.parent_space = parent_space
    space.space_kind = space_kind
    space.boundary_geometry = boundary_geometry or {}
    space.source_document = values.source_document.name
    space.source_ref = source_ref
    space.confidence = confidence
    space.metadata = _approved_metadata(
        {"source_system": "madison_cad", **metadata},
        values=values,
        approved_at=approved_at,
        approved_by=approved_by,
    )
    space.full_clean()
    space.save()
    return space


def _promote_provenance(values, decomposition_spaces, *, approved_at, approved_by):
    records = []
    assigned_objects = (
        values.site_frame,
        values.site_space,
        values.current_building_space,
        values.current_building_placement,
        *decomposition_spaces,
    )
    for assigned_object in assigned_objects:
        object_type = ContentType.objects.get_for_model(type(assigned_object), for_concrete_model=False)
        slug = f"{assigned_object.slug}-madison-cad-provenance"[:100]
        record, _created = PlantProvenance.objects.get_or_create(
            slug=slug,
            defaults={
                "name": f"{assigned_object._meta.verbose_name.title()}: {assigned_object.name} Madison CAD Provenance"[:100],
                "assigned_object_type": object_type,
                "assigned_object_id": assigned_object.pk,
            },
        )
        record.assigned_object_type = object_type
        record.assigned_object_id = assigned_object.pk
        record.source_document = values.source_document
        record.source_sheet = None
        record.source_layer = None
        record.extraction_method = PlantExtractionMethodChoices.METHOD_CAD_EXPORT
        record.source_ref = "madison:cad:underlay"
        record.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
        record.is_authoritative = True
        record.metadata = _approved_metadata(
            record.metadata,
            values=values,
            approved_at=approved_at,
            approved_by=approved_by,
        )
        record.full_clean()
        record.save()
        records.append(record)
    return tuple(records)


def _approved_metadata(metadata, *, values, approved_at, approved_by):
    updated = dict(metadata or {})
    updated.update(
        {
            "review_state": "approved",
            "approved_by": approved_by,
            "approved_at": approved_at.isoformat(),
            "approved_source_units": values.source_units,
            "approved_site_width": str(values.site_width),
            "approved_site_height": str(values.site_height),
            "approved_current_building_origin_x": str(values.building_origin_x),
            "approved_current_building_origin_y": str(values.building_origin_y),
            "approved_current_building_width": str(values.building_width),
            "approved_current_building_height": str(values.building_height),
        }
    )
    if values.notes:
        updated["approval_notes"] = values.notes
    return updated


def _rectangle_boundary(x, y, width, height, *, coordinate_source):
    return {
        "type": "rectangle",
        "anchor": SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
        "x": str(x),
        "y": str(y),
        "width": str(width),
        "depth": str(height),
        "x_min": str(x),
        "x_max": str(x + width),
        "y_min": str(y),
        "y_max": str(y + height),
        "coordinate_source": coordinate_source,
    }


def _get_required(model, **kwargs):
    instance = model.objects.filter(**kwargs).first()
    if instance is None:
        raise ValueError(f"Required Madison CAD underlay object is missing: {model.__name__}.")
    return instance


def _resolve_site(site):
    if isinstance(site, Site):
        return site
    resolved = Site.objects.filter(slug=str(site)).first()
    if resolved is None:
        raise ValueError(f"No site found for slug '{site}'.")
    return resolved


def _first_decimal(*values):
    for value in values:
        if value not in (None, ""):
            return Decimal(str(value)).quantize(Decimal("0.001"))
    return Decimal("0.000")


def _reviewer_name(reviewer):
    if reviewer is None:
        return ""
    username = getattr(reviewer, "get_username", None)
    if callable(username):
        return username()
    return str(reviewer)
