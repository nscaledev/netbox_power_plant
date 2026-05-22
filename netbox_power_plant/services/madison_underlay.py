from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.text import slugify

from dcim.models import Rack, Site

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantSourceLayerKindChoices,
    PlantSourceTypeChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.cad_calibration import (
    GRID_UNIT_SVG,
    LOWER_LEFT_Y_UP,
    UPPER_LEFT_Y_DOWN,
    CoordinateBounds,
    LowerLeftGridCalibration,
)
from netbox_power_plant.services.blueprint_import import (
    BlueprintPhysicalElementImportSummary,
    PhysicalElementReconciliationSummary,
    import_blueprint_physical_elements,
    reconcile_physical_elements_to_objects,
)


MADISON_DATA_HALLS = ("1", "2")
MADISON_UNITS = GRID_UNIT_SVG
DEFAULT_RACK_WIDTH = Decimal("2.000")
DEFAULT_RACK_DEPTH = Decimal("4.000")
DEFAULT_RACK_HEIGHT = Decimal("8.000")
DEFAULT_SLOT_PITCH = Decimal("3.000")
DEFAULT_ROW_PITCH = Decimal("8.000")
DEFAULT_SITE_FRAME_WIDTH = Decimal("12271.000")
DEFAULT_SITE_FRAME_HEIGHT = Decimal("5221.000")
DEFAULT_DATA_HALL_FRAME_WIDTH = Decimal("600.000")
DEFAULT_DATA_HALL_FRAME_HEIGHT = Decimal("600.000")
DEFAULT_MADISON_SVG_BOUNDS = CoordinateBounds.from_values(
    0,
    0,
    DEFAULT_SITE_FRAME_WIDTH,
    DEFAULT_SITE_FRAME_HEIGHT,
)


@dataclass(frozen=True)
class MadisonSeedResult:
    object: object
    action: str

    @property
    def created(self):
        return self.action == "created"

    @property
    def updated(self):
        return self.action == "updated"


@dataclass(frozen=True)
class MadisonRackUnderlayRowResult:
    row_number: int
    source_key: str
    rack_name: str
    data_hall: str
    row_label: str
    rack_order: int | None
    action: str
    physical_space: PhysicalSpace | None = None
    physical_element: PhysicalElement | None = None
    spatial_placement: SpatialPlacement | None = None
    rack: Rack | None = None
    binding: PhysicalObjectBinding | None = None
    binding_action: str = ""
    confidence: str = ""
    coordinate_source: str = ""
    failure_reason: str = ""

    @property
    def blocked(self):
        return self.action == "blocked"

    @property
    def imported(self):
        return self.physical_element is not None

    @property
    def bound(self):
        return self.binding_action in {"bound", "already_bound"}

    @property
    def would_bind(self):
        return self.binding_action == "would_bind"

    @property
    def missing_source_coordinates(self):
        return self.coordinate_source == "derived_from_row_order"


