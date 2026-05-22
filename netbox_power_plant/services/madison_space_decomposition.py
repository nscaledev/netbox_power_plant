from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from importlib import import_module
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalSpaceKindChoices,
    PlantExtractionMethodChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
)
from netbox_power_plant.services.madison_cad_approval import MADISON_CAD_FIRST_FLOOR_SPACE_KEY
from netbox_power_plant.services.madison_cad_materialization import (
    MADISON_CAD_CURRENT_BUILDING_SPACE_KEY,
    MADISON_CAD_SITE_FRAME_KEY,
    MADISON_CAD_SOURCE_DOCUMENT_KEY,
    madison_cad_object_slug,
)


MADISON_DETAILED_SPACE_PREFIX = "madison-detailed-space"
MADISON_DETAILED_SPACE_REVIEW_STATE = "operator_review_required"
MADISON_DETAILED_SPACE_APPROVED_STATE = "approved"


@dataclass(frozen=True)
class MadisonDetailedSpaceSpec:
    key: str
    room_label: str
    display_name: str
    space_kind: str
    source_sheet_numbers: tuple[str, ...]
    x_min_ratio: Decimal
    y_min_ratio: Decimal
    x_max_ratio: Decimal
    y_max_ratio: Decimal
    notes: str = ""

    @property
    def slug_key(self):
        return f"{MADISON_DETAILED_SPACE_PREFIX}-{self.key}"


@dataclass(frozen=True)
class MadisonDetailedSpaceCandidate:
    spec: MadisonDetailedSpaceSpec
    slug: str
    name: str
    boundary_geometry: dict
    source_bounds: dict
    marker: dict | None = None
    space: PhysicalSpace | None = None

    @property
    def materialized(self):
        return self.space is not None

    @property
    def review_state(self):
        if self.space is None:
            return "not_materialized"
        return (self.space.metadata or {}).get("review_state", "")

    @property
    def boundary_status(self):
        if self.space is None:
            return ""
        return (self.space.metadata or {}).get("boundary_status", "")

    @property
    def space_kind_label(self):
        return dict(PhysicalSpaceKindChoices.CHOICES).get(self.spec.space_kind, _humanize(self.spec.space_kind))

    @property
    def boundary_status_label(self):
        if not self.materialized:
            return "Not materialized"
        return _humanize(self.boundary_status or "materialized")


@dataclass(frozen=True)
class MadisonDetailedSpaceDecompositionSummary:
    site: Site | None
    source_document: PlantSourceDocument | None
    site_frame: SpatialFrame | None
    first_floor_space: PhysicalSpace | None
    blocked_reasons: tuple[str, ...]
    candidates: tuple[MadisonDetailedSpaceCandidate, ...] = ()
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0

    @property
    def ready(self):
        return not self.blocked_reasons

    @property
    def candidate_count(self):
        return len(self.candidates)

    @property
    def materialized_count(self):
        return len([candidate for candidate in self.candidates if candidate.materialized])

    @property
    def pending_review_count(self):
        return len(
            [
                candidate
                for candidate in self.candidates
                if candidate.review_state == MADISON_DETAILED_SPACE_REVIEW_STATE
            ]
        )

    @property
    def approved_count(self):
        return len(
            [
                candidate
                for candidate in self.candidates
                if candidate.boundary_status == MADISON_DETAILED_SPACE_APPROVED_STATE
            ]
        )

    @property
    def ready_for_boundary_approval(self):
        return self.ready and self.candidate_count > 0 and self.materialized_count == self.candidate_count


@dataclass(frozen=True)
class _ApprovedUnderlay:
    site: Site
    source_document: PlantSourceDocument
    site_frame: SpatialFrame
    current_building_space: PhysicalSpace
    first_floor_space: PhysicalSpace
    coordinate_source_bounds: dict
    current_building_source_bounds: dict
    scale_x: Decimal
    scale_y: Decimal


