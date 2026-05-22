from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.text import slugify

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantExtractionMethodChoices,
    PlantSourceLayerKindChoices,
    PlantSourceTypeChoices,
    SpatialAnchorChoices,
    SpatialAxisOrientationChoices,
    SpatialConfidenceChoices,
    SpatialPlacementKindChoices,
)
from netbox_power_plant.models import (
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_cad_underlay import (
    MadisonCadCalibrationReport,
    build_madison_cad_calibration_report,
)


MADISON_CAD_SOURCE_DOCUMENT_KEY = "madison-cad-electrical-package"
MADISON_CAD_SITE_FRAME_KEY = "madison-cad-site-coordinate-plane"
MADISON_CAD_SITE_SPACE_KEY = "madison-cad-site-coordinate-plane-space"
MADISON_CAD_CURRENT_BUILDING_SPACE_KEY = "madison-current-building-footprint"
MADISON_CAD_CURRENT_BUILDING_PLACEMENT_KEY = "madison-current-building-placement"


@dataclass(frozen=True)
class MadisonCadMaterializationResult:
    object: object
    action: str

    @property
    def created(self):
        return self.action == "created"

    @property
    def updated(self):
        return self.action == "updated"


@dataclass(frozen=True)
class MadisonCadUnderlayMaterializationSummary:
    site: Site
    dry_run: bool
    report: MadisonCadCalibrationReport
    source_document: PlantSourceDocument
    source_sheets: tuple[PlantSourceSheet, ...]
    source_layers: tuple[PlantSourceLayer, ...]
    site_frame: SpatialFrame
    site_space: PhysicalSpace
    current_building_space: PhysicalSpace | None = None
    current_building_placement: SpatialPlacement | None = None
    provenance_records: tuple[PlantProvenance, ...] = ()
    seed_results: tuple[MadisonCadMaterializationResult, ...] = ()

    @property
    def created_count(self):
        return len([result for result in self.seed_results if result.created])

    @property
    def updated_count(self):
        return len([result for result in self.seed_results if result.updated])

    @property
    def sheet_count(self):
        return len(self.source_sheets)

    @property
    def layer_count(self):
        return len(self.source_layers)


@dataclass(frozen=True)
class MadisonCadUnderlayIngestSummary:
    site: Site
    site_created: bool
    materialization: MadisonCadUnderlayMaterializationSummary

    @property
    def report(self):
        return self.materialization.report


class _DryRunRollback(Exception):
    pass


def ingest_madison_cad_underlay(
    *,
    site_slug,
    site_name="",
    cad_dir,
    source_units: str | None = "inch",
    apply=False,
) -> MadisonCadUnderlayIngestSummary:
    """
    Ingest a Madison CAD package directly into the site modeling records.

    This is the workflow-oriented entry point used by the UI: it validates the CAD
    package directory, creates the site if needed, parses the source files, and
    materializes the underlay records in one operation.
    """
    cad_root = _validate_cad_dir(cad_dir)
    if apply:
        with transaction.atomic():
            return _ingest_madison_cad_underlay(
                site_slug=site_slug,
                site_name=site_name,
                cad_dir=cad_root,
                source_units=source_units,
                apply=True,
            )
    summary = None
    try:
        with transaction.atomic():
            summary = _ingest_madison_cad_underlay(
                site_slug=site_slug,
                site_name=site_name,
                cad_dir=cad_root,
                source_units=source_units,
                apply=False,
            )
            raise _DryRunRollback()
    except _DryRunRollback:
        return summary

    return summary


def materialize_madison_cad_underlay(
    site,
    *,
    cad_dir=None,
    report: MadisonCadCalibrationReport | None = None,
    source_units: str | None = "inch",
    apply=False,
) -> MadisonCadUnderlayMaterializationSummary:
    """
    Persist a Madison CAD calibration report into the physical plant source/space model.

    This service deliberately materializes derived records with deterministic slugs so
    repeated runs can refresh the review state without duplicating the underlay.
    """
    resolved_site = _resolve_site(site)
    calibration_report = report
    if calibration_report is None:
        if cad_dir is None:
            raise ValueError("cad_dir is required when a Madison CAD calibration report is not supplied.")
        calibration_report = build_madison_cad_calibration_report(cad_dir, source_units=source_units)

    if calibration_report.calibration is None:
        raise ValueError("Madison CAD calibration must include confirmed source units before materialization.")

    if apply:
        with transaction.atomic():
            return _process_madison_cad_underlay(resolved_site, calibration_report, dry_run=False)

    summary = None
    try:
        with transaction.atomic():
            summary = _process_madison_cad_underlay(resolved_site, calibration_report, dry_run=True)
            raise _DryRunRollback()
    except _DryRunRollback:
        return summary

    return summary


def madison_cad_object_slug(site, key):
    site_part = slugify(getattr(site, "slug", "") or getattr(site, "name", "")) or "site"
    key_part = slugify(key) or "madison-cad"
    return f"{site_part}-{key_part}"[:100]


def _ingest_madison_cad_underlay(*, site_slug, site_name, cad_dir, source_units, apply):
    site_slug = str(site_slug).strip()
    site_name = str(site_name or site_slug).strip() or site_slug
    site, created = Site.objects.get_or_create(
        slug=site_slug,
        defaults={"name": site_name},
    )
    if site_name and site.name != site_name:
        site.name = site_name
        site.full_clean()
        site.save()
    materialization = materialize_madison_cad_underlay(
        site,
        cad_dir=cad_dir,
        source_units=source_units,
        apply=apply,
    )
    return MadisonCadUnderlayIngestSummary(site=site, site_created=created, materialization=materialization)


def _process_madison_cad_underlay(site, report, *, dry_run):
    manifest = report.to_manifest()
    results = []
    source_document, action = _upsert(
        PlantSourceDocument,
        madison_cad_object_slug(site, MADISON_CAD_SOURCE_DOCUMENT_KEY),
        {
            "name": _name(f"{site.name} Madison Electrical CAD Package"),
            "site": site,
            "location": None,
            "source_type": PlantSourceTypeChoices.TYPE_CAD_EXPORT,
            "discipline": PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
            "document_id": "MAD1-CAD-2026-04-02",
            "revision": "",
            "source_uri": str(report.cad_dir),
            "metadata": {
                "source_system": "madison_cad",
                "cad_dir": str(report.cad_dir),
                "calibration_status": report.status,
                "source_units": report.source_units or "",
                "grid_units": report.grid_units,
                "axis_orientation": manifest.get("axis_orientation", ""),
                "coordinate_plane_bounds": manifest.get("coordinate_plane_bounds"),
                "current_building": manifest.get("current_building"),
                "rendered_underlay_image_uri": _rendered_underlay_image_uri(report),
                "warnings": list(report.warnings),
                "review_state": "operator_review_required",
            },
        },
    )
    results.append(MadisonCadMaterializationResult(source_document, action))

    source_sheets, source_layers, sheet_results = _seed_source_sheets_and_layers(
        site,
        source_document=source_document,
        report=report,
    )
    results.extend(sheet_results)

    site_frame, action = _upsert(
        SpatialFrame,
        madison_cad_object_slug(site, MADISON_CAD_SITE_FRAME_KEY),
        {
            "name": _name(f"{site.name} Madison CAD Site Coordinate Plane"),
            "site": site,
            "location": None,
            "parent_frame": None,
            "origin_x_in_parent": None,
            "origin_y_in_parent": None,
            "width": report.calibration.width,
            "height": report.calibration.height,
            "units": report.grid_units,
            "axis_orientation": SpatialAxisOrientationChoices.ORIENTATION_LOWER_LEFT_X_RIGHT_Y_UP,
            "source_document": source_document.name,
            "source_ref": "madison:cad:site-coordinate-plane",
            "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            "metadata": {
                "source_system": "madison_cad",
                "coordinate_plane_bounds": manifest.get("coordinate_plane_bounds"),
                "current_building": manifest.get("current_building"),
                "warnings": list(report.warnings),
                "review_state": "operator_review_required",
            },
        },
    )
    results.append(MadisonCadMaterializationResult(site_frame, action))

    site_space, action = _upsert(
        PhysicalSpace,
        madison_cad_object_slug(site, MADISON_CAD_SITE_SPACE_KEY),
        {
            "name": _name(f"{site.name} Madison CAD Site Coordinate Plane"),
            "site": site,
            "location": None,
            "spatial_frame": site_frame,
            "parent_space": None,
            "space_kind": PhysicalSpaceKindChoices.KIND_CAMPUS,
            "boundary_geometry": _rectangle_boundary(
                Decimal("0.000"),
                Decimal("0.000"),
                report.calibration.width,
                report.calibration.height,
                coordinate_source="madison_cad_coordinate_plane",
            ),
            "source_document": source_document.name,
            "source_ref": "madison:cad:site-coordinate-plane",
            "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            "metadata": {
                "source_system": "madison_cad",
                "coordinate_plane_bounds": manifest.get("coordinate_plane_bounds"),
                "warnings": list(report.warnings),
            },
        },
    )
    results.append(MadisonCadMaterializationResult(site_space, action))

    current_building_space = None
    current_building_placement = None
    current_building = manifest.get("current_building") or {}
    if current_building:
        current_building_space, current_building_placement, building_results = _seed_current_building(
            site,
            source_document=source_document,
            site_frame=site_frame,
            site_space=site_space,
            current_building=current_building,
        )
        results.extend(building_results)

    provenance_records, provenance_results = _seed_provenance(
        source_document=source_document,
        assigned_objects=(
            site_frame,
            site_space,
            current_building_space,
            current_building_placement,
        ),
    )
    results.extend(provenance_results)

    return MadisonCadUnderlayMaterializationSummary(
        site=site,
        dry_run=dry_run,
        report=report,
        source_document=source_document,
        source_sheets=tuple(source_sheets),
        source_layers=tuple(source_layers),
        site_frame=site_frame,
        site_space=site_space,
        current_building_space=current_building_space,
        current_building_placement=current_building_placement,
        provenance_records=tuple(provenance_records),
        seed_results=tuple(results),
    )