@dataclass(frozen=True)
class MadisonUnderlayImportSummary:
    site: Site
    dry_run: bool
    source_document: PlantSourceDocument
    source_sheet: PlantSourceSheet
    source_layer: PlantSourceLayer
    grid_calibration: LowerLeftGridCalibration
    site_frame: SpatialFrame
    data_hall_frames: tuple[SpatialFrame, ...]
    data_hall_spaces: tuple[PhysicalSpace, ...]
    rows: tuple[MadisonRackUnderlayRowResult, ...]
    seed_results: tuple[MadisonSeedResult, ...]
    blueprint_summary: BlueprintPhysicalElementImportSummary | None = None
    reconciliation_summary: PhysicalElementReconciliationSummary | None = None

    @property
    def total_count(self):
        return len(self.rows)

    @property
    def imported_count(self):
        return len([row for row in self.rows if row.imported])

    @property
    def blocked_count(self):
        return len([row for row in self.rows if row.blocked])

    @property
    def bound_count(self):
        return len([row for row in self.rows if row.bound])

    @property
    def would_bind_count(self):
        return len([row for row in self.rows if row.would_bind])

    @property
    def missing_coordinate_count(self):
        return len([row for row in self.rows if row.missing_source_coordinates])

    @property
    def seed_created_count(self):
        return len([result for result in self.seed_results if result.created])

    @property
    def seed_updated_count(self):
        return len([result for result in self.seed_results if result.updated])

    @property
    def created_count(self):
        blueprint_created = self.blueprint_summary.created_count if self.blueprint_summary is not None else 0
        binding_created = self.reconciliation_summary.bound_count if self.reconciliation_summary is not None else 0
        return self.seed_created_count + blueprint_created + binding_created

    @property
    def updated_count(self):
        blueprint_updated = self.blueprint_summary.updated_count if self.blueprint_summary is not None else 0
        return self.seed_updated_count + blueprint_updated

    @property
    def blocked_reasons(self):
        return tuple(row.failure_reason for row in self.rows if row.failure_reason)

    @property
    def failure_reasons(self):
        return self.blocked_reasons

    @property
    def succeeded(self):
        return self.blocked_count == 0


@dataclass
class _PreparedMadisonRackRow:
    row_number: int
    raw_row: dict
    source_key: str = ""
    rack_name: str = ""
    data_hall: str = ""
    row_label: str = ""
    rack_order: int | None = None
    x: Decimal | None = None
    y: Decimal | None = None
    source_x: Decimal | None = None
    source_y: Decimal | None = None
    width: Decimal = DEFAULT_RACK_WIDTH
    depth: Decimal = DEFAULT_RACK_DEPTH
    height: Decimal = DEFAULT_RACK_HEIGHT
    rotation_degrees: Decimal = Decimal("0.00")
    source_ref: str = ""
    failure_reason: str = ""
    confidence: str = ""
    coordinate_source: str = ""
    source_coordinate_system: str = ""
    physical_space: PhysicalSpace | None = None

    @property
    def valid(self):
        return not self.failure_reason

    @property
    def slot_key(self):
        if not self.data_hall or not self.row_label or self.rack_order is None:
            return None
        return (self.data_hall, _label_key(self.row_label), self.rack_order)


class _DryRunRollback(Exception):
    pass


def import_madison_underlay(
    site,
    rows,
    *,
    apply=False,
    location=None,
    grid_calibration: LowerLeftGridCalibration | None = None,
) -> MadisonUnderlayImportSummary:
    """
    Import normalized Madison rack-manifest rows into the physical plant core.

    The input is intentionally row/dict based so callers can feed already-normalized
    workbook/CSV data without this service knowing about file formats.
    """
    raw_rows = tuple(rows)
    calibration = grid_calibration or default_madison_grid_calibration()
    if apply:
        return _process_madison_underlay(
            site,
            raw_rows,
            dry_run=False,
            location=location,
            grid_calibration=calibration,
        )

    summary = None
    try:
        with transaction.atomic():
            summary = _process_madison_underlay(
                site,
                raw_rows,
                dry_run=True,
                location=location,
                grid_calibration=calibration,
            )
            raise _DryRunRollback()
    except _DryRunRollback:
        return summary

    return summary


def default_madison_grid_calibration():
    return LowerLeftGridCalibration(
        source_name="madison-physical-layout.svg",
        source_type="svg",
        source_units=MADISON_UNITS,
        grid_units=MADISON_UNITS,
        source_axis_orientation=UPPER_LEFT_Y_DOWN,
        structure_bounds=DEFAULT_MADISON_SVG_BOUNDS,
        scale_x=Decimal("1"),
        scale_y=Decimal("1"),
        confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        warnings=(
            "Default Madison grid is based on the hand-built SVG overlay. "
            "Use CAD-derived calibration for authoritative physical dimensions.",
        ),
        provenance=("source-materials/layout/madison-physical-layout.svg",),
    )