MADISON_DETAILED_SPACE_SPECS = (
    MadisonDetailedSpaceSpec(
        key="b1208-upper-gallery",
        room_label="B1208",
        display_name="Data Hall 2 Upper Gallery",
        space_kind=PhysicalSpaceKindChoices.KIND_GALLERY,
        source_sheet_numbers=("E3-1B",),
        x_min_ratio=Decimal("0.0512"),
        y_min_ratio=Decimal("0.6175"),
        x_max_ratio=Decimal("0.2976"),
        y_max_ratio=Decimal("0.6690"),
        notes="Upper gallery serving Data Hall 2.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1209-data-hall-2a",
        room_label="B1209",
        display_name="Data Hall 2A",
        space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        source_sheet_numbers=("E3-1B",),
        x_min_ratio=Decimal("0.0512"),
        y_min_ratio=Decimal("0.5440"),
        x_max_ratio=Decimal("0.2976"),
        y_max_ratio=Decimal("0.6175"),
        notes="Rows A/B, E/F, and I/J per Madison layout materials.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1210-middle-gallery",
        room_label="B1210",
        display_name="Data Hall 2 Middle Gallery",
        space_kind=PhysicalSpaceKindChoices.KIND_GALLERY,
        source_sheet_numbers=("E3-1B",),
        x_min_ratio=Decimal("0.0512"),
        y_min_ratio=Decimal("0.5276"),
        x_max_ratio=Decimal("0.2976"),
        y_max_ratio=Decimal("0.5440"),
        notes="Interstitial gallery between Data Hall 2A and Data Hall 2B.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1211-data-hall-2b",
        room_label="B1211",
        display_name="Data Hall 2B",
        space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        source_sheet_numbers=("E3-1B",),
        x_min_ratio=Decimal("0.0512"),
        y_min_ratio=Decimal("0.4574"),
        x_max_ratio=Decimal("0.2976"),
        y_max_ratio=Decimal("0.5276"),
        notes="Rows C/D, G/H, and K/L per Madison layout materials.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1212-lower-gallery",
        room_label="B1212",
        display_name="Data Hall 2 Lower Gallery",
        space_kind=PhysicalSpaceKindChoices.KIND_GALLERY,
        source_sheet_numbers=("E3-1B",),
        x_min_ratio=Decimal("0.0512"),
        y_min_ratio=Decimal("0.4206"),
        x_max_ratio=Decimal("0.2976"),
        y_max_ratio=Decimal("0.4574"),
        notes="Lower gallery serving Data Hall 2.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1108-upper-gallery",
        room_label="B1108",
        display_name="Data Hall 1 Upper Gallery",
        space_kind=PhysicalSpaceKindChoices.KIND_GALLERY,
        source_sheet_numbers=("E3-1A",),
        x_min_ratio=Decimal("0.2976"),
        y_min_ratio=Decimal("0.6175"),
        x_max_ratio=Decimal("0.5947"),
        y_max_ratio=Decimal("0.6690"),
        notes="Upper gallery serving Data Hall 1.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1109-data-hall-1a",
        room_label="B1109",
        display_name="Data Hall 1A",
        space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        source_sheet_numbers=("E3-1A",),
        x_min_ratio=Decimal("0.2976"),
        y_min_ratio=Decimal("0.5440"),
        x_max_ratio=Decimal("0.5947"),
        y_max_ratio=Decimal("0.6175"),
        notes="Rows M/N, Q/R, and U/V per Madison layout materials.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1110-middle-gallery",
        room_label="B1110",
        display_name="Data Hall 1 Middle Gallery",
        space_kind=PhysicalSpaceKindChoices.KIND_GALLERY,
        source_sheet_numbers=("E3-1A",),
        x_min_ratio=Decimal("0.2976"),
        y_min_ratio=Decimal("0.5276"),
        x_max_ratio=Decimal("0.5947"),
        y_max_ratio=Decimal("0.5440"),
        notes="Interstitial gallery between Data Hall 1A and Data Hall 1B.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1111-data-hall-1b",
        room_label="B1111",
        display_name="Data Hall 1B",
        space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        source_sheet_numbers=("E3-1A",),
        x_min_ratio=Decimal("0.2976"),
        y_min_ratio=Decimal("0.4574"),
        x_max_ratio=Decimal("0.5947"),
        y_max_ratio=Decimal("0.5276"),
        notes="Rows O/P, S/T, and W/X per Madison layout materials.",
    ),
    MadisonDetailedSpaceSpec(
        key="b1112-lower-gallery",
        room_label="B1112",
        display_name="Data Hall 1 Lower Gallery",
        space_kind=PhysicalSpaceKindChoices.KIND_GALLERY,
        source_sheet_numbers=("E3-1A",),
        x_min_ratio=Decimal("0.2976"),
        y_min_ratio=Decimal("0.4206"),
        x_max_ratio=Decimal("0.5947"),
        y_max_ratio=Decimal("0.4574"),
        notes="Lower gallery serving Data Hall 1.",
    ),
)


