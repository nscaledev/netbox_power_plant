from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Location, Rack, Site

from netbox_power_plant.choices import (
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantSourceTypeChoices,
    SpatialAxisOrientationChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_underlay import (
    MadisonUnderlayImportSummary,
    import_madison_underlay,
)
from netbox_power_plant.services.cad_calibration import (
    CoordinateBounds,
    build_cad_lower_left_grid_calibration,
)


class MadisonUnderlayImportTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="GS001", slug="gs001")
        cls.location = Location.objects.create(site=cls.site, name="Data Center", slug="data-center")
        cls.rack_a1 = Rack.objects.create(name="A1", site=cls.site, location=cls.location)
        cls.rack_a2 = Rack.objects.create(name="A2", site=cls.site, location=cls.location)

    def test_dry_run_rolls_back_seeded_and_imported_objects(self):
        summary = import_madison_underlay(
            self.site,
            (
                {
                    "source_key": "manifest:gs001-a1",
                    "rack_name": self.rack_a1.name,
                    "data_hall": "Data Hall 1",
                    "row": "A",
                    "order": 1,
                    "x": "10.000",
                    "y": "20.000",
                },
            ),
            location=self.location,
        )

        self.assertIsInstance(summary, MadisonUnderlayImportSummary)
        self.assertTrue(summary.dry_run)
        self.assertEqual(summary.total_count, 1)
        self.assertEqual(summary.imported_count, 1)
        self.assertEqual(summary.would_bind_count, 1)
        self.assertGreater(summary.seed_created_count, 0)
        self.assertEqual(PlantSourceDocument.objects.count(), 0)
        self.assertEqual(PlantSourceSheet.objects.count(), 0)
        self.assertEqual(PlantSourceLayer.objects.count(), 0)
        self.assertEqual(SpatialFrame.objects.count(), 0)
        self.assertEqual(PhysicalSpace.objects.count(), 0)
        self.assertEqual(PhysicalElement.objects.count(), 0)
        self.assertEqual(SpatialPlacement.objects.count(), 0)
        self.assertEqual(PhysicalObjectBinding.objects.count(), 0)
        self.assertEqual(PlantProvenance.objects.count(), 0)

    def test_apply_is_idempotent_for_underlay_frames_spaces_and_rack_footprints(self):
        row = {
            "source_key": "manifest:gs001-a1",
            "rack_name": self.rack_a1.name,
            "data_hall": "DH1",
            "row": "A",
            "order": 1,
            "x": "10.000",
            "y": "20.000",
            "width": "2.500",
            "depth": "4.500",
        }

        first_summary = import_madison_underlay(self.site, (row,), apply=True, location=self.location)

        self.assertFalse(first_summary.dry_run)
        self.assertEqual(first_summary.total_count, 1)
        self.assertEqual(first_summary.imported_count, 1)
        self.assertEqual(first_summary.bound_count, 1)
        self.assertEqual(PlantSourceDocument.objects.count(), 1)
        self.assertEqual(PlantSourceSheet.objects.count(), 1)
        self.assertEqual(PlantSourceLayer.objects.count(), 1)
        self.assertEqual(SpatialFrame.objects.count(), 3)
        self.assertEqual(PhysicalSpace.objects.count(), 4)
        self.assertEqual(PhysicalElement.objects.count(), 1)
        self.assertEqual(SpatialPlacement.objects.count(), 1)
        self.assertEqual(PhysicalObjectBinding.objects.count(), 1)
        self.assertEqual(PlantProvenance.objects.count(), 2)

        second_summary = import_madison_underlay(self.site, (row,), apply=True, location=self.location)

        self.assertEqual(second_summary.created_count, 0)
        self.assertEqual(second_summary.imported_count, 1)
        self.assertEqual(second_summary.bound_count, 1)
        self.assertEqual(second_summary.rows[0].binding_action, "already_bound")
        self.assertEqual(PlantSourceDocument.objects.count(), 1)
        self.assertEqual(PlantSourceSheet.objects.count(), 1)
        self.assertEqual(PlantSourceLayer.objects.count(), 1)
        self.assertEqual(SpatialFrame.objects.count(), 3)
        self.assertEqual(PhysicalSpace.objects.count(), 4)
        self.assertEqual(PhysicalElement.objects.count(), 1)
        self.assertEqual(SpatialPlacement.objects.count(), 1)
        self.assertEqual(PhysicalObjectBinding.objects.count(), 1)
        self.assertEqual(PlantProvenance.objects.count(), 2)

        self.assertEqual(first_summary.site_frame.units, "gs001_svg_unit")
        self.assertEqual(
            first_summary.site_frame.axis_orientation,
            SpatialAxisOrientationChoices.ORIENTATION_LOWER_LEFT_X_RIGHT_Y_UP,
        )
        self.assertEqual(first_summary.site_frame.source_ref, "madison:site-plan:lower-left-grid")
        self.assertEqual(first_summary.source_document.source_type, PlantSourceTypeChoices.TYPE_SVG)
        self.assertEqual(
            first_summary.source_document.metadata["coordinate_grid"]["target_axis_orientation"],
            SpatialAxisOrientationChoices.ORIENTATION_LOWER_LEFT_X_RIGHT_Y_UP,
        )

    def test_reconciles_imported_rack_footprints_to_netbox_racks(self):
        import_madison_underlay(
            self.site,
            (
                {
                    "source_key": "manifest:gs001-a2",
                    "rack_name": self.rack_a2.name,
                    "data_hall": 1,
                    "row": "A",
                    "order": 2,
                    "x": "13.000",
                    "y": "20.000",
                },
            ),
            apply=True,
            location=self.location,
        )

        element = PhysicalElement.objects.get(source_label=self.rack_a2.name)
        binding = PhysicalObjectBinding.objects.get(physical_element=element)
        self.assertEqual(binding.binding_role, PhysicalObjectBindingRoleChoices.ROLE_INVENTORY_OBJECT_FOR)
        self.assertEqual(binding.assigned_object_type, ContentType.objects.get_for_model(self.rack_a2))
        self.assertEqual(binding.assigned_object_id, self.rack_a2.pk)
        self.assertEqual(binding.assigned_object, self.rack_a2)

    def test_duplicate_manifest_rows_are_blocked_before_import(self):
        summary = import_madison_underlay(
            self.site,
            (
                {
                    "source_key": "duplicate-source",
                    "rack_name": self.rack_a1.name,
                    "data_hall": "Data Hall 1",
                    "row": "A",
                    "order": 1,
                },
                {
                    "source_key": "duplicate-source",
                    "rack_name": self.rack_a1.name,
                    "data_hall": "Data Hall 1",
                    "row": "A",
                    "order": 1,
                },
            ),
            apply=True,
            location=self.location,
        )

        self.assertEqual(summary.blocked_count, 2)
        self.assertIn("duplicate source_key", summary.blocked_reasons[0])
        self.assertIn("duplicate rack slot", summary.blocked_reasons[0])
        self.assertEqual(PhysicalElement.objects.count(), 0)
        self.assertEqual(SpatialPlacement.objects.count(), 0)
        self.assertEqual(PhysicalObjectBinding.objects.count(), 0)

    def test_missing_cad_coordinates_are_derived_from_row_order(self):
        summary = import_madison_underlay(
            self.site,
            (
                {
                    "source_key": "manifest:gs001-a1",
                    "rack_name": self.rack_a1.name,
                    "data_hall": "Data Hall 1",
                    "row": "A",
                    "order": 1,
                    "notes": "row-order-only source",
                },
            ),
            apply=True,
            location=self.location,
        )

        self.assertEqual(summary.missing_coordinate_count, 1)
        self.assertEqual(summary.rows[0].coordinate_source, "derived_from_row_order")
        self.assertEqual(summary.rows[0].confidence, SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL)
        element = PhysicalElement.objects.get(source_label=self.rack_a1.name)
        placement = SpatialPlacement.objects.get(assigned_object_id=element.pk)
        slot_space = PhysicalSpace.objects.get(space_kind=PhysicalSpaceKindChoices.KIND_RACK_SLOT)
        self.assertEqual(element.confidence, SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL)
        self.assertEqual(placement.confidence, SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL)
        self.assertEqual(placement.x, Decimal("1.000"))
        self.assertEqual(placement.y, Decimal("2.000"))
        self.assertTrue(placement.metadata["missing_cad_coordinates"])
        self.assertEqual(placement.metadata["coordinate_source"], "derived_from_row_order")
        self.assertEqual(placement.metadata["madison_manifest_row"]["notes"], "row-order-only source")
        self.assertEqual(slot_space.confidence, SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL)
        self.assertEqual(slot_space.boundary_geometry["coordinate_source"], "derived_from_row_order")

    def test_cad_coordinates_are_transformed_into_lower_left_physical_grid(self):
        calibration = build_cad_lower_left_grid_calibration(
            source_path="Enovum MAD1-Sheet - E3-1A - First Floor Power Plan - Area A.dwg",
            structure_bounds=CoordinateBounds.from_values(1000, 2000, 2200, 3200),
            source_units="inch",
        )

        summary = import_madison_underlay(
            self.site,
            (
                {
                    "source_key": "manifest:gs001-a1-cad",
                    "rack_name": self.rack_a1.name,
                    "data_hall": "Data Hall 1",
                    "row": "A",
                    "order": 1,
                    "cad_x": "1120",
                    "cad_y": "2060",
                },
            ),
            apply=True,
            location=self.location,
            grid_calibration=calibration,
        )

        self.assertEqual(summary.source_document.source_type, PlantSourceTypeChoices.TYPE_CAD_EXPORT)
        self.assertEqual(summary.site_frame.units, "ft")
        self.assertEqual(summary.site_frame.width, Decimal("100.000"))
        self.assertEqual(summary.site_frame.height, Decimal("100.000"))
        self.assertEqual(summary.rows[0].coordinate_source, "dwg_coordinates")
        placement = SpatialPlacement.objects.get()
        self.assertEqual(placement.x, Decimal("10.000"))
        self.assertEqual(placement.y, Decimal("5.000"))
        self.assertEqual(placement.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(placement.metadata["source_x"], "1120")
        self.assertEqual(placement.metadata["source_y"], "2060")
