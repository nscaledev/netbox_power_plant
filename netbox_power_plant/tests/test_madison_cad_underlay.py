from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

from netbox_power_plant.services.cad_calibration import (
    CoordinateBounds,
    DwgGeometryExtraction,
    PcpPlotMetadata,
)
from netbox_power_plant.services.madison_cad_underlay import (
    build_madison_cad_calibration_report,
    discover_madison_cad_sources,
)


class MadisonCadUnderlayTestCase(SimpleTestCase):
    def test_discovers_requested_dwg_pcp_pairs_and_site_grid_flags(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch_sheet(root, "E3-1A", "First Floor Power Plan - Area A")
            _touch_sheet(root, "E3-10", "Enlarged Electrical Plans")
            _touch_sheet(root, "E5-1", "One Line Diagram - Primary")

            sources = discover_madison_cad_sources(root, sheet_numbers=("E3-1A", "E3-10", "E5-1"))

        self.assertEqual([source.sheet_number for source in sources], ["E3-1A", "E3-10", "E5-1"])
        self.assertTrue(sources[0].participates_in_site_grid)
        self.assertFalse(sources[1].participates_in_site_grid)
        self.assertEqual(sources[0].role, "first_floor_power_plan")
        self.assertEqual(sources[1].role, "enlarged_electrical_plan")

    def test_builds_review_required_manifest_from_combined_first_floor_bounds(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch_sheet(root, "E3-1A", "First Floor Power Plan - Area A")
            _touch_sheet(root, "E3-1B", "First Floor Power Plan - Area B")
            _touch_sheet(root, "E3-10", "Enlarged Electrical Plans")

            with patch(
                "netbox_power_plant.services.madison_cad_underlay.read_dwg_geometry_bounds",
                side_effect=_fake_extraction,
            ), patch(
                "netbox_power_plant.services.madison_cad_underlay.read_pcp_plot_metadata",
                side_effect=_fake_pcp,
            ), patch(
                "netbox_power_plant.services.madison_cad_underlay._read_dwg_line_segments",
                side_effect=_fake_line_segments,
            ):
                report = build_madison_cad_calibration_report(
                    root,
                    sheet_numbers=("E3-1A", "E3-1B", "E3-10"),
                    site_grid_sheet_numbers=("E3-1A", "E3-1B"),
                    source_units="inch",
                )

        self.assertEqual(report.status, "review_required")
        self.assertEqual(report.proposed_structure_bounds, CoordinateBounds.from_values(0, 0, 2400, 1200))
        self.assertEqual(report.current_building_bounds, CoordinateBounds.from_values(1200, 0, 2400, 1200))
        self.assertIsNotNone(report.calibration)
        self.assertEqual(report.calibration.width, 200)
        self.assertEqual(report.calibration.height, 100)
        manifest = report.to_manifest()
        self.assertEqual(manifest["schema"], "netbox_power_plant.madison_cad_calibration.v1")
        self.assertEqual(manifest["coordinate_plane_bounds"]["width"], "2400.000")
        self.assertEqual(manifest["calibration"]["origin"]["grid_x"], "0.000")
        self.assertEqual(manifest["current_building"]["origin_in_site_grid"]["x"], "100.000")
        self.assertEqual(manifest["current_building"]["width"], "100.000")
        self.assertEqual(manifest["sheets"][0]["pcp"]["units"], "_I")
        markdown = report.to_markdown()
        self.assertIn("Madison CAD Calibration Report", markdown)
        self.assertIn("Current Building Footprint", markdown)
        self.assertIn("Confirm the CAD model unit assumption", markdown)

    def test_unconfirmed_source_units_blocks_physical_grid_but_reports_sheet_extents(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _touch_sheet(root, "E3-1A", "First Floor Power Plan - Area A")

            with patch(
                "netbox_power_plant.services.madison_cad_underlay.read_dwg_geometry_bounds",
                side_effect=_fake_extraction,
            ), patch(
                "netbox_power_plant.services.madison_cad_underlay._read_dwg_line_segments",
                side_effect=_fake_line_segments,
            ):
                report = build_madison_cad_calibration_report(
                    root,
                    sheet_numbers=("E3-1A",),
                    site_grid_sheet_numbers=("E3-1A",),
                    source_units=None,
                )

        self.assertEqual(report.status, "blocked")
        self.assertIsNone(report.calibration)
        self.assertIsNotNone(report.proposed_structure_bounds)
        self.assertTrue(any("Source units are unconfirmed" in warning for warning in report.warnings))


def _touch_sheet(root, sheet, title):
    stem = f"Enovum MAD1-Sheet - {sheet} - {title}"
    (root / f"{stem}.dwg").write_text("dwg", encoding="utf-8")
    (root / f"{stem}.pcp").write_text("UNITS = _I\nSCALE = 1=1\n", encoding="utf-8")


def _fake_extraction(path):
    sheet = _sheet_from_path(path)
    bounds = {
        "E3-1A": CoordinateBounds.from_values(0, 0, 1200, 1200),
        "E3-1B": CoordinateBounds.from_values(1200, 0, 2400, 1200),
        "E3-10": CoordinateBounds.from_values(5000, 5000, 7000, 5500),
    }[sheet]
    return DwgGeometryExtraction(
        path=str(path),
        decode_version="AC1032",
        entity_count=10,
        point_count=20,
        discarded_point_count=1,
        entity_type_counts={"LINE": 10},
        bounds=bounds,
    )


def _fake_pcp(path):
    return PcpPlotMetadata(path=str(path), units="_I", origin="0.00,0.00", size="MAX", rotate="90", scale="1=1")


def _fake_line_segments(path):
    return (
        (Decimal("0"), Decimal("0"), Decimal("100"), Decimal("0"), Decimal("100")),
        (Decimal("1200"), Decimal("0"), Decimal("2400"), Decimal("0"), Decimal("1200")),
        (Decimal("1200"), Decimal("1200"), Decimal("2400"), Decimal("1200"), Decimal("1200")),
        (Decimal("1200"), Decimal("0"), Decimal("1200"), Decimal("1200"), Decimal("1200")),
        (Decimal("2400"), Decimal("0"), Decimal("2400"), Decimal("1200"), Decimal("1200")),
    )


def _sheet_from_path(path):
    name = Path(path).name
    return name.split(" - ")[1]