def build_madison_detailed_space_decomposition_summary(
    site,
) -> MadisonDetailedSpaceDecompositionSummary:
    resolved_site = _resolve_site(site)
    if resolved_site is None:
        return MadisonDetailedSpaceDecompositionSummary(
            site=None,
            source_document=None,
            site_frame=None,
            first_floor_space=None,
            blocked_reasons=("Madison site does not exist.",),
        )

    underlay, blocked = _approved_underlay(resolved_site)
    if underlay is None:
        return MadisonDetailedSpaceDecompositionSummary(
            site=resolved_site,
            source_document=None,
            site_frame=None,
            first_floor_space=None,
            blocked_reasons=blocked,
        )

    candidates = _build_candidates(underlay, markers={})
    existing = PhysicalSpace.objects.filter(
        site=resolved_site,
        slug__in=[candidate.slug for candidate in candidates],
    ).in_bulk(field_name="slug")
    candidates = tuple(
        _with_existing_space(candidate, existing.get(candidate.slug))
        for candidate in candidates
    )
    return MadisonDetailedSpaceDecompositionSummary(
        site=resolved_site,
        source_document=underlay.source_document,
        site_frame=underlay.site_frame,
        first_floor_space=underlay.first_floor_space,
        blocked_reasons=(),
        candidates=candidates,
    )


def _with_existing_space(candidate, space):
    return MadisonDetailedSpaceCandidate(
        spec=candidate.spec,
        slug=candidate.slug,
        name=candidate.name,
        boundary_geometry=dict(space.boundary_geometry) if space is not None and space.boundary_geometry else candidate.boundary_geometry,
        source_bounds=candidate.source_bounds,
        marker=candidate.marker,
        space=space,
    )


def apply_madison_detailed_space_decomposition(
    site,
    *,
    reviewer=None,
) -> MadisonDetailedSpaceDecompositionSummary:
    resolved_site = _resolve_site(site)
    if resolved_site is None:
        raise ValueError(f"No site found for slug '{site}'.")

    underlay, blocked = _approved_underlay(resolved_site)
    if underlay is None:
        raise ValueError("Madison detailed spaces require an approved CAD site underlay: " + "; ".join(blocked))

    reviewer_name = _reviewer_name(reviewer)
    reviewed_at = timezone.now()
    markers = _extract_room_markers(underlay.source_document)

    created = updated = unchanged = 0
    spaces = {}
    with transaction.atomic():
        candidates = _build_candidates(underlay, markers=markers)
        for candidate in candidates:
            space, action = _upsert_space(
                underlay,
                candidate,
                reviewed_at=reviewed_at,
                reviewer_name=reviewer_name,
            )
            _upsert_provenance(
                underlay,
                candidate,
                space,
                reviewed_at=reviewed_at,
            )
            spaces[candidate.slug] = space
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                unchanged += 1

    candidates = tuple(
        MadisonDetailedSpaceCandidate(
            spec=candidate.spec,
            slug=candidate.slug,
            name=candidate.name,
            boundary_geometry=candidate.boundary_geometry,
            source_bounds=candidate.source_bounds,
            marker=candidate.marker,
            space=spaces.get(candidate.slug),
        )
        for candidate in _build_candidates(underlay, markers=markers)
    )
    return MadisonDetailedSpaceDecompositionSummary(
        site=resolved_site,
        source_document=underlay.source_document,
        site_frame=underlay.site_frame,
        first_floor_space=underlay.first_floor_space,
        blocked_reasons=(),
        candidates=candidates,
        created_count=created,
        updated_count=updated,
        unchanged_count=unchanged,
    )