def _seed_source_sheets_and_layers(site, *, source_document, report):
    source_sheets = []
    source_layers = []
    results = []
    for index, analysis in enumerate(report.sheet_analyses, start=1):
        sheet_slug = madison_cad_object_slug(site, f"madison-cad-{analysis.source.sheet_number}")
        sheet_manifest = analysis.to_manifest(report.cad_dir, source_units=report.source_units)
        sheet, action = _upsert(
            PlantSourceSheet,
            sheet_slug,
            {
                "name": _name(f"{site.name} CAD {analysis.source.sheet_number}"),
                "source_document": source_document,
                "sheet_number": analysis.source.sheet_number,
                "title": analysis.source.title,
                "scale": analysis.pcp_metadata.scale if analysis.pcp_metadata is not None else "",
                "page_index": index,
                "metadata": {
                    "source_system": "madison_cad",
                    "role": analysis.source.role,
                    "participates_in_site_grid": analysis.source.participates_in_site_grid,
                    "source_units": report.source_units or "",
                    "sheet": sheet_manifest,
                },
            },
        )
        source_sheets.append(sheet)
        results.append(MadisonCadMaterializationResult(sheet, action))

        layer, action = _upsert(
            PlantSourceLayer,
            f"{sheet_slug}-geometry"[:100],
            {
                "name": _name(f"{site.name} CAD {analysis.source.sheet_number} Geometry"),
                "source_sheet": sheet,
                "layer_name": "DWG_GEOMETRY",
                "layer_kind": PlantSourceLayerKindChoices.KIND_GEOMETRY,
                "discipline": PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
                "is_visible": True,
                "metadata": {
                    "source_system": "madison_cad",
                    "sheet_number": analysis.source.sheet_number,
                    "role": analysis.source.role,
                    "participates_in_site_grid": analysis.source.participates_in_site_grid,
                    "extraction_status": "error" if analysis.error else "ok",
                },
            },
        )
        source_layers.append(layer)
        results.append(MadisonCadMaterializationResult(layer, action))

    return tuple(source_sheets), tuple(source_layers), tuple(results)