def _process_madison_underlay(site, raw_rows, *, dry_run, location, grid_calibration):
    seed_results = []
    source_document, source_sheet, source_layer, results = _seed_source_records(
        site,
        location=location,
        grid_calibration=grid_calibration,
    )
    seed_results.extend(results)

    site_frame, data_hall_frames, results = _seed_frames(
        site,
        location=location,
        source_document=source_document,
        grid_calibration=grid_calibration,
    )
    seed_results.extend(results)

    prepared_rows = _prepare_manifest_rows(raw_rows, grid_calibration=grid_calibration)
    data_hall_spaces, results = _seed_spaces(
        site,
        location=location,
        source_document=source_document,
        data_hall_frames=data_hall_frames,
        prepared_rows=prepared_rows,
    )
    seed_results.extend(results)

    blueprint_rows = _blueprint_rows_for_prepared_rows(prepared_rows, data_hall_frames)
    blueprint_summary = None
    reconciliation_summary = None
    if blueprint_rows:
        blueprint_summary = import_blueprint_physical_elements(
            site,
            blueprint_rows,
            apply=True,
            default_location=location,
            default_source_document=source_document,
            default_source_sheet=source_sheet,
            default_source_layer=source_layer,
            default_discipline=PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            default_element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
            default_confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
        )
        imported_elements = tuple(
            row.physical_element for row in blueprint_summary.rows if row.physical_element is not None
        )
        if imported_elements:
            reconciliation_summary = reconcile_physical_elements_to_objects(
                imported_elements,
                Rack.objects.filter(site=site),
                apply=not dry_run,
                element_field="source_label",
                object_field="name",
                binding_role=PhysicalObjectBindingRoleChoices.ROLE_INVENTORY_OBJECT_FOR,
                confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            )

    row_results = _build_row_results(
        prepared_rows,
        blueprint_summary=blueprint_summary,
        reconciliation_summary=reconciliation_summary,
    )
    return MadisonUnderlayImportSummary(
        site=site,
        dry_run=dry_run,
        source_document=source_document,
        source_sheet=source_sheet,
        source_layer=source_layer,
        grid_calibration=grid_calibration,
        site_frame=site_frame,
        data_hall_frames=tuple(data_hall_frames[hall] for hall in MADISON_DATA_HALLS),
        data_hall_spaces=tuple(data_hall_spaces[hall] for hall in MADISON_DATA_HALLS),
        rows=tuple(row_results),
        seed_results=tuple(seed_results),
        blueprint_summary=blueprint_summary,
        reconciliation_summary=reconciliation_summary,
    )


def _seed_source_records(site, *, location, grid_calibration):
    seed_results = []
    base_slug = _scoped_slug(site, "madison-spatial-underlay")
    document, action = _upsert(
        PlantSourceDocument,
        base_slug,
        {
            "name": f"{site.name} Madison Spatial Underlay",
            "site": site,
            "location": location,
            "source_type": _source_type_for_calibration(grid_calibration),
            "discipline": PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            "document_id": "madison-spatial-underlay",
            "metadata": {
                "source_system": "madison",
                "underlay": "spatial",
                "coordinate_grid": grid_calibration.to_metadata(),
                "source_files": (
                    "electrical/2026.04.02_Enovum MAD1_Electical CAD/*.dwg",
                    "electrical/2026.04.02_Enovum MAD1_Electical CAD/*.pcp",
                    "source-materials/layout/madison-physical-layout.svg",
                    "source-materials/layout/madison-layout-workbook.xlsx",
                ),
            },
        },
    )
    seed_results.append(MadisonSeedResult(document, action))

    sheet, action = _upsert(
        PlantSourceSheet,
        f"{base_slug}-site-plan",
        {
            "name": f"{site.name} Madison Underlay Site Plan",
            "source_document": document,
            "sheet_number": "MADISON-UNDERLAY",
            "title": "Madison spatial underlay",
            "metadata": {
                "source_system": "madison",
                "underlay": "site_plan",
                "coordinate_grid": grid_calibration.to_metadata(),
            },
        },
    )
    seed_results.append(MadisonSeedResult(sheet, action))

    layer, action = _upsert(
        PlantSourceLayer,
        f"{base_slug}-rack-footprints",
        {
            "name": f"{site.name} Madison Rack Footprints",
            "source_sheet": sheet,
            "layer_name": "MADISON_RACK_FOOTPRINTS",
            "layer_kind": PlantSourceLayerKindChoices.KIND_RACK_LAYOUT,
            "discipline": PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            "metadata": {"source_system": "madison", "feature": "rack_footprint"},
        },
    )
    seed_results.append(MadisonSeedResult(layer, action))

    return document, sheet, layer, tuple(seed_results)