def approve_madison_detailed_space_boundaries(
    site,
    *,
    reviewer=None,
    notes="",
) -> MadisonDetailedSpaceDecompositionSummary:
    resolved_site = _resolve_site(site)
    if resolved_site is None:
        raise ValueError(f"No site found for slug '{site}'.")

    summary = build_madison_detailed_space_decomposition_summary(resolved_site)
    if not summary.ready:
        raise ValueError("Madison detailed spaces are not ready for boundary approval: " + "; ".join(summary.blocked_reasons))
    if not summary.ready_for_boundary_approval:
        missing = summary.candidate_count - summary.materialized_count
        raise ValueError(
            f"Materialize all Madison detailed spaces before approving boundaries; {missing} remain unmaterialized."
        )

    reviewer_name = _reviewer_name(reviewer)
    approved_at = timezone.now()
    review_notes = str(notes or "").strip()
    updated = unchanged = 0

    with transaction.atomic():
        for candidate in summary.candidates:
            space = PhysicalSpace.objects.select_for_update().get(pk=candidate.space.pk)
            changed = _approve_space_boundary(
                space,
                reviewer_name=reviewer_name,
                approved_at=approved_at,
                notes=review_notes,
            )
            _approve_space_provenance(
                space,
                reviewer_name=reviewer_name,
                approved_at=approved_at,
                notes=review_notes,
            )
            if changed:
                updated += 1
            else:
                unchanged += 1

    return replace(
        build_madison_detailed_space_decomposition_summary(resolved_site),
        updated_count=updated,
        unchanged_count=unchanged,
    )


def _approved_underlay(site):
    blocked = []
    source_document = PlantSourceDocument.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SOURCE_DOCUMENT_KEY),
    ).first()
    if source_document is None:
        blocked.append("Approved Madison CAD source document is missing.")
    elif (source_document.metadata or {}).get("review_state") != "approved":
        blocked.append("Madison CAD source document has not been approved.")

    site_frame = SpatialFrame.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SITE_FRAME_KEY),
    ).first()
    if site_frame is None:
        blocked.append("Approved Madison CAD site frame is missing.")

    current_building_space = PhysicalSpace.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_SPACE_KEY),
    ).first()
    if current_building_space is None:
        blocked.append("Approved Madison current-building space is missing.")

    first_floor_space = PhysicalSpace.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_FIRST_FLOOR_SPACE_KEY),
    ).first()
    if first_floor_space is None:
        blocked.append("Approved Madison first-floor space is missing.")

    coordinate_bounds = (source_document.metadata or {}).get("coordinate_plane_bounds") if source_document else None
    current_building = (source_document.metadata or {}).get("current_building") if source_document else None
    current_building_bounds = (current_building or {}).get("source_bounds") if current_building else None
    if not coordinate_bounds:
        blocked.append("Approved Madison coordinate-plane source bounds are missing.")
    if not current_building_bounds:
        blocked.append("Approved Madison current-building source bounds are missing.")

    if blocked:
        return None, tuple(blocked)

    width = _decimal(coordinate_bounds["width"])
    height = _decimal(coordinate_bounds["height"])
    if width <= 0 or height <= 0 or site_frame.width is None or site_frame.height is None:
        return None, ("Approved Madison site frame does not have usable coordinate dimensions.",)

    return (
        _ApprovedUnderlay(
            site=site,
            source_document=source_document,
            site_frame=site_frame,
            current_building_space=current_building_space,
            first_floor_space=first_floor_space,
            coordinate_source_bounds=coordinate_bounds,
            current_building_source_bounds=current_building_bounds,
            scale_x=_decimal(site_frame.width) / width,
            scale_y=_decimal(site_frame.height) / height,
        ),
        (),
    )


def _build_candidates(underlay, *, markers):
    return tuple(_candidate_from_spec(underlay, spec, markers.get(spec.room_label)) for spec in MADISON_DETAILED_SPACE_SPECS)