def _seed_current_building(site, *, source_document, site_frame, site_space, current_building):
    results = []
    origin = current_building.get("origin_in_site_grid") or {}
    x = _decimal(origin.get("x"))
    y = _decimal(origin.get("y"))
    width = _decimal(current_building.get("width"))
    height = _decimal(current_building.get("height"))
    building_space, action = _upsert(
        PhysicalSpace,
        madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_SPACE_KEY),
        {
            "name": _name(f"{site.name} Madison Current Building Footprint"),
            "site": site,
            "location": None,
            "spatial_frame": site_frame,
            "parent_space": site_space,
            "space_kind": PhysicalSpaceKindChoices.KIND_BUILDING,
            "boundary_geometry": _rectangle_boundary(
                x,
                y,
                width,
                height,
                coordinate_source="madison_cad_current_building_footprint",
            ),
            "source_document": source_document.name,
            "source_ref": "madison:cad:current-building-footprint",
            "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            "metadata": {
                "source_system": "madison_cad",
                "current_building": current_building,
                "inference_method": current_building.get("inference_method", ""),
            },
        },
    )
    results.append(MadisonCadMaterializationResult(building_space, action))

    placement, action = _upsert(
        SpatialPlacement,
        madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_PLACEMENT_KEY),
        {
            "name": _name(f"{site.name} Madison Current Building Placement"),
            "spatial_frame": site_frame,
            "assigned_object_type": ContentType.objects.get_for_model(
                PhysicalSpace,
                for_concrete_model=False,
            ),
            "assigned_object_id": building_space.pk,
            "x": x,
            "y": y,
            "z": None,
            "width": width,
            "depth": height,
            "height": None,
            "rotation_degrees": Decimal("0.00"),
            "anchor": SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
            "placement_kind": SpatialPlacementKindChoices.KIND_INFERRED,
            "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            "source_document": source_document.name,
            "source_ref": "madison:cad:current-building-footprint",
            "metadata": {
                "source_system": "madison_cad",
                "current_building": current_building,
            },
        },
    )
    results.append(MadisonCadMaterializationResult(placement, action))
    return building_space, placement, tuple(results)