def _seed_frames(site, *, location, source_document, grid_calibration):
    seed_results = []
    site_frame, action = _upsert(
        SpatialFrame,
        _scoped_slug(site, "madison-site-plan-frame"),
        {
            "name": f"{site.name} Madison Site Plan",
            "site": site,
            "location": None,
            "width": grid_calibration.width,
            "height": grid_calibration.height,
            "units": grid_calibration.grid_units,
            "axis_orientation": LOWER_LEFT_Y_UP,
            "source_document": source_document.name,
            "source_ref": "madison:site-plan:lower-left-grid",
        },
    )
    seed_results.append(MadisonSeedResult(site_frame, action))

    data_hall_frames = {}
    for hall in MADISON_DATA_HALLS:
        hall_frame, action = _upsert(
            SpatialFrame,
            _scoped_slug(site, f"madison-data-hall-{hall}-frame"),
            {
                "name": f"{site.name} Madison Data Hall {hall}",
                "site": site,
                "location": location,
                "parent_frame": site_frame,
                "origin_x_in_parent": Decimal("0.000"),
                "origin_y_in_parent": DEFAULT_DATA_HALL_FRAME_HEIGHT * (int(hall) - 1),
                "width": DEFAULT_DATA_HALL_FRAME_WIDTH,
                "height": DEFAULT_DATA_HALL_FRAME_HEIGHT,
                "units": grid_calibration.grid_units,
                "axis_orientation": LOWER_LEFT_Y_UP,
                "source_document": source_document.name,
                "source_ref": f"madison:data-hall-{hall}",
            },
        )
        data_hall_frames[hall] = hall_frame
        seed_results.append(MadisonSeedResult(hall_frame, action))

    return site_frame, data_hall_frames, tuple(seed_results)