def _candidate_from_spec(underlay, spec, marker):
    source_bounds = _source_bounds_from_spec(underlay.current_building_source_bounds, spec)
    x = _source_x_to_grid(underlay, source_bounds["min_x"])
    y = _source_y_to_grid(underlay, source_bounds["min_y"])
    width = _quantize((source_bounds["max_x"] - source_bounds["min_x"]) * underlay.scale_x)
    depth = _quantize((source_bounds["max_y"] - source_bounds["min_y"]) * underlay.scale_y)
    boundary = _rectangle_boundary(
        x,
        y,
        width,
        depth,
        coordinate_source="madison_cad_detailed_space_decomposition",
    )
    return MadisonDetailedSpaceCandidate(
        spec=spec,
        slug=madison_cad_object_slug(underlay.site, spec.slug_key),
        name=_name(f"{underlay.site.name} {spec.room_label} {spec.display_name}"),
        boundary_geometry=boundary,
        source_bounds={
            "min_x": _decimal_string(source_bounds["min_x"]),
            "min_y": _decimal_string(source_bounds["min_y"]),
            "max_x": _decimal_string(source_bounds["max_x"]),
            "max_y": _decimal_string(source_bounds["max_y"]),
            "width": _decimal_string(source_bounds["max_x"] - source_bounds["min_x"]),
            "height": _decimal_string(source_bounds["max_y"] - source_bounds["min_y"]),
        },
        marker=marker,
    )


def _source_bounds_from_spec(building_source_bounds, spec):
    min_x = _decimal(building_source_bounds["min_x"])
    min_y = _decimal(building_source_bounds["min_y"])
    width = _decimal(building_source_bounds["width"])
    height = _decimal(building_source_bounds["height"])
    return {
        "min_x": min_x + (width * spec.x_min_ratio),
        "max_x": min_x + (width * spec.x_max_ratio),
        "min_y": min_y + (height * spec.y_min_ratio),
        "max_y": min_y + (height * spec.y_max_ratio),
    }


def _source_x_to_grid(underlay, x):
    return _quantize((x - _decimal(underlay.coordinate_source_bounds["min_x"])) * underlay.scale_x)


def _source_y_to_grid(underlay, y):
    return _quantize((y - _decimal(underlay.coordinate_source_bounds["min_y"])) * underlay.scale_y)


def _upsert_space(underlay, candidate, *, reviewed_at, reviewer_name):
    spec = candidate.spec
    space = PhysicalSpace.objects.filter(slug=candidate.slug).first()
    created = space is None
    if space is None:
        space = PhysicalSpace(slug=candidate.slug)

    existing_metadata = dict(space.metadata or {})
    boundary_changed = created or space.boundary_geometry != candidate.boundary_geometry
    approval_is_still_valid = (
        not boundary_changed
        and existing_metadata.get("boundary_status") == MADISON_DETAILED_SPACE_APPROVED_STATE
    )
    metadata = dict(existing_metadata)
    metadata.update(
        {
            "source_system": "madison_cad",
            "decomposition_role": "detailed_space",
            "source_room_label": spec.room_label,
            "source_sheet_numbers": list(spec.source_sheet_numbers),
            "source_bounds": candidate.source_bounds,
            "source_marker": candidate.marker or {},
            "notes": spec.notes,
            "inference_method": (
                "Scaled Madison detailed space ratios within the operator-approved CAD current-building "
                "source bounds; source room labels are captured as supporting evidence when available."
            ),
        }
    )
    if approval_is_still_valid:
        metadata.update(
            {
                "review_state": MADISON_DETAILED_SPACE_APPROVED_STATE,
                "boundary_status": MADISON_DETAILED_SPACE_APPROVED_STATE,
            }
        )
    else:
        for approval_key in (
            "boundary_approved_by",
            "boundary_approved_at",
            "boundary_review_method",
            "boundary_review_notes",
        ):
            metadata.pop(approval_key, None)
        metadata.update(
            {
                "review_state": MADISON_DETAILED_SPACE_REVIEW_STATE,
                "boundary_status": MADISON_DETAILED_SPACE_REVIEW_STATE,
                "review_requested_by": reviewer_name,
                "review_requested_at": reviewed_at.isoformat(),
            }
        )

    confidence = (
        SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
        if approval_is_still_valid
        else SpatialConfidenceChoices.CONFIDENCE_DERIVED
    )
    defaults = {
        "name": candidate.name,
        "site": underlay.site,
        "location": None,
        "spatial_frame": underlay.site_frame,
        "parent_space": underlay.first_floor_space,
        "space_kind": spec.space_kind,
        "floor_label": "1",
        "boundary_geometry": candidate.boundary_geometry,
        "source_document": underlay.source_document.name,
        "source_ref": f"madison:cad:detailed-space:{spec.room_label.lower()}",
        "confidence": confidence,
        "metadata": metadata,
    }
    changed = _assign_changed(space, defaults, created=created)
    if changed:
        space.full_clean()
        space.save()
    if created:
        return space, "created"
    if changed:
        return space, "updated"
    return space, "unchanged"


