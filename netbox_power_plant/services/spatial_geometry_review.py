from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from dcim.models import Site

from netbox_power_plant.choices import (
    PlantExtractionMethodChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import PhysicalSpace, PlantProvenance, SpatialFrame


VISUAL_GEOMETRY_SOURCE = "operator_visual_review"
VISUAL_GEOMETRY_REVIEW_STATE = "operator_review_required"
VISUAL_GEOMETRY_CORRECTED_STATE = "operator_corrected"
VISUAL_GEOMETRY_APPROVED_STATE = "approved"


@dataclass(frozen=True)
class SpaceGeometryUpdateResult:
    space: PhysicalSpace
    provenance: PlantProvenance
    original_geometry: dict
    updated_geometry: dict
    changed: bool


@dataclass(frozen=True)
class SpaceGeometryApprovalResult:
    space: PhysicalSpace
    provenance: PlantProvenance | None
    approved: bool


def update_physical_space_geometry_from_visual_review(
    space_id,
    *,
    x,
    y,
    width,
    depth,
    reviewer=None,
    notes="",
    site=None,
    spatial_frame=None,
) -> SpaceGeometryUpdateResult:
    """Save a y-up visual geometry correction for a PhysicalSpace boundary."""

    with transaction.atomic():
        space = (
            PhysicalSpace.objects
            .select_for_update()
            .get(pk=space_id)
        )
        _validate_scope(space, site=site, spatial_frame=spatial_frame)

        frame = space.spatial_frame
        if frame is None:
            raise ValueError("The selected space is not attached to a spatial frame.")

        x = _quantize(_decimal(x))
        y = _quantize(_decimal(y))
        width = _quantize(_decimal(width))
        depth = _quantize(_decimal(depth))
        _validate_geometry(frame, x=x, y=y, width=width, depth=depth)

        reviewed_at = timezone.now()
        reviewer_name = _reviewer_name(reviewer)
        original_geometry = dict(space.boundary_geometry or {})
        updated_geometry = _rectangle_boundary(
            x=x,
            y=y,
            width=width,
            depth=depth,
            original_geometry=original_geometry,
        )
        changed = original_geometry != updated_geometry

        metadata = _updated_space_metadata(
            space.metadata,
            original_geometry=original_geometry,
            updated_geometry=updated_geometry,
            reviewed_at=reviewed_at,
            reviewer_name=reviewer_name,
            notes=notes,
        )
        space.boundary_geometry = updated_geometry
        space.confidence = SpatialConfidenceChoices.CONFIDENCE_DERIVED
        space.metadata = metadata
        space.full_clean()
        space.save()

        provenance = _upsert_visual_geometry_provenance(
            space,
            original_geometry=original_geometry,
            updated_geometry=updated_geometry,
            reviewed_at=reviewed_at,
            reviewer_name=reviewer_name,
            notes=notes,
        )

    return SpaceGeometryUpdateResult(
        space=space,
        provenance=provenance,
        original_geometry=original_geometry,
        updated_geometry=updated_geometry,
        changed=changed,
    )


def approve_visual_geometry_correction(
    space_id,
    *,
    reviewer=None,
    notes="",
    site=None,
    spatial_frame=None,
) -> SpaceGeometryApprovalResult:
    """Approve an operator-corrected y-up PhysicalSpace boundary."""

    with transaction.atomic():
        space = (
            PhysicalSpace.objects
            .select_for_update()
            .get(pk=space_id)
        )
        _validate_scope(space, site=site, spatial_frame=spatial_frame)

        metadata = dict(space.metadata or {})
        if metadata.get("geometry_review_state") != VISUAL_GEOMETRY_CORRECTED_STATE:
            raise ValueError("The selected space does not have a visual geometry correction pending approval.")

        approved_at = timezone.now()
        reviewer_name = _reviewer_name(reviewer)
        approval_event = {
            "approved_by": reviewer_name,
            "approved_at": approved_at.isoformat(),
            "method": "visual_spatial_review",
            "notes": notes or "",
            "geometry": dict(space.boundary_geometry or {}),
        }
        approval_history = list(metadata.get("visual_geometry_approval_history") or ())
        approval_history.append(approval_event)
        metadata.update(
            {
                "review_state": VISUAL_GEOMETRY_APPROVED_STATE,
                "boundary_status": VISUAL_GEOMETRY_APPROVED_STATE,
                "geometry_review_state": VISUAL_GEOMETRY_APPROVED_STATE,
                "geometry_review_approved_by": reviewer_name,
                "geometry_review_approved_at": approved_at.isoformat(),
                "geometry_review_approval_notes": notes or "",
                "boundary_approved_by": reviewer_name,
                "boundary_approved_at": approved_at.isoformat(),
                "boundary_review_method": "visual_spatial_review",
                "boundary_review_notes": notes or "",
                "visual_geometry_approval_history": approval_history[-25:],
            }
        )

        space.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
        space.metadata = metadata
        space.full_clean()
        space.save()

        object_type = ContentType.objects.get_for_model(PhysicalSpace, for_concrete_model=False)
        provenance = _preferred_provenance(space, object_type)
        if provenance is not None:
            _approve_visual_geometry_provenance(
                provenance,
                approved_at=approved_at,
                reviewer_name=reviewer_name,
                notes=notes,
                approval_event=approval_event,
            )

    return SpaceGeometryApprovalResult(
        space=space,
        provenance=provenance,
        approved=True,
    )


def _validate_scope(space, *, site=None, spatial_frame=None):
    if site is not None:
        site_id = site.pk if isinstance(site, Site) else site
        if str(space.site_id) != str(site_id):
            raise ValueError("The selected space does not belong to the current site.")

    if spatial_frame is not None:
        frame_id = spatial_frame.pk if isinstance(spatial_frame, SpatialFrame) else spatial_frame
        if str(space.spatial_frame_id) != str(frame_id):
            raise ValueError("The selected space does not belong to the current spatial frame.")


def _validate_geometry(frame, *, x, y, width, depth):
    if x < 0 or y < 0:
        raise ValueError("Space geometry must use non-negative x/y coordinates.")
    if width <= 0 or depth <= 0:
        raise ValueError("Space geometry width and depth must be greater than zero.")

    frame_width = _decimal(frame.width)
    frame_height = _decimal(frame.height)
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("The selected spatial frame has no usable width or height.")
    if x + width > frame_width:
        raise ValueError("Space geometry must fit inside the spatial frame width.")
    if y + depth > frame_height:
        raise ValueError("Space geometry must fit inside the spatial frame height.")


def _rectangle_boundary(*, x, y, width, depth, original_geometry):
    boundary = dict(original_geometry or {})
    original_source = boundary.get("coordinate_source", "")
    boundary.update(
        {
            "type": "rectangle",
            "anchor": SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
            "x": _decimal_string(x),
            "y": _decimal_string(y),
            "width": _decimal_string(width),
            "depth": _decimal_string(depth),
            "x_min": _decimal_string(x),
            "x_max": _decimal_string(x + width),
            "y_min": _decimal_string(y),
            "y_max": _decimal_string(y + depth),
            "coordinate_source": VISUAL_GEOMETRY_SOURCE,
        }
    )
    if original_source and original_source != VISUAL_GEOMETRY_SOURCE:
        boundary["source_coordinate_source"] = original_source
    return boundary


def _updated_space_metadata(metadata, *, original_geometry, updated_geometry, reviewed_at, reviewer_name, notes):
    updated = dict(metadata or {})
    event = _geometry_event(
        original_geometry=original_geometry,
        updated_geometry=updated_geometry,
        reviewed_at=reviewed_at,
        reviewer_name=reviewer_name,
        notes=notes,
    )
    history = list(updated.get("visual_geometry_review_history") or ())
    history.append(event)
    updated.update(
        {
            "review_state": VISUAL_GEOMETRY_REVIEW_STATE,
            "boundary_status": VISUAL_GEOMETRY_REVIEW_STATE,
            "geometry_review_state": VISUAL_GEOMETRY_CORRECTED_STATE,
            "geometry_review_method": "visual_spatial_review",
            "geometry_reviewed_by": reviewer_name,
            "geometry_reviewed_at": reviewed_at.isoformat(),
            "geometry_review_notes": notes or "",
            "visual_geometry_review_history": history[-25:],
        }
    )
    return updated


def _upsert_visual_geometry_provenance(
    space,
    *,
    original_geometry,
    updated_geometry,
    reviewed_at,
    reviewer_name,
    notes,
):
    object_type = ContentType.objects.get_for_model(PhysicalSpace, for_concrete_model=False)
    provenance = _preferred_provenance(space, object_type)
    created = provenance is None
    if provenance is None:
        provenance = PlantProvenance(
            slug=f"{space.slug[:68]}-{space.pk}-visual-geometry-review"[:100],
            assigned_object_type=object_type,
            assigned_object_id=space.pk,
            extraction_method=PlantExtractionMethodChoices.METHOD_MANUAL,
            source_ref="operator:visual-geometry-review",
        )

    metadata = dict(provenance.metadata or {})
    event = _geometry_event(
        original_geometry=original_geometry,
        updated_geometry=updated_geometry,
        reviewed_at=reviewed_at,
        reviewer_name=reviewer_name,
        notes=notes,
    )
    history = list(metadata.get("visual_geometry_review_history") or ())
    history.append(event)
    metadata.update(
        {
            "review_state": VISUAL_GEOMETRY_REVIEW_STATE,
            "boundary_status": VISUAL_GEOMETRY_REVIEW_STATE,
            "geometry_review_state": VISUAL_GEOMETRY_CORRECTED_STATE,
            "geometry_review_method": "visual_spatial_review",
            "visual_geometry_review_history": history[-25:],
            "latest_visual_geometry_review": event,
        }
    )

    provenance.name = (
        provenance.name
        or f"Physical Space: {space.name} Visual Geometry Review"
    )[:100]
    provenance.assigned_object_type = object_type
    provenance.assigned_object_id = space.pk
    provenance.confidence = SpatialConfidenceChoices.CONFIDENCE_DERIVED
    provenance.is_authoritative = False
    provenance.extracted_at = reviewed_at
    provenance.metadata = metadata
    provenance.full_clean()
    provenance.save()
    return provenance


def _approve_visual_geometry_provenance(provenance, *, approved_at, reviewer_name, notes, approval_event):
    metadata = dict(provenance.metadata or {})
    approval_history = list(metadata.get("visual_geometry_approval_history") or ())
    approval_history.append(approval_event)
    metadata.update(
        {
            "review_state": VISUAL_GEOMETRY_APPROVED_STATE,
            "boundary_status": VISUAL_GEOMETRY_APPROVED_STATE,
            "geometry_review_state": VISUAL_GEOMETRY_APPROVED_STATE,
            "geometry_review_approved_by": reviewer_name,
            "geometry_review_approved_at": approved_at.isoformat(),
            "geometry_review_approval_notes": notes or "",
            "boundary_approved_by": reviewer_name,
            "boundary_approved_at": approved_at.isoformat(),
            "boundary_review_method": "visual_spatial_review",
            "boundary_review_notes": notes or "",
            "visual_geometry_approval_history": approval_history[-25:],
            "latest_visual_geometry_approval": approval_event,
        }
    )
    provenance.confidence = SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
    provenance.is_authoritative = True
    provenance.metadata = metadata
    provenance.full_clean()
    provenance.save()


def _preferred_provenance(space, object_type):
    queryset = PlantProvenance.objects.filter(
        assigned_object_type=object_type,
        assigned_object_id=space.pk,
    )
    return (
        queryset.filter(source_ref__startswith="madison:cad:detailed-space:")
        .order_by("-is_authoritative", "pk")
        .first()
        or queryset.order_by("-is_authoritative", "pk").first()
    )


def _geometry_event(*, original_geometry, updated_geometry, reviewed_at, reviewer_name, notes):
    return {
        "reviewed_by": reviewer_name,
        "reviewed_at": reviewed_at.isoformat(),
        "method": "visual_spatial_review",
        "notes": notes or "",
        "original_geometry": dict(original_geometry or {}),
        "updated_geometry": dict(updated_geometry or {}),
    }


def _reviewer_name(reviewer):
    if reviewer is None:
        return ""
    username = getattr(reviewer, "get_username", None)
    if callable(username):
        return username()
    return str(reviewer)


def _decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Invalid decimal value: {value!r}") from None


def _quantize(value):
    return Decimal(value).quantize(Decimal("0.001"))


def _decimal_string(value):
    return f"{_quantize(value):f}"