def _seed_provenance(*, source_document, assigned_objects):
    records = []
    results = []
    for assigned_object in assigned_objects:
        if assigned_object is None:
            continue
        object_type = ContentType.objects.get_for_model(type(assigned_object), for_concrete_model=False)
        object_label = assigned_object._meta.verbose_name.title()
        slug = f"{assigned_object.slug}-madison-cad-provenance"[:100]
        record, action = _upsert(
            PlantProvenance,
            slug,
            {
                "name": _name(f"{object_label}: {assigned_object.name} Madison CAD Provenance"),
                "assigned_object_type": object_type,
                "assigned_object_id": assigned_object.pk,
                "source_document": source_document,
                "source_sheet": None,
                "source_layer": None,
                "extraction_method": PlantExtractionMethodChoices.METHOD_CAD_EXPORT,
                "source_ref": "madison:cad:underlay",
                "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
                "is_authoritative": False,
                "metadata": {
                    "source_system": "madison_cad",
                    "review_state": "operator_review_required",
                },
            },
        )
        records.append(record)
        results.append(MadisonCadMaterializationResult(record, action))
    return tuple(records), tuple(results)


def _upsert(model, slug, defaults):
    instance = model.objects.filter(slug=slug).order_by("pk").first()
    created = instance is None
    if instance is None:
        instance = model(slug=slug)

    changed = created
    for field_name, value in defaults.items():
        if created:
            setattr(instance, field_name, value)
            continue
        if getattr(instance, field_name) != value:
            setattr(instance, field_name, value)
            changed = True

    if changed:
        instance.full_clean()
        instance.save()

    if created:
        return instance, "created"
    if changed:
        return instance, "updated"
    return instance, "unchanged"


def _resolve_site(site):
    if isinstance(site, Site):
        return site
    resolved = Site.objects.filter(slug=str(site)).first()
    if resolved is None:
        raise ValueError(f"No site found for slug '{site}'.")
    return resolved


def _validate_cad_dir(cad_dir):
    root = Path(cad_dir).expanduser()
    if not root.exists():
        raise ValueError(f"CAD directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"CAD path must be a directory: {root}")
    if not any(path.suffix.lower() == ".dwg" for path in root.iterdir() if path.is_file()):
        raise ValueError(f"CAD directory does not contain DWG files: {root}")
    return root


def _rendered_underlay_image_uri(report):
    image_path = Path(report.cad_dir).parent / "generated" / "madison_cad_crop_unit_assumptions.png"
    if not image_path.exists():
        return ""
    return f"file://{image_path}"


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


def _decimal(value):
    if value in (None, ""):
        return Decimal("0.000")
    return Decimal(str(value)).quantize(Decimal("0.001"))


def _name(value):
    return str(value)[:100]