def _upsert_provenance(underlay, candidate, space, *, reviewed_at):
    object_type = ContentType.objects.get_for_model(PhysicalSpace, for_concrete_model=False)
    source_sheet = _source_sheet(underlay.source_document, candidate.spec.source_sheet_numbers)
    source_layer = _source_layer(source_sheet)
    slug = f"{space.slug}-madison-detailed-space-provenance"[:100]
    provenance = PlantProvenance.objects.filter(slug=slug).first()
    created = provenance is None
    if provenance is None:
        provenance = PlantProvenance(slug=slug)
    space_metadata = space.metadata or {}
    review_state = space_metadata.get("review_state") or MADISON_DETAILED_SPACE_REVIEW_STATE
    boundary_status = space_metadata.get("boundary_status") or MADISON_DETAILED_SPACE_REVIEW_STATE
    is_approved = boundary_status == MADISON_DETAILED_SPACE_APPROVED_STATE
    provenance_metadata = {
        "source_system": "madison_cad",
        "review_state": review_state,
        "boundary_status": boundary_status,
        "source_room_label": candidate.spec.room_label,
        "source_sheet_numbers": list(candidate.spec.source_sheet_numbers),
    }
    for approval_key in (
        "boundary_approved_by",
        "boundary_approved_at",
        "boundary_review_method",
        "boundary_review_notes",
    ):
        if approval_key in space_metadata:
            provenance_metadata[approval_key] = space_metadata[approval_key]
    defaults = {
        "name": _name(f"Physical Space: {space.name} Madison Detailed Space Provenance"),
        "assigned_object_type": object_type,
        "assigned_object_id": space.pk,
        "source_document": underlay.source_document,
        "source_sheet": source_sheet,
        "source_layer": source_layer,
        "extraction_method": PlantExtractionMethodChoices.METHOD_CAD_EXPORT,
        "source_ref": f"madison:cad:detailed-space:{candidate.spec.room_label.lower()}",
        "confidence": (
            SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
            if is_approved
            else SpatialConfidenceChoices.CONFIDENCE_DERIVED
        ),
        "is_authoritative": is_approved,
        "extracted_at": reviewed_at,
        "metadata": provenance_metadata,
    }
    changed = _assign_changed(provenance, defaults, created=created)
    if changed:
        provenance.full_clean()
        provenance.save()
    return provenance


def _approve_space_boundary(space, *, reviewer_name, approved_at, notes):
    metadata = dict(space.metadata or {})
    metadata.update(
        {
            "review_state": MADISON_DETAILED_SPACE_APPROVED_STATE,
            "boundary_status": MADISON_DETAILED_SPACE_APPROVED_STATE,
            "boundary_approved_by": reviewer_name,
            "boundary_approved_at": approved_at.isoformat(),
            "boundary_review_method": "operator_review",
            "boundary_review_notes": notes,
        }
    )
    if metadata.get("geometry_review_state") == "operator_corrected":
        metadata.update(
            {
                "geometry_review_state": MADISON_DETAILED_SPACE_APPROVED_STATE,
                "geometry_review_approved_by": reviewer_name,
                "geometry_review_approved_at": approved_at.isoformat(),
                "geometry_review_approval_notes": notes,
            }
        )
    defaults = {
        "confidence": SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        "metadata": metadata,
    }
    changed = _assign_changed(space, defaults, created=False)
    if changed:
        space.full_clean()
        space.save()
    return changed


