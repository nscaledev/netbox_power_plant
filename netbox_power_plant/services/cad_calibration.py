from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from importlib import import_module
from pathlib import Path


LOWER_LEFT_Y_UP = "lower-left-x-right-y-up"
UPPER_LEFT_Y_DOWN = "upper-left-x-right-y-down"

CONFIDENCE_AUTHORITATIVE = "authoritative"
CONFIDENCE_DERIVED = "derived"
CONFIDENCE_PROVISIONAL = "provisional"

GRID_UNIT_FEET = "ft"
GRID_UNIT_SVG = "gs001_svg_unit"
DEFAULT_DWG_ENTITY_TYPES = ("LINE", "LWPOLYLINE", "ARC", "CIRCLE", "ELLIPSE", "POINT")
DEFAULT_MAX_ABS_DWG_COORDINATE = Decimal("10000000")

CAD_MODEL_UNIT_TO_FEET = {
    "inch": Decimal("0.08333333333333333333333333333"),
    "in": Decimal("0.08333333333333333333333333333"),
    "foot": Decimal("1"),
    "feet": Decimal("1"),
    "ft": Decimal("1"),
    "millimeter": Decimal("0.003280839895013123359580052493"),
    "millimetre": Decimal("0.003280839895013123359580052493"),
    "mm": Decimal("0.003280839895013123359580052493"),
    "centimeter": Decimal("0.03280839895013123359580052493"),
    "centimetre": Decimal("0.03280839895013123359580052493"),
    "cm": Decimal("0.03280839895013123359580052493"),
    "meter": Decimal("3.280839895013123359580052493"),
    "metre": Decimal("3.280839895013123359580052493"),
    "m": Decimal("3.280839895013123359580052493"),
}

DXF_INSUNITS_TO_MODEL_UNIT = {
    1: "inch",
    2: "foot",
    4: "millimeter",
    5: "centimeter",
    6: "meter",
}


class CadCalibrationError(ValueError):
    pass


@dataclass(frozen=True)
class CoordinateBounds:
    min_x: Decimal
    min_y: Decimal
    max_x: Decimal
    max_y: Decimal

    def __post_init__(self):
        if self.max_x <= self.min_x:
            raise CadCalibrationError("bounds max_x must be greater than min_x.")
        if self.max_y <= self.min_y:
            raise CadCalibrationError("bounds max_y must be greater than min_y.")

    @property
    def width(self):
        return self.max_x - self.min_x

    @property
    def height(self):
        return self.max_y - self.min_y

    def to_metadata(self):
        return {
            "min_x": _decimal_string(self.min_x),
            "min_y": _decimal_string(self.min_y),
            "max_x": _decimal_string(self.max_x),
            "max_y": _decimal_string(self.max_y),
            "width": _decimal_string(self.width),
            "height": _decimal_string(self.height),
        }

    @classmethod
    def from_values(cls, min_x, min_y, max_x, max_y):
        return cls(_decimal(min_x), _decimal(min_y), _decimal(max_x), _decimal(max_y))


@dataclass(frozen=True)
class PcpPlotMetadata:
    path: str
    units: str = ""
    origin: str = ""
    size: str = ""
    rotate: str = ""
    scale: str = ""

    @property
    def uses_imperial_plot_units(self):
        return self.units == "_I"

    def to_metadata(self):
        return {
            "path": self.path,
            "units": self.units,
            "origin": self.origin,
            "size": self.size,
            "rotate": self.rotate,
            "scale": self.scale,
            "uses_imperial_plot_units": self.uses_imperial_plot_units,
        }


@dataclass(frozen=True)
class DwgGeometryExtraction:
    path: str
    decode_version: str
    entity_count: int
    point_count: int
    discarded_point_count: int
    entity_type_counts: dict
    bounds: CoordinateBounds

    def to_metadata(self):
        return {
            "path": self.path,
            "decode_version": self.decode_version,
            "entity_count": self.entity_count,
            "point_count": self.point_count,
            "discarded_point_count": self.discarded_point_count,
            "entity_type_counts": dict(self.entity_type_counts),
            "bounds": self.bounds.to_metadata(),
        }


