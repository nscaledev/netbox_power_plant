#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import ezdwg
from PIL import Image, ImageDraw, ImageFont


MODEL_MAX_ABS = 10_000_000
PRIMARY_GEOMETRY_SHEETS = {"E3-1A", "E3-1B", "E3-1C", "E3-1D"}
SHEET_COLORS = {
    "E3-1A": (32, 113, 181, 255),
    "E3-1B": (44, 162, 95, 255),
    "E3-1C": (230, 85, 13, 255),
    "E3-1D": (117, 107, 177, 255),
    "E4-1A": (49, 130, 189, 180),
    "E4-1B": (35, 139, 69, 180),
    "E4-1C": (253, 141, 60, 180),
    "E4-1D": (106, 81, 163, 180),
}


def main():
    parser = argparse.ArgumentParser(description="Render Madison CAD crop/unit assumptions as a PNG.")
    parser.add_argument("--manifest", required=True, help="madison_cad_calibration_manifest.json")
    parser.add_argument("--out", required=True, help="Output PNG path")
    parser.add_argument("--width", type=int, default=2400)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image = render_manifest(manifest, manifest_path=manifest_path, width=args.width, height=args.height)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    print(out_path)


def render_manifest(manifest, *, manifest_path, width, height):
    cad_dir = Path(manifest["cad_dir"])
    bounds = _bounds(manifest.get("coordinate_plane_bounds") or manifest["proposed_structure_bounds"])
    current_building = manifest.get("current_building") or {}
    source_units = manifest.get("source_units") or "unconfirmed"
    grid_units = manifest.get("grid_units") or "ft"
    calibration = manifest.get("calibration") or {}
    sheet_entries = manifest.get("sheets") or []

    margin_left = 96
    margin_right = 72
    margin_top = 120
    margin_bottom = 130
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    scale = min(plot_w / bounds["width"], plot_h / bounds["height"])
    actual_w = bounds["width"] * scale
    actual_h = bounds["height"] * scale
    plot_x = margin_left + (plot_w - actual_w) / 2
    plot_y = margin_top + (plot_h - actual_h) / 2

    image = Image.new("RGBA", (width, height), (249, 250, 252, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    fonts = _fonts()

    _draw_header(draw, fonts, width, manifest, source_units, grid_units)
    _draw_geometry(draw, cad_dir, sheet_entries, bounds, plot_x, plot_y, scale)
    _draw_sheet_bounds(draw, sheet_entries, bounds, plot_x, plot_y, scale, fonts)
    _draw_current_building(draw, current_building, bounds, plot_x, plot_y, scale, fonts)
    _draw_crop_and_axes(draw, bounds, plot_x, plot_y, actual_w, actual_h, scale, fonts)
    _draw_scale_bar(draw, bounds, plot_x, plot_y, actual_h, scale, fonts)
    _draw_footer(draw, fonts, width, height, manifest_path, calibration, current_building)

    return image.convert("RGB")


def _draw_header(draw, fonts, width, manifest, source_units, grid_units):
    title = "Madison CAD site grid and building-origin assumptions"
    subtitle = (
        f"Status: {manifest.get('status')}   |   Source units: {source_units}   |   "
        f"Grid units: {grid_units}   |   Axis: {manifest.get('axis_orientation')}"
    )
    draw.text((40, 28), title, fill=(22, 34, 51, 255), font=fonts["title"])
    draw.text((40, 72), subtitle, fill=(74, 85, 104, 255), font=fonts["body"])
    warning = "Outer grid preserves west/left reserve; blue footprint is the current rendered building."
    draw.text((width - 40, 72), warning, fill=(174, 75, 0, 255), font=fonts["body"], anchor="ra")


def _draw_geometry(draw, cad_dir, sheet_entries, bounds, plot_x, plot_y, scale):
    geometry_color = (65, 75, 90, 34)
    for sheet in sheet_entries:
        sheet_number = sheet.get("sheet_number")
        if sheet_number not in PRIMARY_GEOMETRY_SHEETS:
            continue
        dwg_path = cad_dir / sheet["dwg_path"]
        for segment in _iter_dwg_segments(dwg_path):
            p1, p2 = segment
            if not (_point_near_bounds(p1, bounds) and _point_near_bounds(p2, bounds)):
                continue
            draw.line(
                (
                    *_to_pixel(p1[0], p1[1], bounds, plot_x, plot_y, scale),
                    *_to_pixel(p2[0], p2[1], bounds, plot_x, plot_y, scale),
                ),
                fill=geometry_color,
                width=1,
            )


def _draw_sheet_bounds(draw, sheet_entries, bounds, plot_x, plot_y, scale, fonts):
    for sheet in sheet_entries:
        extraction = sheet.get("dwg_extraction")
        if not extraction:
            continue
        sheet_bounds = _bounds(extraction["bounds"])
        color = SHEET_COLORS.get(sheet["sheet_number"], (100, 116, 139, 160))
        x1, y1 = _to_pixel(sheet_bounds["min_x"], sheet_bounds["min_y"], bounds, plot_x, plot_y, scale)
        x2, y2 = _to_pixel(sheet_bounds["max_x"], sheet_bounds["max_y"], bounds, plot_x, plot_y, scale)
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        _draw_dashed_rectangle(draw, (left, top, right, bottom), color=color, width=3)
        label = sheet["sheet_number"]
        draw.rectangle((left + 6, top + 6, left + 72, top + 30), fill=(255, 255, 255, 210))
        draw.text((left + 12, top + 9), label, fill=color, font=fonts["small"])


def _draw_current_building(draw, current_building, bounds, plot_x, plot_y, scale, fonts):
    source_bounds = current_building.get("source_bounds")
    if not source_bounds:
        return
    building = _bounds(source_bounds)
    x1, y1 = _to_pixel(building["min_x"], building["min_y"], bounds, plot_x, plot_y, scale)
    x2, y2 = _to_pixel(building["max_x"], building["max_y"], bounds, plot_x, plot_y, scale)
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))

    outline = (37, 99, 235, 255)
    draw.rectangle((left, top, right, bottom), outline=outline, width=5)

    label = "current building footprint"
    label_w = _text_width(draw, label, fonts["body"]) + 24
    label_h = 34
    label_x = min(left + 12, right - label_w - 8)
    label_y = max(top + 12, 112)
    draw.rectangle((label_x, label_y, label_x + label_w, label_y + label_h), fill=(255, 255, 255, 230))
    draw.text((label_x + 12, label_y + 7), label, fill=outline, font=fonts["body"])

    origin = current_building.get("origin_in_site_grid") or {}
    if origin:
        marker = (left, bottom)
        draw.ellipse((marker[0] - 7, marker[1] - 7, marker[0] + 7, marker[1] + 7), fill=outline)
        origin_label = f"building origin: ({origin.get('x')}, {origin.get('y')}) {origin.get('units', 'ft')}"
        draw.rectangle(
            (marker[0] + 12, marker[1] - 48, marker[0] + 408, marker[1] - 16),
            fill=(255, 255, 255, 230),
        )
        draw.text((marker[0] + 22, marker[1] - 42), origin_label, fill=outline, font=fonts["small"])