def _seed_spaces(site, *, location, source_document, data_hall_frames, prepared_rows):
    seed_results = []
    data_hall_spaces = {}
    for hall in MADISON_DATA_HALLS:
        hall_space, action = _upsert(
            PhysicalSpace,
            _scoped_slug(site, f"data-hall-{hall}"),
            {
                "name": f"Data Hall {hall}",
                "site": site,
                "location": location,
                "spatial_frame": data_hall_frames[hall],
                "space_kind": PhysicalSpaceKindChoices.KIND_DATA_HALL,
                "source_document": source_document.name,
                "source_ref": f"madison:data-hall-{hall}",
                "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
                "metadata": {"source_system": "madison", "data_hall": hall},
            },
        )
        data_hall_spaces[hall] = hall_space
        seed_results.append(MadisonSeedResult(hall_space, action))

    row_spaces = {}
    for row in prepared_rows:
        if not row.valid:
            continue

        row_key = (row.data_hall, _label_key(row.row_label))
        row_space = row_spaces.get(row_key)
        if row_space is None:
            row_space, action = _upsert(
                PhysicalSpace,
                _scoped_slug(site, f"data-hall-{row.data_hall}-row-{_label_key(row.row_label)}"),
                {
                    "name": f"Data Hall {row.data_hall} Row {row.row_label}",
                    "site": site,
                    "location": location,
                    "spatial_frame": data_hall_frames[row.data_hall],
                    "parent_space": data_hall_spaces[row.data_hall],
                    "space_kind": PhysicalSpaceKindChoices.KIND_ROW_ZONE,
                    "source_document": source_document.name,
                    "source_ref": f"madison:data-hall-{row.data_hall}:row-{row.row_label}",
                    "confidence": SpatialConfidenceChoices.CONFIDENCE_DERIVED,
                    "metadata": {
                        "source_system": "madison",
                        "data_hall": row.data_hall,
                        "row": row.row_label,
                    },
                },
            )
            row_spaces[row_key] = row_space
            seed_results.append(MadisonSeedResult(row_space, action))

        slot_slug = _slot_space_slug(site, row)
        slot_space, action = _upsert(
            PhysicalSpace,
            slot_slug,
            {
                "name": f"{row.rack_name} Rack Slot",
                "site": site,
                "location": location,
                "spatial_frame": data_hall_frames[row.data_hall],
                "parent_space": row_space,
                "space_kind": PhysicalSpaceKindChoices.KIND_RACK_SLOT,
                "boundary_geometry": _slot_boundary(row),
                "source_document": source_document.name,
                "source_ref": row.source_ref,
                "confidence": row.confidence,
                "metadata": _rack_metadata(row),
            },
        )
        row.physical_space = slot_space
        seed_results.append(MadisonSeedResult(slot_space, action))

    return data_hall_spaces, tuple(seed_results)


def _prepare_manifest_rows(raw_rows, *, grid_calibration):
    prepared_rows = [
        _prepare_manifest_row(index, raw_row, grid_calibration=grid_calibration)
        for index, raw_row in enumerate(raw_rows, start=1)
    ]
    _mark_duplicates(prepared_rows)
    _assign_missing_coordinates(prepared_rows)
    return tuple(prepared_rows)