@dataclass(frozen=True)
class LowerLeftGridCalibration:
    source_name: str
    source_type: str
    source_units: str
    grid_units: str
    source_axis_orientation: str
    structure_bounds: CoordinateBounds
    scale_x: Decimal
    scale_y: Decimal
    confidence: str
    model_bounds: CoordinateBounds | None = None
    pcp_metadata: PcpPlotMetadata | None = None
    dwg_extraction: DwgGeometryExtraction | None = None
    warnings: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()

    @property
    def width(self):
        return _quantize(self.structure_bounds.width * self.scale_x)

    @property
    def height(self):
        return _quantize(self.structure_bounds.height * self.scale_y)

    @property
    def origin_source_x(self):
        return self.structure_bounds.min_x

    @property
    def origin_source_y(self):
        if self.source_axis_orientation == UPPER_LEFT_Y_DOWN:
            return self.structure_bounds.max_y
        return self.structure_bounds.min_y

    def source_to_grid(self, x, y):
        source_x = _decimal(x)
        source_y = _decimal(y)
        grid_x = (source_x - self.structure_bounds.min_x) * self.scale_x
        if self.source_axis_orientation == UPPER_LEFT_Y_DOWN:
            grid_y = (self.structure_bounds.max_y - source_y) * self.scale_y
        else:
            grid_y = (source_y - self.structure_bounds.min_y) * self.scale_y
        return _quantize(grid_x), _quantize(grid_y)

    def grid_to_source(self, x, y):
        grid_x = _decimal(x)
        grid_y = _decimal(y)
        source_x = (grid_x / self.scale_x) + self.structure_bounds.min_x
        if self.source_axis_orientation == UPPER_LEFT_Y_DOWN:
            source_y = self.structure_bounds.max_y - (grid_y / self.scale_y)
        else:
            source_y = (grid_y / self.scale_y) + self.structure_bounds.min_y
        return _quantize(source_x), _quantize(source_y)

    def to_metadata(self):
        metadata = {
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_units": self.source_units,
            "grid_units": self.grid_units,
            "source_axis_orientation": self.source_axis_orientation,
            "target_axis_orientation": LOWER_LEFT_Y_UP,
            "origin": {
                "description": "Lower-left corner of the calibrated source bounds.",
                "source_x": _decimal_string(self.origin_source_x),
                "source_y": _decimal_string(self.origin_source_y),
                "grid_x": "0.000",
                "grid_y": "0.000",
            },
            "structure_bounds": self.structure_bounds.to_metadata(),
            "scale_x": _decimal_string(self.scale_x),
            "scale_y": _decimal_string(self.scale_y),
            "width": _decimal_string(self.width),
            "height": _decimal_string(self.height),
            "confidence": self.confidence,
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
        }
        if self.model_bounds is not None:
            metadata["model_bounds"] = self.model_bounds.to_metadata()
        if self.pcp_metadata is not None:
            metadata["pcp"] = self.pcp_metadata.to_metadata()
        if self.dwg_extraction is not None:
            metadata["dwg_extraction"] = self.dwg_extraction.to_metadata()
        return metadata


