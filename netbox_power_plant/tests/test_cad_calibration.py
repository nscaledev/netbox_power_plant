import sys
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from netbox_power_plant.choices import SpatialConfidenceChoices
from netbox_power_plant.services.cad_calibration import (
    LOWER_LEFT_Y_UP,
    UPPER_LEFT_Y_DOWN,
    CadCalibrationError,
    CoordinateBounds,
    LowerLeftGridCalibration,
    build_cad_lower_left_grid_calibration,
    read_dwg_geometry_bounds,
)


class CadCalibrationTestCase(SimpleTestCase):
    def test_builds_physical_grid_from_supplied_dwg_structure_bounds(self):
        calibration = build_cad_lower_left_grid_calibration(
            source_path="madison-area-a.dwg",
            structure_bounds=CoordinateBounds.from_values(1000, 2000, 2200, 3200),
            source_units="inch",
        )

        self.assertEqual(calibration.source_type, "dwg")
        self.assertEqual(calibration.grid_units, "ft")
        self.assertEqual(calibration.source_axis_orientation, LOWER_LEFT_Y_UP)
        self.assertEqual(calibration.scale_x, Decimal("0.08333333333333333333333333333"))
        self.assertEqual(calibration.width, Decimal("100.000"))
        self.assertEqual(calibration.height, Decimal("100.000"))
        self.assertEqual(calibration.source_to_grid(1120, 2060), (Decimal("10.000"), Decimal("5.000")))
        self.assertIn("DWG bounds", calibration.to_metadata()["warnings"][0])

    def test_unbounded_dwg_requires_mandatory_cad_dependency(self):
        with patch("netbox_power_plant.services.cad_calibration.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(CadCalibrationError, "mandatory netbox_power_plant dependency"):
                build_cad_lower_left_grid_calibration(
                    source_path="madison-area-a.dwg",
                    source_units="inch",
                )

    def test_reads_dwg_bounds_with_ezdwg_and_discards_outlier_points(self):
        fake_ezdwg = SimpleNamespace(read=lambda path: _FakeDwgDocument())

        with patch.dict(sys.modules, {"ezdwg": fake_ezdwg}):
            extraction = read_dwg_geometry_bounds("madison-area-a.dwg")

        self.assertEqual(extraction.decode_version, "AC1032")
        self.assertEqual(extraction.entity_count, 2)
        self.assertEqual(extraction.point_count, 4)
        self.assertEqual(extraction.discarded_point_count, 2)
        self.assertEqual(extraction.bounds, CoordinateBounds.from_values(0, 0, 120, 60))
        self.assertEqual(extraction.entity_type_counts["LINE"], 2)

    def test_upper_left_overlay_transforms_to_lower_left_grid(self):
        calibration = LowerLeftGridCalibration(
            source_name="overlay.svg",
            source_type="svg",
            source_units="svg_unit",
            grid_units="ft",
            source_axis_orientation=UPPER_LEFT_Y_DOWN,
            structure_bounds=CoordinateBounds.from_values(0, 0, 100, 50),
            scale_x=Decimal("2"),
            scale_y=Decimal("4"),
            confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        )

        self.assertEqual(calibration.source_to_grid(0, 50), (Decimal("0.000"), Decimal("0.000")))
        self.assertEqual(calibration.source_to_grid(100, 0), (Decimal("200.000"), Decimal("200.000")))
        self.assertEqual(calibration.grid_to_source(200, 200), (Decimal("100.000"), Decimal("0.000")))


class _FakeDwgDocument:
    decode_version = "AC1032"
    version = "AC1032"

    def modelspace(self):
        return _FakeDwgLayout()


class _FakeDwgLayout:
    def query(self, query):
        return (
            _FakeDwgEntity("LINE", {"start": (0, 0, 0), "end": (120, 60, 0)}),
            _FakeDwgEntity("LINE", {"start": (Decimal("1E+99"), 0, 0), "end": (10, Decimal("-1E+99"), 0)}),
        )


class _FakeDwgEntity:
    def __init__(self, dxftype, dxf):
        self.dxftype = dxftype
        self.dxf = dxf