def _prepare_manifest_row(row_number, raw_row, *, grid_calibration):
    if not isinstance(raw_row, dict):
        return _PreparedMadisonRackRow(
            row_number=row_number,
            raw_row={},
            source_key=f"row-{row_number}",
            failure_reason="Madison rack manifest row must be a dict.",
        )

    row = _PreparedMadisonRackRow(row_number=row_number, raw_row=raw_row)
    failures = []
    row.rack_name = str(_row_value(raw_row, "rack_name", "rack", "rack_label", "source_label", "name") or "").strip()
    row.source_key = str(_row_value(raw_row, "source_key", "manifest_key") or row.rack_name).strip()
    row.row_label = str(_row_value(raw_row, "row", "rack_row", "row_label") or "").strip()
    row.data_hall = _normalize_data_hall(_row_value(raw_row, "data_hall", "datahall", "hall", "dh"))
    row.source_ref = str(_row_value(raw_row, "source_ref") or row.source_key or f"row-{row_number}").strip()

    if not row.rack_name:
        failures.append("rack_name is required.")
    if not row.source_key:
        failures.append("source_key is required.")
    if not row.data_hall:
        failures.append("data_hall must resolve to Data Hall 1 or Data Hall 2.")
    if not row.row_label:
        failures.append("row is required.")

    order_value = _row_value(raw_row, "order", "rack_order", "slot", "slot_index", "position")
    row.rack_order = _positive_int(order_value)
    if row.rack_order is None:
        failures.append("rack order/slot is required as a positive integer.")

    row.x, x_failure = _optional_decimal(raw_row, "x", "grid_x", "footprint_x")
    row.y, y_failure = _optional_decimal(raw_row, "y", "grid_y", "footprint_y")
    failures.extend(failure for failure in (x_failure, y_failure) if failure)
    if (row.x is None) != (row.y is None):
        failures.append("both x and y are required when grid coordinates are provided.")

    row.source_x, source_x_failure = _optional_decimal(
        raw_row,
        "cad_x",
        "source_x",
        "dwg_x",
        "svg_x",
        "plan_x",
    )
    row.source_y, source_y_failure = _optional_decimal(
        raw_row,
        "cad_y",
        "source_y",
        "dwg_y",
        "svg_y",
        "plan_y",
    )
    failures.extend(failure for failure in (source_x_failure, source_y_failure) if failure)
    if (row.source_x is None) != (row.source_y is None):
        failures.append("both source_x/cad_x and source_y/cad_y are required when source coordinates are provided.")
    if row.x is not None and row.source_x is not None:
        failures.append("provide either grid x/y or source cad_x/cad_y coordinates, not both.")

    width, width_failure = _optional_decimal(raw_row, "width", "rack_width")
    depth, depth_failure = _optional_decimal(raw_row, "depth", "rack_depth")
    height, height_failure = _optional_decimal(raw_row, "height", "rack_height")
    rotation, rotation_failure = _optional_decimal(raw_row, "rotation_degrees", "rotation", "angle")
    failures.extend(
        failure for failure in (width_failure, depth_failure, height_failure, rotation_failure) if failure
    )
    for dimension_name, dimension_value in (("width", width), ("depth", depth), ("height", height)):
        if dimension_value is not None and dimension_value <= 0:
            failures.append(f"{dimension_name} must be greater than zero.")
    row.width = width or DEFAULT_RACK_WIDTH
    row.depth = depth or DEFAULT_RACK_DEPTH
    row.height = height or DEFAULT_RACK_HEIGHT
    row.rotation_degrees = rotation or Decimal("0.00")

    if row.source_x is not None and row.source_y is not None:
        row.x, row.y = grid_calibration.source_to_grid(row.source_x, row.source_y)
        row.confidence = grid_calibration.confidence
        row.coordinate_source = f"{grid_calibration.source_type}_coordinates"
        row.source_coordinate_system = grid_calibration.source_name
    elif row.x is not None and row.y is not None:
        row.confidence = SpatialConfidenceChoices.CONFIDENCE_DERIVED
        row.coordinate_source = "manifest_grid_coordinates"
        row.source_coordinate_system = "madison_lower_left_grid"

    row.failure_reason = " ".join(failures)
    return row


def _mark_duplicates(prepared_rows):
    source_key_duplicates = _duplicate_keys(
        _casefold_key(row.source_key) for row in prepared_rows if row.source_key
    )
    rack_name_duplicates = _duplicate_keys(
        _casefold_key(row.rack_name) for row in prepared_rows if row.rack_name
    )
    slot_key_duplicates = _duplicate_keys(row.slot_key for row in prepared_rows if row.slot_key is not None)

    for row in prepared_rows:
        reasons = []
        if row.source_key and _casefold_key(row.source_key) in source_key_duplicates:
            reasons.append(f"duplicate source_key in Madison manifest: {row.source_key}.")
        if row.rack_name and _casefold_key(row.rack_name) in rack_name_duplicates:
            reasons.append(f"duplicate rack_name in Madison manifest: {row.rack_name}.")
        if row.slot_key is not None and row.slot_key in slot_key_duplicates:
            reasons.append(
                f"duplicate rack slot in Madison manifest: data hall {row.data_hall} "
                f"row {row.row_label} order {row.rack_order}."
            )
        if reasons:
            row.failure_reason = " ".join(reason for reason in (row.failure_reason, *reasons) if reason)


def _assign_missing_coordinates(prepared_rows):
    rows_by_hall = {}
    for row in prepared_rows:
        if row.valid:
            rows_by_hall.setdefault(row.data_hall, set()).add(row.row_label)

    row_indexes = {}
    for hall, row_labels in rows_by_hall.items():
        for index, row_label in enumerate(sorted(row_labels, key=_row_sort_key)):
            row_indexes[(hall, _label_key(row_label))] = index

    for row in prepared_rows:
        if not row.valid or row.x is not None:
            continue

        row_index = row_indexes[(row.data_hall, _label_key(row.row_label))]
        row.x = (DEFAULT_SLOT_PITCH * Decimal(row.rack_order - 1)) + (row.width / 2)
        row.y = (DEFAULT_ROW_PITCH * Decimal(row_index)) + (row.depth / 2)
        row.confidence = SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL
        row.coordinate_source = "derived_from_row_order"


