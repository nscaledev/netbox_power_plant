from django.test import TestCase as DjangoTestCase
from django.urls import reverse
from utilities.testing import TestCase

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantSourceLayerKindChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
)
from netbox_power_plant.services.madison_cad_approval import MADISON_CAD_FIRST_FLOOR_SPACE_KEY
from netbox_power_plant.services.madison_cad_materialization import (
    MADISON_CAD_CURRENT_BUILDING_SPACE_KEY,
    MADISON_CAD_SITE_FRAME_KEY,
    MADISON_CAD_SOURCE_DOCUMENT_KEY,
    madison_cad_object_slug,
)
from netbox_power_plant.services.madison_space_decomposition import (
    MADISON_DETAILED_SPACE_APPROVED_STATE,
    MADISON_DETAILED_SPACE_REVIEW_STATE,
    apply_madison_detailed_space_decomposition,
    approve_madison_detailed_space_boundaries,
    build_madison_detailed_space_decomposition_summary,
)
from netbox_power_plant.services.spatial_geometry_review import (
    update_physical_space_geometry_from_visual_review,
)


class MadisonDetailedSpaceDecompositionServiceTestCase(DjangoTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = _seed_approved_underlay()

    def test_builds_candidates_from_approved_cad_underlay(self):
        summary = build_madison_detailed_space_decomposition_summary(self.site)

        self.assertTrue(summary.ready)
        self.assertEqual(summary.candidate_count, 10)
        self.assertEqual(summary.materialized_count, 0)
        data_hall_2a = next(candidate for candidate in summary.candidates if candidate.spec.room_label == "B1209")
        self.assertEqual(data_hall_2a.boundary_geometry["coordinate_source"], "madison_cad_detailed_space_decomposition")
        self.assertGreater(float(data_hall_2a.boundary_geometry["width"]), 0)
        self.assertGreater(float(data_hall_2a.boundary_geometry["depth"]), 0)

    def test_apply_materializes_spaces_and_provenance_idempotently(self):
        first = apply_madison_detailed_space_decomposition(self.site)
        second = apply_madison_detailed_space_decomposition(self.site)

        self.assertEqual(first.created_count, 10)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(PhysicalSpace.objects.filter(site=self.site, metadata__decomposition_role="detailed_space").count(), 10)
        self.assertEqual(PlantProvenance.objects.filter(source_ref__startswith="madison:cad:detailed-space").count(), 10)

        data_hall_1b = PhysicalSpace.objects.get(slug=madison_cad_object_slug(self.site, "madison-detailed-space-b1111-data-hall-1b"))
        self.assertEqual(data_hall_1b.space_kind, PhysicalSpaceKindChoices.KIND_DATA_HALL)
        self.assertEqual(data_hall_1b.metadata["review_state"], MADISON_DETAILED_SPACE_REVIEW_STATE)
        self.assertEqual(data_hall_1b.metadata["source_room_label"], "B1111")
        self.assertEqual(data_hall_1b.parent_space.slug, madison_cad_object_slug(self.site, MADISON_CAD_FIRST_FLOOR_SPACE_KEY))

    def test_approve_boundaries_promotes_spaces_and_provenance(self):
        apply_madison_detailed_space_decomposition(self.site)

        summary = approve_madison_detailed_space_boundaries(
            self.site,
            reviewer="operator",
            notes="Reviewed against CAD room labels.",
        )

        self.assertEqual(summary.approved_count, 10)
        self.assertEqual(summary.pending_review_count, 0)
        self.assertEqual(summary.updated_count, 10)

        data_hall_2a = PhysicalSpace.objects.get(slug=madison_cad_object_slug(self.site, "madison-detailed-space-b1209-data-hall-2a"))
        self.assertEqual(data_hall_2a.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(data_hall_2a.metadata["review_state"], MADISON_DETAILED_SPACE_APPROVED_STATE)
        self.assertEqual(data_hall_2a.metadata["boundary_status"], MADISON_DETAILED_SPACE_APPROVED_STATE)
        self.assertEqual(data_hall_2a.metadata["boundary_approved_by"], "operator")
        self.assertEqual(data_hall_2a.metadata["boundary_review_notes"], "Reviewed against CAD room labels.")

        provenance = PlantProvenance.objects.get(
            assigned_object_id=data_hall_2a.pk,
            source_ref="madison:cad:detailed-space:b1209",
        )
        self.assertTrue(provenance.is_authoritative)
        self.assertEqual(provenance.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(provenance.metadata["boundary_status"], MADISON_DETAILED_SPACE_APPROVED_STATE)

    def test_approve_boundaries_requires_materialized_spaces(self):
        with self.assertRaisesMessage(ValueError, "Materialize all Madison detailed spaces before approving boundaries"):
            approve_madison_detailed_space_boundaries(self.site)

    def test_refresh_preserves_approval_when_geometry_is_unchanged(self):
        apply_madison_detailed_space_decomposition(self.site)
        approve_madison_detailed_space_boundaries(self.site, reviewer="operator")

        refreshed = apply_madison_detailed_space_decomposition(self.site, reviewer="automation")

        self.assertEqual(refreshed.approved_count, 10)
        self.assertEqual(refreshed.pending_review_count, 0)
        self.assertEqual(refreshed.updated_count, 0)

    def test_blocks_without_approved_cad_underlay(self):
        site = Site.objects.create(name="Blocked", slug="blocked")

        summary = build_madison_detailed_space_decomposition_summary(site)

        self.assertFalse(summary.ready)
        self.assertIn("Approved Madison CAD source document is missing.", summary.blocked_reasons)


class MadisonDetailedSpaceDecompositionViewTestCase(TestCase):
    user_permissions = (
        "dcim.view_site",
        "netbox_power_plant.view_physicalspace",
        "netbox_power_plant.view_plantsourcedocument",
        "netbox_power_plant.view_spatialframe",
        "netbox_power_plant.view_spatialplacement",
        "netbox_power_plant.add_physicalspace",
        "netbox_power_plant.change_physicalspace",
        "netbox_power_plant.add_plantprovenance",
        "netbox_power_plant.change_plantprovenance",
    )

    @classmethod
    def setUpTestData(cls):
        cls.site = _seed_approved_underlay()

    def test_review_page_renders_detailed_space_workflow(self):
        apply_madison_detailed_space_decomposition(self.site)

        response = self.client.get(reverse("plugins:netbox_power_plant:madison_underlay_review"))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Detailed Space Decomposition")
        self.assertContains(response, "10")
        self.assertContains(response, "B1209")
        self.assertContains(response, "Apply Detailed Spaces")
        self.assertContains(response, 'data-spatial-drag-handle="move"')
        self.assertContains(response, "Use Saved Geometry")
        self.assertContains(response, "Approve Selected Boundary")

    def test_review_page_applies_detailed_space_decomposition(self):
        response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "apply_detailed_spaces",
                "site": "gs001",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Applied Madison detailed space decomposition")
        self.assertContains(response, "10 of 10 materialized")
        self.assertTrue(
            PhysicalSpace.objects.filter(
                site=self.site,
                slug=madison_cad_object_slug(self.site, "madison-detailed-space-b1209-data-hall-2a"),
            ).exists()
        )

    def test_review_page_approves_detailed_space_boundaries(self):
        apply_madison_detailed_space_decomposition(self.site)

        response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "approve_detailed_space_boundaries",
                "site": "gs001",
                "notes": "Operator review complete.",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Approved Madison detailed space boundaries")
        self.assertContains(response, "10 approved")
        self.assertContains(response, "Approved")
        self.assertEqual(
            PhysicalSpace.objects.filter(
                site=self.site,
                metadata__boundary_status=MADISON_DETAILED_SPACE_APPROVED_STATE,
            ).count(),
            10,
        )

    def test_review_page_updates_detailed_space_geometry_from_visual_review(self):
        apply_madison_detailed_space_decomposition(self.site)
        approve_madison_detailed_space_boundaries(self.site, reviewer="operator")
        space = PhysicalSpace.objects.get(
            slug=madison_cad_object_slug(self.site, "madison-detailed-space-b1209-data-hall-2a"),
        )

        response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "update_space_geometry",
                "site": "gs001",
                "space_id": space.pk,
                "x": "101.000",
                "y": "231.000",
                "width": "197.000",
                "depth": "42.000",
                "notes": "Corrected visually against the rendered CAD underlay.",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Updated visual geometry")
        self.assertContains(response, "Save Geometry Correction")

        space.refresh_from_db()
        self.assertEqual(space.boundary_geometry["x"], "101.000")
        self.assertEqual(space.boundary_geometry["y"], "231.000")
        self.assertEqual(space.boundary_geometry["width"], "197.000")
        self.assertEqual(space.boundary_geometry["depth"], "42.000")
        self.assertEqual(space.boundary_geometry["x_max"], "298.000")
        self.assertEqual(space.boundary_geometry["y_max"], "273.000")
        self.assertEqual(space.boundary_geometry["coordinate_source"], "operator_visual_review")
        self.assertEqual(space.metadata["review_state"], MADISON_DETAILED_SPACE_REVIEW_STATE)
        self.assertEqual(space.metadata["boundary_status"], MADISON_DETAILED_SPACE_REVIEW_STATE)
        self.assertEqual(space.metadata["geometry_review_state"], "operator_corrected")

        provenance = PlantProvenance.objects.get(
            assigned_object_id=space.pk,
            source_ref="madison:cad:detailed-space:b1209",
        )
        self.assertFalse(provenance.is_authoritative)
        self.assertEqual(provenance.confidence, SpatialConfidenceChoices.CONFIDENCE_DERIVED)
        self.assertEqual(provenance.metadata["boundary_status"], MADISON_DETAILED_SPACE_REVIEW_STATE)

    def test_review_page_requires_visual_geometry_confirmation(self):
        apply_madison_detailed_space_decomposition(self.site)
        space = PhysicalSpace.objects.get(
            slug=madison_cad_object_slug(self.site, "madison-detailed-space-b1209-data-hall-2a"),
        )

        response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "update_space_geometry",
                "site": "gs001",
                "space_id": space.pk,
                "x": "101.000",
                "y": "231.000",
                "width": "197.000",
                "depth": "42.000",
            },
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "This field is required.")
        space.refresh_from_db()
        self.assertNotEqual(space.boundary_geometry["x"], "101.000")

    def test_review_page_approves_corrected_space_geometry(self):
        apply_madison_detailed_space_decomposition(self.site)
        space = PhysicalSpace.objects.get(
            slug=madison_cad_object_slug(self.site, "madison-detailed-space-b1209-data-hall-2a"),
        )
        update_physical_space_geometry_from_visual_review(
            space.pk,
            x="101.000",
            y="231.000",
            width="197.000",
            depth="42.000",
            reviewer="operator",
            site=self.site,
            spatial_frame=space.spatial_frame,
        )

        response = self.client.post(
            reverse("plugins:netbox_power_plant:madison_underlay_review"),
            {
                "action": "approve_space_geometry",
                "site": "gs001",
                "space_id": space.pk,
                "notes": "Overlay checked.",
                "confirm": "on",
            },
            follow=True,
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, "Approved corrected visual geometry")
        space.refresh_from_db()
        self.assertEqual(space.metadata["review_state"], MADISON_DETAILED_SPACE_APPROVED_STATE)
        self.assertEqual(space.metadata["boundary_status"], MADISON_DETAILED_SPACE_APPROVED_STATE)
        self.assertEqual(space.metadata["geometry_review_state"], MADISON_DETAILED_SPACE_APPROVED_STATE)
        self.assertEqual(space.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)

        provenance = PlantProvenance.objects.get(
            assigned_object_id=space.pk,
            source_ref="madison:cad:detailed-space:b1209",
        )
        self.assertTrue(provenance.is_authoritative)
        self.assertEqual(provenance.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)


def _seed_approved_underlay():
    site = Site.objects.create(name="GS001", slug="gs001")
    source_document = PlantSourceDocument.objects.create(
        name="GS001 Madison Electrical CAD Package",
        slug=madison_cad_object_slug(site, MADISON_CAD_SOURCE_DOCUMENT_KEY),
        site=site,
        discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
        source_uri="/missing/test/cad-dir",
        metadata={
            "review_state": "approved",
            "calibration_status": "approved",
            "source_units": "inch",
            "coordinate_plane_bounds": {
                "min_x": "0.000",
                "min_y": "0.000",
                "max_x": "12000.000",
                "max_y": "6000.000",
                "width": "12000.000",
                "height": "6000.000",
            },
            "current_building": {
                "source_bounds": {
                    "min_x": "1200.000",
                    "min_y": "600.000",
                    "max_x": "10800.000",
                    "max_y": "5400.000",
                    "width": "9600.000",
                    "height": "4800.000",
                },
                "origin_in_site_grid": {"x": "100.000", "y": "50.000", "units": "ft"},
                "width": "800.000",
                "height": "400.000",
            },
        },
    )
    for index, sheet_number in enumerate(("E3-1A", "E3-1B"), start=1):
        sheet = PlantSourceSheet.objects.create(
            name=f"GS001 CAD {sheet_number}",
            slug=madison_cad_object_slug(site, f"madison-cad-{sheet_number}"),
            source_document=source_document,
            sheet_number=sheet_number,
            title=f"Sheet {sheet_number}",
            page_index=index,
        )
        PlantSourceLayer.objects.create(
            name=f"GS001 CAD {sheet_number} Geometry",
            slug=f"{sheet.slug}-geometry"[:100],
            source_sheet=sheet,
            layer_name="DWG_GEOMETRY",
            layer_kind=PlantSourceLayerKindChoices.KIND_GEOMETRY,
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
        )

    frame = SpatialFrame.objects.create(
        name="GS001 Madison CAD Site Coordinate Plane",
        slug=madison_cad_object_slug(site, MADISON_CAD_SITE_FRAME_KEY),
        site=site,
        width="1000.000",
        height="500.000",
        units="ft",
        confidence="authoritative",
        metadata={"review_state": "approved"},
    )
    current_building = PhysicalSpace.objects.create(
        name="GS001 Madison Current Building Footprint",
        slug=madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_SPACE_KEY),
        site=site,
        spatial_frame=frame,
        space_kind=PhysicalSpaceKindChoices.KIND_BUILDING,
        confidence="authoritative",
        metadata={"review_state": "approved"},
    )
    PhysicalSpace.objects.create(
        name="GS001 Madison First Floor",
        slug=madison_cad_object_slug(site, MADISON_CAD_FIRST_FLOOR_SPACE_KEY),
        site=site,
        spatial_frame=frame,
        parent_space=current_building,
        space_kind=PhysicalSpaceKindChoices.KIND_FLOOR,
        confidence="authoritative",
        metadata={"review_state": "approved"},
    )
    return site