def _approve_space_provenance(space, *, reviewer_name, approved_at, notes):
    object_type = ContentType.objects.get_for_model(PhysicalSpace, for_concrete_model=False)
    for provenance in PlantProvenance.objects.filter(
        assigned_object_type=object_type,
        assigned_object_id=space.pk,
        source_ref__startswith="madison:cad:detailed-space:",
    ):
        metadata = dict(provenance.metadata or {})
        metadata.update(
            {
                "review_state": MADISON_DETAILED_SPACE_APPROVED_STATE,
                "boundary_status": MADISON_DETAILED_SPACE_APPROVED_STATE,
                "boundary_approved_by": reviewer_name,
                "boundary_approved_at": approved_at.isoformat(),
                "boundary_review_method": "operator_review",
                "boundary_review_notes": notes,
            }
        )
        if metadata.get("geometry_review_state") == "operator_corrected":
            metadata.update(
                {
                    "geometry_review_state": MADISON_DETAILED_SPACE_APPROVED_STATE,
                    "geometry_review_approved_by": reviewer_name,
                    "geometry_review_approved_at": approved_at.isoformat(),
                    "geometry_review_approval_notes": notes,
                }
            )
        defaults = {
            "confidence": SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            "is_authoritative": True,
            "metadata": metadata,
        }
        if _assign_changed(provenance, defaults, created=False):
            provenance.full_clean()
            provenance.save()


def _source_sheet(source_document, sheet_numbers):
    return (
        PlantSourceSheet.objects.filter(source_document=source_document, sheet_number__in=sheet_numbers)
        .order_by("page_index", "sheet_number", "pk")
        .first()
    )


def _source_layer(source_sheet):
    if source_sheet is None:
        return None
    return (
        PlantSourceLayer.objects.filter(source_sheet=source_sheet)
        .order_by("layer_kind", "name", "pk")
        .first()
    )


def _extract_room_markers(source_document):
    cad_dir = Path(source_document.source_uri or (source_document.metadata or {}).get("cad_dir") or "")
    if not cad_dir.exists() or not cad_dir.is_dir():
        return {}

    markers = {}
    for sheet_number in sorted({sheet for spec in MADISON_DETAILED_SPACE_SPECS for sheet in spec.source_sheet_numbers}):
        path = next(cad_dir.glob(f"* - {sheet_number} - *.dwg"), None)
        if path is None:
            continue
        for marker in _iter_room_markers(path, sheet_number=sheet_number):
            markers.setdefault(marker["room_label"], marker)
    return markers


def _iter_room_markers(path, *, sheet_number):
    try:
        ezdwg = import_module("ezdwg")
        doc = ezdwg.read(str(path))
    except Exception:
        return

    nearby_text = []
    for entity in doc.modelspace().query("MTEXT TEXT"):
        dxf = getattr(entity, "dxf", {}) or {}
        insert = dxf.get("insert")
        if not insert or len(insert) < 2:
            continue
        text = _clean_cad_text(str(dxf.get("text") or dxf.get("raw_text") or ""))
        if not text:
            continue
        nearby_text.append((text, _decimal(insert[0]), _decimal(insert[1])))

    for text, x, y in nearby_text:
        if not re.fullmatch(r"B\d{4}[A-Z]?", text):
            continue
        companion = [
            value
            for value, other_x, other_y in nearby_text
            if value != text and abs(other_x - x) <= Decimal("120") and abs(other_y - y) <= Decimal("180")
        ]
        yield {
            "room_label": text,
            "sheet_number": sheet_number,
            "source_x": _decimal_string(x),
            "source_y": _decimal_string(y),
            "nearby_text": companion[:5],
        }


def _clean_cad_text(value):
    text = "".join(character if 32 <= ord(character) <= 126 else " " for character in value)
    return re.sub(r"\s+", " ", text).strip()


def _rectangle_boundary(x, y, width, depth, *, coordinate_source):
    return {
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
        "coordinate_source": coordinate_source,
    }


def _resolve_site(site):
    if isinstance(site, Site):
        return site
    return Site.objects.filter(slug=str(site)).first()


def _assign_changed(instance, defaults, *, created):
    changed = created
    for field_name, value in defaults.items():
        if created or getattr(instance, field_name) != value:
            setattr(instance, field_name, value)
            changed = True
    return changed


def _reviewer_name(reviewer):
    if reviewer is None:
        return ""
    username = getattr(reviewer, "get_username", None)
    if callable(username):
        return username()
    return str(reviewer)


def _decimal(value):
    if value in (None, ""):
        return Decimal("0.000")
    return Decimal(str(value))


def _quantize(value):
    return Decimal(value).quantize(Decimal("0.001"))


def _decimal_string(value):
    return f"{_quantize(value):f}"


def _name(value):
    return str(value)[:100]


def _humanize(value):
    return str(value or "").replace("_", " ").replace("-", " ").title()