def build_cad_lower_left_grid_calibration(
    *,
    source_path,
    structure_bounds: CoordinateBounds | None = None,
    model_bounds: CoordinateBounds | None = None,
    source_units: str | None = None,
    pcp_path=None,
    grid_units: str = GRID_UNIT_FEET,
    confidence: str = CONFIDENCE_AUTHORITATIVE,
) -> LowerLeftGridCalibration:
    """
    Build an operator-facing lower-left grid from CAD model-space bounds.

    DWG parsing uses the mandatory `ezdwg` dependency when bounds are not supplied.
    Callers can still pass a cropped structure_bounds value when the full drawing
    includes title blocks, legends, or off-building geometry.
    """
    source = Path(source_path)
    pcp_metadata = read_pcp_plot_metadata(pcp_path) if pcp_path else None
    warnings = []
    provenance = [str(source)]
    if pcp_metadata is not None:
        provenance.append(pcp_metadata.path)

    dxf_header = {}
    dwg_extraction = None
    if source.suffix.lower() == ".dxf":
        dxf_header = read_dxf_header_metadata(source)
        if model_bounds is None:
            model_bounds = dxf_header.get("extents")
        if structure_bounds is None:
            structure_bounds = model_bounds
        if source_units is None:
            source_units = dxf_header.get("source_units")
    elif source.suffix.lower() == ".dwg" and model_bounds is None and structure_bounds is None:
        dwg_extraction = read_dwg_geometry_bounds(source)
        if model_bounds is None:
            model_bounds = dwg_extraction.bounds
        if structure_bounds is None:
            structure_bounds = model_bounds
        if dwg_extraction.discarded_point_count:
            warnings.append(
                f"Discarded {dwg_extraction.discarded_point_count} outlier DWG geometry point(s) "
                "while deriving model bounds."
            )
    elif source.suffix.lower() == ".dwg" and model_bounds is None:
        model_bounds = structure_bounds

    if source.suffix.lower() == ".dwg" and structure_bounds is None:
        raise CadCalibrationError(
            "DWG geometry could not be read. Verify the netbox_power_plant installation includes ezdwg "
            "or pass CAD-extracted structure_bounds."
        )

    if structure_bounds is None:
        raise CadCalibrationError("structure_bounds are required when CAD extents are not available.")

    if source_units is None:
        if pcp_metadata is not None and pcp_metadata.uses_imperial_plot_units:
            warnings.append(
                "PCP metadata confirms imperial plotting but does not prove the CAD model unit; "
                "pass source_units from the CAD drawing before treating the grid as authoritative."
            )
        raise CadCalibrationError("source_units are required for physical CAD calibration.")

    scale = _unit_scale_to_grid(source_units, grid_units)
    if source.suffix.lower() == ".dwg":
        warnings.append(
            "DWG bounds are high-level geometry bounds. Use structure_bounds to crop to the physical "
            "building outline when title blocks, legends, or non-building geometry are present."
        )

    return LowerLeftGridCalibration(
        source_name=source.name,
        source_type=source.suffix.lower().lstrip(".") or "cad",
        source_units=_normalize_unit(source_units),
        grid_units=grid_units,
        source_axis_orientation=LOWER_LEFT_Y_UP,
        structure_bounds=structure_bounds,
        model_bounds=model_bounds,
        scale_x=scale,
        scale_y=scale,
        confidence=confidence,
        pcp_metadata=pcp_metadata,
        dwg_extraction=dwg_extraction,
        warnings=tuple(warnings),
        provenance=tuple(provenance),
    )


def build_svg_overlay_grid_calibration(
    *,
    svg_path,
    target_grid: LowerLeftGridCalibration,
    svg_bounds: CoordinateBounds | None = None,
) -> LowerLeftGridCalibration:
    """
    Map an approximate SVG overlay onto an authoritative CAD-derived grid.
    """
    source = Path(svg_path)
    bounds = svg_bounds or read_svg_viewbox_bounds(source)
    return LowerLeftGridCalibration(
        source_name=source.name,
        source_type="svg",
        source_units=GRID_UNIT_SVG,
        grid_units=target_grid.grid_units,
        source_axis_orientation=UPPER_LEFT_Y_DOWN,
        structure_bounds=bounds,
        scale_x=target_grid.width / bounds.width,
        scale_y=target_grid.height / bounds.height,
        confidence=CONFIDENCE_PROVISIONAL,
        warnings=(
            "SVG overlay coordinates are approximate; CAD-derived coordinates remain authoritative.",
        ),
        provenance=(str(source), *target_grid.provenance),
    )


def build_source_unit_svg_grid_calibration(*, svg_path, grid_units: str = GRID_UNIT_SVG):
    source = Path(svg_path)
    bounds = read_svg_viewbox_bounds(source)
    return LowerLeftGridCalibration(
        source_name=source.name,
        source_type="svg",
        source_units=GRID_UNIT_SVG,
        grid_units=grid_units,
        source_axis_orientation=UPPER_LEFT_Y_DOWN,
        structure_bounds=bounds,
        scale_x=Decimal("1"),
        scale_y=Decimal("1"),
        confidence=CONFIDENCE_PROVISIONAL,
        warnings=(
            "This grid is source-unit only. Use CAD-derived bounds before treating dimensions as physical.",
        ),
        provenance=(str(source),),
    )


