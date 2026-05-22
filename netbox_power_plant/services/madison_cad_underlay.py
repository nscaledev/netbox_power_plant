from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from importlib import import_module
from pathlib import Path

from netbox_power_plant.services.cad_calibration import (
    CONFIDENCE_DERIVED,
    GRID_UNIT_FEET,
    LOWER_LEFT_Y_UP,
    CadCalibrationError,
    CoordinateBounds,
    DwgGeometryExtraction,
    LowerLeftGridCalibration,
    PcpPlotMetadata,
    cad_model_unit_scale_to_grid,
    read_dwg_geometry_bounds,
    read_pcp_plot_metadata,
)


DEFAULT_MADISON_CAD_SHEETS = (
    "E3-1A",
    "E3-1B",
    "E3-1C",
    "E3-1D",
    "E4-1A",
    "E4-1B",
    "E4-1C",
    "E4-1D",
    "E3-10",
)
DEFAULT_SITE_GRID_SHEETS = (
    "E3-1A",
    "E3-1B",
    "E3-1C",
    "E3-1D",
    "E4-1A",
    "E4-1B",
    "E4-1C",
    "E4-1D",
)
DEFAULT_BUILDING_GEOMETRY_SHEETS = (
    "E3-1A",
    "E3-1B",
    "E3-1C",
    "E3-1D",
)
DEFAULT_BUILDING_X_HISTOGRAM_BIN = Decimal("250")
DEFAULT_BUILDING_X_HISTOGRAM_THRESHOLD_RATIO = Decimal("0.02")
DEFAULT_BUILDING_MIN_SEGMENT_LENGTH = Decimal("500")
DEFAULT_MAX_ABS_DWG_COORDINATE = Decimal("10000000")