def _draw_crop_and_axes(draw, bounds, plot_x, plot_y, actual_w, actual_h, scale, fonts):
    crop = (plot_x, plot_y, plot_x + actual_w, plot_y + actual_h)
    draw.rectangle(crop, outline=(220, 38, 38, 255), width=5)
    draw.text((plot_x + 12, plot_y + 12), "site coordinate plane", fill=(185, 28, 28, 255), font=fonts["body"])

    origin = (plot_x, plot_y + actual_h)
    draw.ellipse((origin[0] - 7, origin[1] - 7, origin[0] + 7, origin[1] + 7), fill=(185, 28, 28, 255))
    draw.text((origin[0] + 12, origin[1] - 24), "site origin: lower-left", fill=(185, 28, 28, 255), font=fonts["body"])
    draw.text(
        (origin[0] + 12, origin[1] - 3),
        f"source ({bounds['min_x']:.3f}, {bounds['min_y']:.3f})",
        fill=(185, 28, 28, 255),
        font=fonts["small"],
    )

    arrow_len = min(260, actual_w * 0.16)
    draw.line((origin[0], origin[1], origin[0] + arrow_len, origin[1]), fill=(22, 101, 52, 255), width=4)
    draw.polygon(
        ((origin[0] + arrow_len, origin[1]), (origin[0] + arrow_len - 14, origin[1] - 7), (origin[0] + arrow_len - 14, origin[1] + 7)),
        fill=(22, 101, 52, 255),
    )
    draw.text((origin[0] + arrow_len + 8, origin[1] - 11), "+X", fill=(22, 101, 52, 255), font=fonts["body"])

    y_arrow = min(190, actual_h * 0.28)
    draw.line((origin[0], origin[1], origin[0], origin[1] - y_arrow), fill=(29, 78, 216, 255), width=4)
    draw.polygon(
        ((origin[0], origin[1] - y_arrow), (origin[0] - 7, origin[1] - y_arrow + 14), (origin[0] + 7, origin[1] - y_arrow + 14)),
        fill=(29, 78, 216, 255),
    )
    draw.text((origin[0] + 10, origin[1] - y_arrow - 12), "+Y", fill=(29, 78, 216, 255), font=fonts["body"])


def _draw_scale_bar(draw, bounds, plot_x, plot_y, actual_h, scale, fonts):
    cad_units_per_100_ft = 1200
    bar_w = cad_units_per_100_ft * scale
    x = plot_x + 42
    y = plot_y + actual_h + 58
    draw.line((x, y, x + bar_w, y), fill=(15, 23, 42, 255), width=5)
    draw.line((x, y - 10, x, y + 10), fill=(15, 23, 42, 255), width=3)
    draw.line((x + bar_w, y - 10, x + bar_w, y + 10), fill=(15, 23, 42, 255), width=3)
    draw.text((x, y + 16), "100 ft = 1200 CAD units", fill=(15, 23, 42, 255), font=fonts["small"])
    draw.text((x + 360, y + 16), "assumption: CAD model units are inches", fill=(174, 75, 0, 255), font=fonts["small"])