def read_pcp_plot_metadata(path) -> PcpPlotMetadata:
    pcp_path = Path(path)
    values = {}
    with pcp_path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "=" not in line or line.lstrip().startswith(";"):
                continue
            key, value = line.split("=", 1)
            values[key.strip().upper()] = value.strip()
    return PcpPlotMetadata(
        path=str(pcp_path),
        units=values.get("UNITS", ""),
        origin=values.get("ORIGIN", ""),
        size=values.get("SIZE", ""),
        rotate=values.get("ROTATE", ""),
        scale=values.get("SCALE", ""),
    )


def read_dwg_geometry_bounds(
    path,
    *,
    entity_types=DEFAULT_DWG_ENTITY_TYPES,
    max_abs_coordinate=DEFAULT_MAX_ABS_DWG_COORDINATE,
) -> DwgGeometryExtraction:
    dwg_path = Path(path)
    try:
        ezdwg = import_module("ezdwg")
    except ImportError as exc:
        raise CadCalibrationError(
            "DWG reading requires ezdwg, which is a mandatory netbox_power_plant dependency."
        ) from exc

    doc = ezdwg.read(str(dwg_path))
    modelspace = doc.modelspace()
    query = " ".join(entity_types)
    points = []
    discarded = 0
    entity_count = 0
    point_count = 0
    entity_type_counts = {}

    for entity in modelspace.query(query):
        entity_count += 1
        entity_type = str(getattr(entity, "dxftype", "") or "").upper()
        entity_type_counts[entity_type] = entity_type_counts.get(entity_type, 0) + 1
        for point in _entity_candidate_points(entity_type, getattr(entity, "dxf", {}) or {}):
            point_count += 1
            if _is_usable_dwg_point(point, max_abs_coordinate=max_abs_coordinate):
                points.append((_decimal(point[0]), _decimal(point[1])))
            else:
                discarded += 1

    if not points:
        raise CadCalibrationError(f"No usable DWG geometry points were found in {dwg_path}.")

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bounds = CoordinateBounds(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))
    return DwgGeometryExtraction(
        path=str(dwg_path),
        decode_version=str(getattr(doc, "decode_version", "") or getattr(doc, "version", "") or ""),
        entity_count=entity_count,
        point_count=point_count,
        discarded_point_count=discarded,
        entity_type_counts=entity_type_counts,
        bounds=bounds,
    )


def read_svg_viewbox_bounds(path) -> CoordinateBounds:
    svg_path = Path(path)
    root = ET.parse(svg_path).getroot()
    view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
    if view_box:
        parts = [_decimal(part) for part in re.split(r"[\s,]+", view_box.strip()) if part]
        if len(parts) == 4:
            min_x, min_y, width, height = parts
            return CoordinateBounds(min_x=min_x, min_y=min_y, max_x=min_x + width, max_y=min_y + height)
    width = _svg_length(root.attrib.get("width"))
    height = _svg_length(root.attrib.get("height"))
    if width is None or height is None:
        raise CadCalibrationError(f"SVG {svg_path} does not expose a usable viewBox or width/height.")
    return CoordinateBounds.from_values(0, 0, width, height)


def read_dxf_header_metadata(path):
    dxf_path = Path(path)
    pairs = _read_dxf_pairs(dxf_path)
    values = {}
    index = 0
    while index < len(pairs):
        code, value = pairs[index]
        if code != "9":
            index += 1
            continue
        variable = value.strip().upper()
        index += 1
        variable_pairs = []
        while index < len(pairs) and pairs[index][0] != "9":
            variable_pairs.append(pairs[index])
            index += 1
        values[variable] = variable_pairs

    extents = _dxf_extents(values.get("$EXTMIN"), values.get("$EXTMAX"))
    source_units = _dxf_units(values.get("$INSUNITS"))
    return {"extents": extents, "source_units": source_units}