_CAD_FILENAME_RE = re.compile(
    r"^Enovum MAD1-Sheet - (?P<sheet>[A-Z]\d+(?:-\d+)?[A-Z]*) - (?P<title>.+)\.(?P<ext>dwg|pcp)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MadisonCadSheetSource:
    sheet_number: str
    title: str
    dwg_path: Path
    pcp_path: Path | None = None
    participates_in_site_grid: bool = False

    @property
    def role(self):
        if self.sheet_number == "E3-10":
            return "enlarged_electrical_plan"
        if "Generator Yard" in self.title:
            return "generator_yard_plan"
        if "Power Plan" in self.title:
            return "first_floor_power_plan"
        if "Auxiliary Systems Plan" in self.title:
            return "first_floor_auxiliary_plan"
        return "cad_plan"

    def to_manifest(self, root):
        return {
            "sheet_number": self.sheet_number,
            "title": self.title,
            "role": self.role,
            "participates_in_site_grid": self.participates_in_site_grid,
            "dwg_path": _relative_path(self.dwg_path, root),
            "pcp_path": _relative_path(self.pcp_path, root) if self.pcp_path else "",
        }


@dataclass(frozen=True)
class MadisonCadSheetAnalysis:
    source: MadisonCadSheetSource
    extraction: DwgGeometryExtraction | None = None
    pcp_metadata: PcpPlotMetadata | None = None
    error: str = ""

    @property
    def usable_for_site_grid(self):
        return self.source.participates_in_site_grid and self.extraction is not None and not self.error

    @property
    def bounds(self):
        return self.extraction.bounds if self.extraction is not None else None

    def to_manifest(self, root, *, source_units):
        data = self.source.to_manifest(root)
        data.update(
            {
                "status": "ok" if not self.error else "error",
                "error": self.error,
                "source_units": source_units or "",
                "pcp": self.pcp_metadata.to_metadata() if self.pcp_metadata is not None else None,
                "dwg_extraction": self.extraction.to_metadata() if self.extraction is not None else None,
            }
        )
        if self.extraction is not None and source_units:
            scale = cad_model_unit_scale_to_grid(source_units, GRID_UNIT_FEET)
            data["width_ft"] = _decimal_string(self.extraction.bounds.width * scale)
            data["height_ft"] = _decimal_string(self.extraction.bounds.height * scale)
        return data


@dataclass(frozen=True)
class MadisonCadCalibrationReport:
    cad_dir: Path
    sheet_analyses: tuple[MadisonCadSheetAnalysis, ...]
    source_units: str | None = None
    grid_units: str = GRID_UNIT_FEET
    proposed_structure_bounds: CoordinateBounds | None = None
    current_building_bounds: CoordinateBounds | None = None
    calibration: LowerLeftGridCalibration | None = None
    warnings: tuple[str, ...] = ()

    @property
    def status(self):
        if self.calibration is None:
            return "blocked"
        return "review_required"

    @property
    def usable_site_grid_sheets(self):
        return tuple(analysis for analysis in self.sheet_analyses if analysis.usable_for_site_grid)

    def to_manifest(self):
        current_building = None
        if self.current_building_bounds is not None:
            current_building = _current_building_manifest(
                self.current_building_bounds,
                site_bounds=self.proposed_structure_bounds,
                source_units=self.source_units,
            )
        return {
            "schema": "netbox_power_plant.madison_cad_calibration.v1",
            "status": self.status,
            "cad_dir": str(self.cad_dir),
            "source_units": self.source_units or "",
            "grid_units": self.grid_units,
            "axis_orientation": LOWER_LEFT_Y_UP,
            "coordinate_plane_bounds": (
                self.proposed_structure_bounds.to_metadata() if self.proposed_structure_bounds is not None else None
            ),
            "proposed_structure_bounds": (
                self.proposed_structure_bounds.to_metadata() if self.proposed_structure_bounds is not None else None
            ),
            "current_building": current_building,
            "calibration": self.calibration.to_metadata() if self.calibration is not None else None,
            "warnings": list(self.warnings),
            "sheets": [
                analysis.to_manifest(self.cad_dir, source_units=self.source_units)
                for analysis in self.sheet_analyses
            ],
        }

    def to_json(self):
        return json.dumps(self.to_manifest(), indent=2, sort_keys=True) + "\n"

    def to_markdown(self):
        lines = [
            "# Madison CAD Calibration Report",
            "",
            f"- Status: `{self.status}`",
            f"- CAD directory: `{self.cad_dir}`",
            f"- Source units: `{self.source_units or 'unconfirmed'}`",
            f"- Target grid: `{self.grid_units}`, `{LOWER_LEFT_Y_UP}`",
            "",
        ]
        if self.calibration is not None:
            lines.extend(
                [
                    "## Site Coordinate Plane",
                    "",
                    f"- Origin source X/Y: `{self.calibration.origin_source_x}`, `{self.calibration.origin_source_y}`",
                    f"- Width: `{self.calibration.width}` {self.grid_units}",
                    f"- Height: `{self.calibration.height}` {self.grid_units}",
                    f"- Confidence: `{self.calibration.confidence}` pending operator review",
                    "",
                ]
            )
        if self.current_building_bounds is not None:
            building = _current_building_manifest(
                self.current_building_bounds,
                site_bounds=self.proposed_structure_bounds,
                source_units=self.source_units,
            )
            lines.extend(
                [
                    "## Current Building Footprint",
                    "",
                    f"- Lower-left source X/Y: `{self.current_building_bounds.min_x}`, `{self.current_building_bounds.min_y}`",
                    f"- Origin in site grid: `{building['origin_in_site_grid']['x']}`, `{building['origin_in_site_grid']['y']}` {self.grid_units}",
                    f"- Width: `{building['width']}` {self.grid_units}",
                    f"- Height: `{building['height']}` {self.grid_units}",
                    f"- Inference: `{building['inference_method']}`",
                    "",
                ]
            )
        if self.warnings:
            lines.extend(["## Warnings", ""])
            lines.extend(f"- {warning}" for warning in self.warnings)
            lines.append("")

        lines.extend(
            [
                "## Sheet Analysis",
                "",
                "| Sheet | Role | Site grid | Status | Bounds | Size ft | Entities | Points discarded | PCP |",
                "|---|---|---:|---|---|---|---:|---:|---|",
            ]
        )
        for analysis in self.sheet_analyses:
            lines.append(_sheet_markdown_row(analysis, source_units=self.source_units))

        lines.extend(
            [
                "",
                "## Review Checklist",
                "",
                "- Confirm the CAD model unit assumption against AutoCAD drawing settings.",
                "- Confirm the site coordinate plane intentionally retains the west/left reserve and excludes title blocks or legends.",
                "- Confirm the inferred current building footprint matches the rendered structural elements in the authoritative CAD sheets.",
                "- Decide whether generator yards belong in the initial site grid or in child exterior frames.",
                "- Promote the reviewed bounds to authoritative before bulk rack or equipment placement.",
            ]
        )
        return "\n".join(lines) + "\n"


def discover_madison_cad_sources(
    cad_dir,
    *,
    sheet_numbers=DEFAULT_MADISON_CAD_SHEETS,
    site_grid_sheet_numbers=DEFAULT_SITE_GRID_SHEETS,
):
    root = Path(cad_dir)
    dwg_by_sheet = {}
    pcp_by_sheet = {}
    titles = {}
    requested = {sheet.upper() for sheet in sheet_numbers}
    site_grid = {sheet.upper() for sheet in site_grid_sheet_numbers}

    for path in root.glob("*"):
        if not path.is_file():
            continue
        match = _CAD_FILENAME_RE.match(path.name)
        if not match:
            continue
        sheet = match.group("sheet").upper()
        if sheet not in requested:
            continue
        titles[sheet] = match.group("title")
        if match.group("ext").lower() == "dwg":
            dwg_by_sheet[sheet] = path
        else:
            pcp_by_sheet[sheet] = path

    sources = []
    for sheet in sorted(requested, key=_sheet_sort_key):
        dwg_path = dwg_by_sheet.get(sheet)
        if dwg_path is None:
            continue
        sources.append(
            MadisonCadSheetSource(
                sheet_number=sheet,
                title=titles.get(sheet, ""),
                dwg_path=dwg_path,
                pcp_path=pcp_by_sheet.get(sheet),
                participates_in_site_grid=sheet in site_grid,
            )
        )
    return tuple(sources)


def build_madison_cad_calibration_report(
    cad_dir,
    *,
    source_units: str | None = "inch",
    sheet_numbers=DEFAULT_MADISON_CAD_SHEETS,
    site_grid_sheet_numbers=DEFAULT_SITE_GRID_SHEETS,
    building_geometry_sheet_numbers=DEFAULT_BUILDING_GEOMETRY_SHEETS,
    structure_bounds: CoordinateBounds | None = None,
    current_building_bounds: CoordinateBounds | None = None,
):
    sources = discover_madison_cad_sources(
        cad_dir,
        sheet_numbers=sheet_numbers,
        site_grid_sheet_numbers=site_grid_sheet_numbers,
    )
    analyses = tuple(_analyze_sheet(source) for source in sources)
    warnings = []
    if source_units:
        warnings.append(
            f"Source units are set to '{source_units}' for grid sizing. Confirm this against CAD drawing units."
        )
    else:
        warnings.append("Source units are unconfirmed; no physical grid can be finalized.")

    if any(analysis.pcp_metadata and analysis.pcp_metadata.uses_imperial_plot_units for analysis in analyses):
        warnings.append("PCP files use imperial plotting units, which supports but does not prove CAD model units.")

    usable = tuple(analysis for analysis in analyses if analysis.usable_for_site_grid)
    proposed_bounds = structure_bounds or _combined_bounds(analysis.bounds for analysis in usable)
    building_bounds = current_building_bounds
    if building_bounds is None and proposed_bounds is not None:
        building_bounds = _infer_current_building_bounds(
            analyses,
            site_bounds=proposed_bounds,
            building_geometry_sheet_numbers=building_geometry_sheet_numbers,
        )
    calibration = None
    if source_units and proposed_bounds is not None:
        scale = cad_model_unit_scale_to_grid(source_units, GRID_UNIT_FEET)
        calibration = LowerLeftGridCalibration(
            source_name="madison-cad-first-floor-composite",
            source_type="dwg",
            source_units=source_units,
            grid_units=GRID_UNIT_FEET,
            source_axis_orientation=LOWER_LEFT_Y_UP,
            structure_bounds=proposed_bounds,
            scale_x=scale,
            scale_y=scale,
            confidence=CONFIDENCE_DERIVED,
            warnings=(
                "Composite bounds are derived from first-floor CAD sheet geometry and require review.",
            ),
            provenance=tuple(str(analysis.source.dwg_path) for analysis in usable),
        )

    if not usable:
        warnings.append("No usable site-grid DWG sheets were extracted.")
    elif structure_bounds is None:
        warnings.append(
            "Site coordinate plane uses combined extents of selected first-floor sheets so westward future construction can remain in positive coordinates."
        )
    if building_bounds is not None and proposed_bounds is not None and source_units:
        origin = _source_point_to_site_grid(
            building_bounds.min_x,
            building_bounds.min_y,
            site_bounds=proposed_bounds,
            source_units=source_units,
        )
        warnings.append(
            f"Current building footprint origin is offset inside the site grid at x={origin[0]} {GRID_UNIT_FEET}, y={origin[1]} {GRID_UNIT_FEET}."
        )

    return MadisonCadCalibrationReport(
        cad_dir=Path(cad_dir),
        sheet_analyses=analyses,
        source_units=source_units,
        grid_units=GRID_UNIT_FEET,
        proposed_structure_bounds=proposed_bounds,
        current_building_bounds=building_bounds,
        calibration=calibration,
        warnings=tuple(warnings),
    )


def write_madison_cad_calibration_artifacts(report, *, manifest_path, markdown_path):
    manifest = Path(manifest_path)
    markdown = Path(markdown_path)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(report.to_json(), encoding="utf-8")
    markdown.write_text(report.to_markdown(), encoding="utf-8")


def _analyze_sheet(source):
    pcp_metadata = read_pcp_plot_metadata(source.pcp_path) if source.pcp_path else None
    try:
        extraction = read_dwg_geometry_bounds(source.dwg_path)
    except CadCalibrationError as exc:
        return MadisonCadSheetAnalysis(source=source, pcp_metadata=pcp_metadata, error=str(exc))
    return MadisonCadSheetAnalysis(source=source, extraction=extraction, pcp_metadata=pcp_metadata)


def _combined_bounds(bounds):
    usable = tuple(bound for bound in bounds if bound is not None)
    if not usable:
        return None
    return CoordinateBounds(
        min_x=min(bound.min_x for bound in usable),
        min_y=min(bound.min_y for bound in usable),
        max_x=max(bound.max_x for bound in usable),
        max_y=max(bound.max_y for bound in usable),
    )


def _infer_current_building_bounds(analyses, *, site_bounds, building_geometry_sheet_numbers):
    geometry_sheets = {sheet.upper() for sheet in building_geometry_sheet_numbers}
    segments = []
    for analysis in analyses:
        if analysis.source.sheet_number.upper() not in geometry_sheets:
            continue
        if analysis.error:
            continue
        segments.extend(_read_dwg_line_segments(analysis.source.dwg_path))
    if not segments:
        return None

    x_range = _dominant_x_range_after_left_reserve(segments)
    if x_range is None:
        return None
    min_x_range, max_x_range = x_range
    candidate_points = []
    for x1, y1, x2, y2, length in segments:
        if length < DEFAULT_BUILDING_MIN_SEGMENT_LENGTH:
            continue
        if max(x1, x2) < min_x_range:
            continue
        if min(x1, x2) > max_x_range:
            continue
        candidate_points.extend(((x1, y1), (x2, y2)))
    if not candidate_points:
        return None
    bounds = CoordinateBounds(
        min_x=min(point[0] for point in candidate_points),
        min_y=min(point[1] for point in candidate_points),
        max_x=max(point[0] for point in candidate_points),
        max_y=max(point[1] for point in candidate_points),
    )
    min_x = max(bounds.min_x, site_bounds.min_x)
    min_y = max(bounds.min_y, site_bounds.min_y)
    max_x = min(bounds.max_x, site_bounds.max_x)
    max_y = min(bounds.max_y, site_bounds.max_y)
    if max_x <= min_x or max_y <= min_y:
        return None
    return CoordinateBounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def _dominant_x_range_after_left_reserve(segments):
    histogram = {}
    bin_size = DEFAULT_BUILDING_X_HISTOGRAM_BIN
    for x1, _y1, x2, _y2, length in segments:
        min_x = min(x1, x2)
        max_x = max(x1, x2)
        start = int((min_x / bin_size).to_integral_value(rounding=ROUND_FLOOR))
        end = int((max_x / bin_size).to_integral_value(rounding=ROUND_FLOOR))
        span = max(end - start + 1, 1)
        for index in range(start, end + 1):
            histogram[index] = histogram.get(index, Decimal("0")) + (length / span)
    if not histogram:
        return None
    threshold = max(histogram.values()) * DEFAULT_BUILDING_X_HISTOGRAM_THRESHOLD_RATIO
    occupied = sorted(index for index, value in histogram.items() if value >= threshold)
    ranges = _contiguous_ranges(occupied, bin_size=bin_size)
    if not ranges:
        return None
    return max(ranges, key=lambda item: item[1] - item[0])


def _contiguous_ranges(indexes, *, bin_size):
    if not indexes:
        return ()
    ranges = []
    start = previous = indexes[0]
    for index in indexes[1:]:
        if index == previous + 1:
            previous = index
            continue
        ranges.append((Decimal(start) * bin_size, Decimal(previous + 1) * bin_size))
        start = previous = index
    ranges.append((Decimal(start) * bin_size, Decimal(previous + 1) * bin_size))
    return tuple(ranges)


def _read_dwg_line_segments(path):
    ezdwg = import_module("ezdwg")
    segments = []
    doc = ezdwg.read(str(path))
    for entity in doc.modelspace().query("LINE"):
        dxf = getattr(entity, "dxf", {}) or {}
        start = _point2(dxf.get("start"))
        end = _point2(dxf.get("end"))
        if start is None or end is None:
            continue
        length = _segment_length(start, end)
        if length <= 0:
            continue
        segments.append((start[0], start[1], end[0], end[1], length))
    return tuple(segments)


def _point2(point):
    if point is None or len(point) < 2:
        return None
    try:
        x = Decimal(str(point[0]))
        y = Decimal(str(point[1]))
    except Exception:
        return None
    if abs(x) > DEFAULT_MAX_ABS_DWG_COORDINATE or abs(y) > DEFAULT_MAX_ABS_DWG_COORDINATE:
        return None
    return x, y


def _segment_length(start, end):
    return Decimal(str(math.hypot(float(end[0] - start[0]), float(end[1] - start[1]))))


def _current_building_manifest(building_bounds, *, site_bounds, source_units):
    data = {
        "source_bounds": building_bounds.to_metadata(),
        "inference_method": (
            "largest occupied post-gap x-range from first-floor E3 rendered structural linework; "
            "site plane retains west/left reserve."
        ),
    }
    if site_bounds is not None and source_units:
        origin_x, origin_y = _source_point_to_site_grid(
            building_bounds.min_x,
            building_bounds.min_y,
            site_bounds=site_bounds,
            source_units=source_units,
        )
        scale = cad_model_unit_scale_to_grid(source_units, GRID_UNIT_FEET)
        data.update(
            {
                "origin_in_site_grid": {"x": origin_x, "y": origin_y, "units": GRID_UNIT_FEET},
                "width": _decimal_string(building_bounds.width * scale),
                "height": _decimal_string(building_bounds.height * scale),
            }
        )
    return data


def _source_point_to_site_grid(x, y, *, site_bounds, source_units):
    scale = cad_model_unit_scale_to_grid(source_units, GRID_UNIT_FEET)
    return (
        _decimal_string((x - site_bounds.min_x) * scale),
        _decimal_string((y - site_bounds.min_y) * scale),
    )


def _sheet_markdown_row(analysis, *, source_units):
    status = "error" if analysis.error else "ok"
    bounds = ""
    size = ""
    entities = ""
    discarded = ""
    if analysis.extraction is not None:
        bounds = _bounds_inline(analysis.extraction.bounds)
        entities = str(analysis.extraction.entity_count)
        discarded = str(analysis.extraction.discarded_point_count)
        if source_units:
            scale = cad_model_unit_scale_to_grid(source_units, GRID_UNIT_FEET)
            size = f"{_decimal_string(analysis.extraction.bounds.width * scale)} x {_decimal_string(analysis.extraction.bounds.height * scale)}"
    pcp = ""
    if analysis.pcp_metadata is not None:
        pcp = f"{analysis.pcp_metadata.units} / {analysis.pcp_metadata.scale}"
    return (
        f"| {analysis.source.sheet_number} | {analysis.source.role} | "
        f"{'yes' if analysis.source.participates_in_site_grid else 'no'} | {status} | "
        f"{bounds or analysis.error} | {size} | {entities} | {discarded} | {pcp} |"
    )


def _bounds_inline(bounds):
    return (
        f"{_decimal_string(bounds.min_x)}, {_decimal_string(bounds.min_y)} -> "
        f"{_decimal_string(bounds.max_x)}, {_decimal_string(bounds.max_y)}"
    )


def _relative_path(path, root):
    if path is None:
        return ""
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def _sheet_sort_key(sheet):
    return tuple(_sort_part(part) for part in re.split(r"([0-9]+)", sheet))


def _sort_part(value):
    return int(value) if value.isdecimal() else value


def _decimal_string(value):
    return f"{Decimal(value).quantize(Decimal('0.001')):f}"
