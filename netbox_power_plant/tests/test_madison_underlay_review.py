from django.contrib.contenttypes.models import ContentType
from django.test import TestCase as DjangoTestCase
from django.urls import reverse

from dcim.models import Location, Rack, Site
from utilities.testing import TestCase

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantSourceLayerKindChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_review import build_madison_underlay_review_summary


class MadisonUnderlayReviewServiceTestCase(DjangoTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="GS001", slug="gs001")
        cls.other_site = Site.objects.create(name="Other Site", slug="other-site")
        cls.location = Location.objects.create(site=cls.site, name="Hall A", slug="hall-a")
        cls.source_document = PlantSourceDocument.objects.create(
            name="GS001 Rack Layout Package",
            slug="gs001-rack-layout-package",
            site=cls.site,
            location=cls.location,
            discipline=PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            revision="A",
        )
        cls.source_sheet = PlantSourceSheet.objects.create(
            name="GS001 L1 Rack Plan",
            slug="gs001-l1-rack-plan",
            source_document=cls.source_document,
            sheet_number="R-101",
            title="Rack plan",
        )
        cls.source_layer = PlantSourceLayer.objects.create(
            name="Rack Footprints Layer",
            slug="rack-footprints-layer",
            source_sheet=cls.source_sheet,
            layer_name="RACKS",
            layer_kind=PlantSourceLayerKindChoices.KIND_RACK_LAYOUT,
            discipline=PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
        )
        PlantSourceDocument.objects.create(
            name="Other Site Source",
            slug="other-site-source",
            site=cls.other_site,
        )
        cls.frame = SpatialFrame.objects.create(
            name="GS001 Hall A Frame",
            slug="gs001-hall-a-frame",
            site=cls.site,
            location=cls.location,
            width="100.000",
            height="100.000",
        )
        cls.space = PhysicalSpace.objects.create(
            name="GS001 Hall A Space",
            slug="gs001-hall-a-space",
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.frame,
            space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
        )
        cls.element_type = PhysicalElementType.objects.create(
            name="Rack Footprint",
            slug="gs001-rack-footprint",
            discipline=PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
        )
        cls.placed_element = PhysicalElement.objects.create(
            name="Rack A1 Footprint",
            slug="rack-a1-footprint",
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.space,
            label="Rack A1",
        )
        cls.unplaced_element = PhysicalElement.objects.create(
            name="Rack A2 Footprint",
            slug="rack-a2-footprint",
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.space,
            label="Rack A2",
        )
        cls.placement = SpatialPlacement.objects.create(
            name="Rack A1 Placement",
            slug="rack-a1-placement",
            spatial_frame=cls.frame,
            assigned_object_type=ContentType.objects.get_for_model(cls.placed_element, for_concrete_model=False),
            assigned_object_id=cls.placed_element.pk,
            x="10.000",
            y="10.000",
            width="2.000",
            depth="4.000",
        )
        cls.rack = Rack.objects.create(name="Rack A1", site=cls.site, location=cls.location)
        cls.binding = PhysicalObjectBinding.objects.create(
            name="Rack A1 NetBox Rack Binding",
            slug="rack-a1-netbox-rack-binding",
            physical_element=cls.placed_element,
            spatial_placement=cls.placement,
            assigned_object_type=ContentType.objects.get_for_model(Rack, for_concrete_model=False),
            assigned_object_id=cls.rack.pk,
            binding_role=PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
            is_primary=True,
        )
        PlantProvenance.objects.create(
            name="Rack A1 Source Provenance",
            slug="rack-a1-source-provenance",
            assigned_object_type=ContentType.objects.get_for_model(cls.placed_element, for_concrete_model=False),
            assigned_object_id=cls.placed_element.pk,
            source_document=cls.source_document,
            source_sheet=cls.source_sheet,
            source_layer=cls.source_layer,
        )

    def test_summary_counts_madison_underlay_scope(self):
        summary = build_madison_underlay_review_summary("gs001")

        self.assertTrue(summary.site_found)
        self.assertEqual(summary.source_document_count, 1)
        self.assertEqual(summary.source_sheet_count, 1)
        self.assertEqual(summary.source_layer_count, 1)
        self.assertEqual(summary.spatial_frame_count, 1)
        self.assertEqual(summary.physical_space_count, 1)
        self.assertEqual(summary.physical_element_count, 2)
        self.assertEqual(summary.rack_footprint_count, 2)
        self.assertEqual(summary.rack_binding_count, 1)
        self.assertEqual(summary.placed_element_count, 1)
        self.assertEqual(summary.unplaced_element_count, 1)
        self.assertEqual(summary.rack_bindings[0].rack, self.rack)

        validation_counts = {count.key: count.count for count in summary.validation_type_counts}
        self.assertEqual(validation_counts["unbound_physical_element"], 1)
        self.assertEqual(validation_counts["unplaced_physical_element"], 1)
        self.assertEqual(summary.physical_validation_finding_count, 2)

    def test_missing_site_summary_is_empty(self):
        summary = build_madison_underlay_review_summary("missing-site")

        self.assertFalse(summary.site_found)
        self.assertEqual(summary.source_document_count, 0)
        self.assertEqual(summary.rack_binding_count, 0)
        self.assertEqual(summary.physical_validation_finding_count, 0)


class MadisonUnderlayReviewViewTestCase(TestCase):
    user_permissions = (
        "dcim.view_location",
        "dcim.view_rack",
        "dcim.view_site",
        "netbox_power_plant.view_physicalelement",
        "netbox_power_plant.view_physicalobjectbinding",
        "netbox_power_plant.view_physicalspace",
        "netbox_power_plant.view_plantsourcedocument",
        "netbox_power_plant.view_spatialframe",
        "netbox_power_plant.view_spatialplacement",
    )

    @classmethod
    def setUpTestData(cls):
        MadisonUnderlayReviewServiceTestCase.setUpTestData()

    def test_review_page_renders_read_only_summary(self):
        response = self.client.get(reverse("plugins:netbox_power_plant:madison_underlay_review"))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Madison Underlay Review")
        self.assertContains(response, "GS001 Rack Layout Package")
        self.assertContains(response, "Rack A1 Footprint")
        self.assertContains(response, "1 unplaced of 2")
        self.assertContains(response, "Rack A1")
        self.assertContains(response, "Unplaced Physical Element")
        self.assertContains(response, "Visual Spatial Review")
        self.assertContains(response, "data-spatial-review-map")
        self.assertContains(response, "scale(1 -1)")

        post_response = self.client.post(reverse("plugins:netbox_power_plant:madison_underlay_review"), {})
        self.assertEqual(post_response.status_code, 405)

    def test_review_page_handles_missing_site_query(self):
        response = self.client.get(
            "{}?site=missing-site".format(reverse("plugins:netbox_power_plant:madison_underlay_review")),
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "missing-site")
        self.assertContains(response, "No site with slug")