def _draw_footer(draw, fonts, width, height, manifest_path, calibration, current_building):
    if calibration:
        text = f"Derived grid size: {calibration.get('width')} ft x {calibration.get('height')} ft"
        draw.text((40, height - 54), text, fill=(22, 34, 51, 255), font=fonts["body"])
    origin = (current_building.get("origin_in_site_grid") or {}) if current_building else {}
    if origin:
        text = f"Current building origin in site grid: x={origin.get('x')} {origin.get('units', 'ft')}, y={origin.get('y')} {origin.get('units', 'ft')}"
        draw.text((40, height - 28), text, fill=(37, 99, 235, 255), font=fonts["small"])
    draw.text((width - 40, height - 54), str(manifest_path), fill=(100, 116, 139, 255), font=fonts["small"], anchor="ra")


def _iter_dwg_segments(path):
    doc = ezdwg.read(str(path))
    for entity in doc.modelspace().query("LINE LWPOLYLINE ARC CIRCLE ELLIPSE"):
        kind = str(getattr(entity, "dxftype", "") or "").upper()
        dxf = getattr(entity, "dxf", {}) or {}
        if kind == "LINE":
            start = _point2(dxf.get("start"))
            end = _point2(dxf.get("end"))
            if start and end:
                yield (start, end)
        elif kind == "LWPOLYLINE":
            points = [_point2(point) for point in (dxf.get("points") or dxf.get("vertices") or ())]
            points = [point for point in points if point]
            for index in range(len(points) - 1):
                yield (points[index], points[index + 1])
        elif kind == "ARC":
            yield from _arc_segments(dxf)
        elif kind == "CIRCLE":
            yield from _circle_segments(dxf)
        elif kind == "ELLIPSE":
            center = _point2(dxf.get("center"))
            if center:
                # The bounds already carry the useful signal; draw a tiny cross for ellipse centers.
                delta = 12
                yield ((center[0] - delta, center[1]), (center[0] + delta, center[1]))
                yield ((center[0], center[1] - delta), (center[0], center[1] + delta))


def _arc_segments(dxf):
    center = _point2(dxf.get("center"))
    radius = _finite_float(dxf.get("radius"))
    if not center or radius is None or radius <= 0:
        return
    start = _finite_float(dxf.get("start_angle")) or 0
    end = _finite_float(dxf.get("end_angle")) or 360
    if end < start:
        end += 360
    steps = max(8, min(64, int((end - start) / 8)))
    points = []
    for index in range(steps + 1):
        angle = math.radians(start + ((end - start) * index / steps))
        points.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius))
    for index in range(len(points) - 1):
        yield (points[index], points[index + 1])


def _circle_segments(dxf):
    center = _point2(dxf.get("center"))
    radius = _finite_float(dxf.get("radius"))
    if not center or radius is None or radius <= 0:
        return
    points = []
    for index in range(49):
        angle = math.tau * index / 48
        points.append((center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius))
    for index in range(len(points) - 1):
        yield (points[index], points[index + 1])


def _point2(point):
    if point is None or len(point) < 2:
        return None
    x = _finite_float(point[0])
    y = _finite_float(point[1])
    if x is None or y is None:
        return None
    if abs(x) > MODEL_MAX_ABS or abs(y) > MODEL_MAX_ABS:
        return None
    return (x, y)


def _finite_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _point_near_bounds(point, bounds):
    pad = max(bounds["width"], bounds["height"]) * 0.02
    return (
        bounds["min_x"] - pad <= point[0] <= bounds["max_x"] + pad
        and bounds["min_y"] - pad <= point[1] <= bounds["max_y"] + pad
    )


def _to_pixel(x, y, bounds, plot_x, plot_y, scale):
    return (
        plot_x + (x - bounds["min_x"]) * scale,
        plot_y + (bounds["max_y"] - y) * scale,
    )


def _bounds(data):
    return {
        "min_x": float(data["min_x"]),
        "min_y": float(data["min_y"]),
        "max_x": float(data["max_x"]),
        "max_y": float(data["max_y"]),
        "width": float(data["width"]),
        "height": float(data["height"]),
    }


def _draw_dashed_rectangle(draw, rect, *, color, width):
    left, top, right, bottom = rect
    for start, end in (
        ((left, top), (right, top)),
        ((right, top), (right, bottom)),
        ((right, bottom), (left, bottom)),
        ((left, bottom), (left, top)),
    ):
        _draw_dashed_line(draw, start, end, color=color, width=width)


def _draw_dashed_line(draw, start, end, *, color, width, dash=18, gap=10):
    x1, y1 = start
    x2, y2 = end
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    pos = 0
    while pos < length:
        seg_end = min(pos + dash, length)
        draw.line((x1 + dx * pos, y1 + dy * pos, x1 + dx * seg_end, y1 + dy * seg_end), fill=color, width=width)
        pos += dash + gap


def _text_width(draw, text, font):
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return right - left


def _fonts():
    def font(size, bold=False):
        names = (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        )
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    return {
        "title": font(30, bold=True),
        "body": font(18),
        "small": font(14),
    }


if __name__ == "__main__":
    main()