def _blueprint_rows_for_prepared_rows(prepared_rows, data_hall_frames):
    rows = []
    for row in prepared_rows:
        if not row.valid:
            continue

        rows.append(
            {
                "source_key": row.source_key,
                "source_label": row.rack_name,
                "name": f"{row.rack_name} Rack Footprint",
                "label": row.rack_name,
                "role": "rack_footprint",
                "source_ref": row.source_ref,
                "discipline": PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
                "element_kind": PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
                "element_type_name": "Rack Footprint",
                "physical_space": row.physical_space,
                "spatial_frame": data_hall_frames[row.data_hall],
                "x": row.x,
                "y": row.y,
                "width": row.width,
                "depth": row.depth,
                "height": row.height,
                "rotation_degrees": row.rotation_degrees,
                "anchor": SpatialAnchorChoices.ANCHOR_CENTER,
                "confidence": row.confidence,
                "metadata": _rack_metadata(row),
                "placement_metadata": _placement_metadata(row),
                "provenance_metadata": {"madison_manifest_row": _json_safe(row.raw_row)},
            }
        )
    return tuple(rows)


def _build_row_results(prepared_rows, *, blueprint_summary, reconciliation_summary):
    blueprint_results = {}
    if blueprint_summary is not None:
        blueprint_results = {row.source_key: row for row in blueprint_summary.rows}

    reconciliation_results = {}
    if reconciliation_summary is not None:
        reconciliation_results = {
            row.physical_element.pk: row
            for row in reconciliation_summary.rows
            if row.physical_element is not None and row.physical_element.pk is not None
        }

    results = []
    for row in prepared_rows:
        if not row.valid:
            results.append(_blocked_row_result(row, row.failure_reason))
            continue

        blueprint_result = blueprint_results.get(row.source_key)
        if blueprint_result is None:
            results.append(_blocked_row_result(row, "Madison row was not submitted to blueprint import."))
            continue
        if blueprint_result.blocked:
            results.append(_blocked_row_result(row, blueprint_result.failure_reason))
            continue

        reconciliation_result = reconciliation_results.get(blueprint_result.physical_element.pk)
        rack = reconciliation_result.matched_object if reconciliation_result is not None else None
        binding = reconciliation_result.binding if reconciliation_result is not None else None
        binding_action = reconciliation_result.action if reconciliation_result is not None else ""
        failure_reason = reconciliation_result.failure_reason if reconciliation_result is not None else ""
        results.append(
            MadisonRackUnderlayRowResult(
                row_number=row.row_number,
                source_key=row.source_key,
                rack_name=row.rack_name,
                data_hall=row.data_hall,
                row_label=row.row_label,
                rack_order=row.rack_order,
                action=blueprint_result.action,
                physical_space=row.physical_space,
                physical_element=blueprint_result.physical_element,
                spatial_placement=blueprint_result.spatial_placement,
                rack=rack,
                binding=binding,
                binding_action=binding_action,
                confidence=row.confidence,
                coordinate_source=row.coordinate_source,
                failure_reason=failure_reason,
            )
        )
    return tuple(results)


def _blocked_row_result(row, failure_reason):
    return MadisonRackUnderlayRowResult(
        row_number=row.row_number,
        source_key=row.source_key,
        rack_name=row.rack_name,
        data_hall=row.data_hall,
        row_label=row.row_label,
        rack_order=row.rack_order,
        action="blocked",
        confidence=row.confidence,
        coordinate_source=row.coordinate_source,
        failure_reason=failure_reason,
    )


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


