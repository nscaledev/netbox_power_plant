from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase as DjangoTestCase
from django.urls import reverse
from utilities.testing import TestCase

from dcim.models import Rack

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PlantProvenance,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_rack_footprints import (
    MADISON_RACK_FOOTPRINT_APPROVED_STATE,
    MADISON_RACK_FOOTPRINT_REVIEW_STATE,
    apply_madison_rack_footprint_candidates,
    approve_madison_rack_footprint_bindings,
    build_madison_rack_footprint_summary,
    slot_for_electrical_rack_id,
)
from netbox_power_plant.services.madison_space_decomposition import (
    apply_madison_detailed_space_decomposition,
    approve_madison_detailed_space_boundaries,
)
from netbox_power_plant.tests.test_madison_space_decomposition import _seed_approved_underlay


class MadisonRackFootprintServiceTestCase(DjangoTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = _seed_approved_underlay()
        apply_madison_detailed_space_decomposition(cls.site)
        approve_madison_detailed_space_boundaries(cls.site, reviewer="operator")
        cls.rack_a1 = Rack.objects.create(name="A1", site=cls.site)
        cls.rack_b1 = Rack.objects.create(name="B1", site=cls.site)

    def test_maps_electrical_rack_ids_to_workbook_physical_slots(self):
        self.assertEqual(slot_for_electrical_rack_id("GB300-P5-R1-C1"), "A1")
        self.assertEqual(slot_for_electrical_rack_id("GB300-P5-R2-C1"), "B1")
        self.assertEqual(slot_for_electrical_rack_id("FE-P1-R1-C1"), "Q13")
        self.assertEqual(slot_for_electrical_rack_id("BE-P1-R2-C4"), "R18")
        self.assertEqual(slot_for_electrical_rack_id("NW-P2A-R2-C7"), "J7")

    def test_builds_candidates_from_netbox_rack_slots_when_manifest_is_absent(self):
        summary = build_madison_rack_footprint_summary(
            self.site,
            manifest_path="/missing/manifest.csv",
            schedule_path="/missing/schedule.csv",
        )

        self.assertTrue(summary.ready)
        self.assertEqual(summary.candidate_count, 2)
        self.assertEqual(summary.matched_count, 2)
        self.assertEqual(summary.materialized_count, 0)

        a1 = next(candidate for candidate in summary.candidates if candidate.source_record.physical_slot == "A1")
        self.assertEqual(a1.rack, self.rack_a1)
        self.assertEqual(a1.physical_space.metadata["source_room_label"], "B1209")
        self.assertEqual(a1.boundary_geometry["coordinate_source"], "madison_rack_cabinet_layout")
        self.assertGreater(float(a1.boundary_geometry["width"]), 0)
        self.assertGreater(float(a1.boundary_geometry["depth"]), 0)

    def test_apply_materializes_footprints_placements_bindings_and_provenance(self):
        result = apply_madison_rack_footprint_candidates(
            self.site,
            manifest_path="/missing/manifest.csv",
            schedule_path="/missing/schedule.csv",
            reviewer="operator",
        )

        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.materialized_count, 2)
        self.assertEqual(result.placed_count, 2)
        self.assertEqual(result.bound_count, 2)
        self.assertEqual(result.pending_review_count, 2)

        element = PhysicalElement.objects.get(label="A1")
        self.assertEqual(element.element_type.element_kind, PhysicalElementKindChoices.KIND_RACK_FOOTPRINT)
        self.assertEqual(element.metadata["review_state"], MADISON_RACK_FOOTPRINT_REVIEW_STATE)
        self.assertEqual(element.metadata["matched_netbox_rack_name"], "A1")

        placement = SpatialPlacement.objects.get(assigned_object_id=element.pk)
        self.assertEqual(placement.metadata["review_state"], MADISON_RACK_FOOTPRINT_REVIEW_STATE)
        self.assertEqual(placement.anchor, "lower-left")

        binding = PhysicalObjectBinding.objects.get(physical_element=element)
        self.assertEqual(binding.assigned_object, self.rack_a1)
        self.assertFalse(binding.is_primary)
        self.assertEqual(binding.confidence, SpatialConfidenceChoices.CONFIDENCE_DERIVED)
        self.assertEqual(binding.metadata["review_state"], MADISON_RACK_FOOTPRINT_REVIEW_STATE)

        self.assertEqual(
            PlantProvenance.objects.filter(source_ref="madison:rack-footprint:a1").count(),
            3,
        )

    def test_approve_promotes_matched_bindings_and_provenance(self):
        apply_madison_rack_footprint_candidates(
            self.site,
            manifest_path="/missing/manifest.csv",
            schedule_path="/missing/schedule.csv",
            reviewer="operator",
        )

        result = approve_madison_rack_footprint_bindings(
            self.site,
            reviewer="operator",
            notes="Visual overlay checked.",
        )

        self.assertEqual(result.approved_count, 2)
        self.assertEqual(result.pending_review_count, 0)

        binding = PhysicalObjectBinding.objects.get(
            assigned_object_type=ContentType.objects.get_for_model(Rack, for_concrete_model=False),
            assigned_object_id=self.rack_a1.pk,
        )
        self.assertTrue(binding.is_primary)
        self.assertEqual(binding.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(binding.metadata["review_state"], MADISON_RACK_FOOTPRINT_APPROVED_STATE)
        self.assertEqual(binding.metadata["approval_notes"], "Visual overlay checked.")

        binding.physical_element.refresh_from_db()
        binding.spatial_placement.refresh_from_db()
        self.assertEqual(binding.physical_element.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(binding.spatial_placement.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertTrue(
            all(
                provenance.is_authoritative
                for provenance in PlantProvenance.objects.filter(source_ref="madison:rack-footprint:a1")
            )
        )


class MadisonRackFootprintViewTestCase(TestCase):
    user_permissions = (
        "dcim.view_rack",
        "dcim.view_site",
        "netbox_power_plant.view_physicalelement",
        "netbox_power_plant.view_physicalobjectbinding",
        "netbox_power_plant.view_physicalspace",
        "netbox_power_plant.view_plantsourcedocument",
        "netbox_power_plant.view_spatialframe",
        "netbox_power_plant.view_spatialplacement",
        "netbox_power_plant.add_physicalelement",
        "netbox_power_plant.change_physicalelement",
        "netbox_power_plant.add_spatialplacement",
        "netbox_power_plant.change_spatialplacement",
        "netbox_power_plant.add_physicalobjectbinding",
        "netbox_power_plant.change_physicalobjectbinding",
        "netbox_power_plant.add_plantprovenance",
        "netbox_power_plant.change_plantprovenance",
    )

    @classmethod
    def setUpTestData(cls):
        cls.site = _seed_approved_underlay()
        apply_madison_detailed_space_decomposition(cls.site)
        approve_madison_detailed_space_boundaries(cls.site, reviewer="operator")
        cls.rack = Rack.objects.create(name="A1", site=cls.site)

    @patch("netbox_power_plant.services.madison_rack_footprints.DEFAULT_RACK_MANIFEST_PATHS", ())
    @patch("netbox_power_plant.services.madison_rack_footprints.DEFAULT_CABINET_SCHEDULE_PATHS", ())
    def test_review_page_applies_and_approves_rack_footprints(self):
        apply_response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "apply_rack_footprints",
                "site": "gs001",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(apply_response, 200)
        self.assertContains(apply_response, "Applied Madison rack/cabinet footprints")
        self.assertContains(apply_response, "Rack/Cabinet Footprint Modeling")
        self.assertContains(apply_response, 'data-spatial-review-kind="placement"')

        approve_response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "approve_rack_footprint_bindings",
                "site": "gs001",
                "notes": "Visual rack overlay checked.",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(approve_response, 200)
        self.assertContains(approve_response, "Approved Madison rack/cabinet footprint bindings")
        binding = PhysicalObjectBinding.objects.get(assigned_object_id=self.rack.pk)
        self.assertTrue(binding.is_primary)
        self.assertEqual(binding.metadata["review_state"], MADISON_RACK_FOOTPRINT_APPROVED_STATE)