def cad_model_unit_scale_to_grid(source_units, grid_units=GRID_UNIT_FEET):
    return _unit_scale_to_grid(source_units, grid_units)


def _entity_candidate_points(entity_type, dxf):
    if entity_type == "LINE":
        return _present_points(dxf.get("start"), dxf.get("end"))
    if entity_type == "POINT":
        return _present_points(dxf.get("location"), dxf.get("point"), dxf.get("insert"))
    if entity_type == "LWPOLYLINE":
        return tuple(dxf.get("points") or dxf.get("vertices") or ())
    if entity_type in {"CIRCLE", "ARC"}:
        center = dxf.get("center")
        radius = dxf.get("radius")
        if center is None or radius in (None, ""):
            return ()
        center_x = _decimal(center[0])
        center_y = _decimal(center[1])
        radius = _decimal(radius)
        return (
            (center_x - radius, center_y - radius),
            (center_x + radius, center_y + radius),
        )
    if entity_type == "ELLIPSE":
        center = dxf.get("center")
        major_axis = dxf.get("major_axis")
        ratio = dxf.get("ratio") or dxf.get("axis_ratio") or 1
        if center is None or major_axis is None:
            return _present_points(center)
        center_x = _decimal(center[0])
        center_y = _decimal(center[1])
        major_radius = max(abs(_decimal(major_axis[0])), abs(_decimal(major_axis[1])))
        minor_radius = major_radius * _decimal(ratio)
        radius = max(major_radius, minor_radius)
        return (
            (center_x - radius, center_y - radius),
            (center_x + radius, center_y + radius),
        )
    return ()


def _present_points(*points):
    return tuple(point for point in points if point is not None)


def _is_usable_dwg_point(point, *, max_abs_coordinate):
    if point is None or len(point) < 2:
        return False
    try:
        x = _decimal(point[0])
        y = _decimal(point[1])
    except CadCalibrationError:
        return False
    return abs(x) <= max_abs_coordinate and abs(y) <= max_abs_coordinate


def _read_dxf_pairs(path):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    pairs = []
    for index in range(0, len(lines) - 1, 2):
        pairs.append((lines[index].strip(), lines[index + 1].strip()))
    return pairs


def _dxf_extents(extmin_pairs, extmax_pairs):
    if not extmin_pairs or not extmax_pairs:
        return None
    min_values = _dxf_point(extmin_pairs)
    max_values = _dxf_point(extmax_pairs)
    if min_values is None or max_values is None:
        return None
    return CoordinateBounds.from_values(min_values[0], min_values[1], max_values[0], max_values[1])


def _dxf_point(pairs):
    values = {}
    for code, value in pairs:
        if code in {"10", "20", "30"}:
            values[code] = value
    if "10" not in values or "20" not in values:
        return None
    return values["10"], values["20"]


def _dxf_units(insunits_pairs):
    if not insunits_pairs:
        return None
    for code, value in insunits_pairs:
        if code == "70":
            try:
                return DXF_INSUNITS_TO_MODEL_UNIT.get(int(value))
            except ValueError:
                return None
    return None


def _unit_scale_to_grid(source_units, grid_units):
    normalized_source = _normalize_unit(source_units)
    normalized_grid = _normalize_unit(grid_units)
    if normalized_grid != GRID_UNIT_FEET:
        if normalized_source == normalized_grid:
            return Decimal("1")
        raise CadCalibrationError(f"unsupported target grid unit: {grid_units}.")
    try:
        return CAD_MODEL_UNIT_TO_FEET[normalized_source]
    except KeyError as exc:
        raise CadCalibrationError(f"unsupported CAD model unit: {source_units}.") from exc


def _normalize_unit(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _svg_length(value):
    if value in (None, ""):
        return None
    match = re.match(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", str(value))
    if not match:
        return None
    return _decimal(match.group(1))


def _decimal(value):
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise CadCalibrationError(f"{value!r} is not a decimal value.") from exc


def _quantize(value):
    return Decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _decimal_string(value):
    return f"{_quantize(value):f}"