def _row_value(row, *aliases):
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(_normalize_key(alias))
        if value not in (None, ""):
            return value
    return None


def _normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _normalize_data_hall(value):
    if value in (None, ""):
        return ""
    match = re.search(r"\b([12])\b", str(value))
    if not match:
        compact_match = re.fullmatch(
            r"(?:dh|datahall|hall)([12])",
            re.sub(r"[^a-z0-9]+", "", str(value).lower()),
        )
        match = compact_match
    if not match:
        return ""
    hall = match.group(1)
    return hall if hall in MADISON_DATA_HALLS else ""


def _positive_int(value):
    if value in (None, ""):
        return None
    try:
        parsed_decimal = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if parsed_decimal != parsed_decimal.to_integral_value():
        return None
    parsed = int(parsed_decimal)
    return parsed if parsed > 0 else None


def _optional_decimal(row, *aliases):
    value = _row_value(row, *aliases)
    if value in (None, ""):
        return None, ""
    try:
        return Decimal(str(value).strip()), ""
    except (InvalidOperation, ValueError):
        return None, f"{aliases[0]} must be a decimal value."


def _duplicate_keys(keys):
    counts = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count > 1}


def _casefold_key(value):
    return str(value or "").strip().casefold()


def _row_sort_key(value):
    text = str(value or "").strip()
    match = re.fullmatch(r"([A-Za-z]+)(\d+)?", text)
    if match:
        letters, number = match.groups()
        return (letters.casefold(), int(number or 0), text.casefold())
    try:
        return ("", int(text), text.casefold())
    except ValueError:
        return (text.casefold(), 0, text.casefold())


def _label_key(value):
    return slugify(str(value or "").strip()) or "unknown"


def _scoped_slug(site, value):
    site_part = slugify(getattr(site, "slug", "") or getattr(site, "name", "")) or "site"
    value_part = slugify(value) or "madison"
    return f"{site_part}-{value_part}"[:100]


def _slot_space_slug(site, row):
    return _scoped_slug(
        site,
        f"data-hall-{row.data_hall}-row-{_label_key(row.row_label)}-slot-{row.rack_order}",
    )


def _slot_boundary(row):
    half_width = row.width / 2
    half_depth = row.depth / 2
    return {
        "type": "rectangle",
        "anchor": SpatialAnchorChoices.ANCHOR_CENTER,
        "x": str(row.x),
        "y": str(row.y),
        "width": str(row.width),
        "depth": str(row.depth),
        "x_min": str(row.x - half_width),
        "x_max": str(row.x + half_width),
        "y_min": str(row.y - half_depth),
        "y_max": str(row.y + half_depth),
        "coordinate_source": row.coordinate_source,
    }


def _rack_metadata(row):
    return {
        "source_system": "madison",
        "source_key": row.source_key,
        "rack_name": row.rack_name,
        "data_hall": row.data_hall,
        "row": row.row_label,
        "rack_order": row.rack_order,
        "coordinate_source": row.coordinate_source,
        "source_coordinate_system": row.source_coordinate_system,
        "source_x": str(row.source_x) if row.source_x is not None else "",
        "source_y": str(row.source_y) if row.source_y is not None else "",
        "confidence": row.confidence,
        "madison_manifest_row": _json_safe(row.raw_row),
    }


def _placement_metadata(row):
    metadata = _rack_metadata(row)
    metadata["missing_cad_coordinates"] = row.coordinate_source == "derived_from_row_order"
    return metadata


def _source_type_for_calibration(grid_calibration):
    if grid_calibration.source_type in {"dwg", "dxf", "cad"}:
        return PlantSourceTypeChoices.TYPE_CAD_EXPORT
    if grid_calibration.source_type == "svg":
        return PlantSourceTypeChoices.TYPE_SVG
    return PlantSourceTypeChoices.TYPE_OTHER


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if value in (None, True, False) or isinstance(value, (str, int, float)):
        return value
    return str(value)
