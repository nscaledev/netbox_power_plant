from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalSpaceKindChoices,
    PlantExtractionMethodChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import PhysicalSpace, PlantProvenance, SpatialFrame
from netbox_power_plant.services.spatial_geometry_review import (
    VISUAL_GEOMETRY_APPROVED_STATE,
    VISUAL_GEOMETRY_CORRECTED_STATE,
    VISUAL_GEOMETRY_REVIEW_STATE,
    VISUAL_GEOMETRY_SOURCE,
    approve_visual_geometry_correction,
    update_physical_space_geometry_from_visual_review,
)


class SpatialGeometryReviewServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Madison", slug="madison")
        cls.other_site = Site.objects.create(name="Other Site", slug="other-site")
        cls.frame = SpatialFrame.objects.create(
            name="Madison Site Grid",
            slug="madison-site-grid",
            site=cls.site,
            width="200.000",
            height="100.000",
            units="ft",
        )
        cls.space = PhysicalSpace.objects.create(
            name="Data Hall 1A",
            slug="data-hall-1a",
            site=cls.site,
            spatial_frame=cls.frame,
            space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
            boundary_geometry={
                "type": "rectangle",
                "anchor": SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
                "x": "20.000",
                "y": "30.000",
                "width": "50.000",
                "depth": "20.000",
                "x_min": "20.000",
                "x_max": "70.000",
                "y_min": "30.000",
                "y_max": "50.000",
                "coordinate_source": "madison_cad_detailed_space_decomposition",
            },
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            metadata={
                "review_state": "approved",
                "boundary_status": "approved",
                "boundary_approved_by": "operator",
            },
        )
        cls.object_type = ContentType.objects.get_for_model(PhysicalSpace, for_concrete_model=False)
        cls.provenance = PlantProvenance.objects.create(
            name="Data Hall 1A CAD Provenance",
            slug="data-hall-1a-cad-provenance",
            assigned_object_type=cls.object_type,
            assigned_object_id=cls.space.pk,
            extraction_method=PlantExtractionMethodChoices.METHOD_CAD_EXPORT,
            source_ref="madison:cad:detailed-space:b1109",
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            is_authoritative=True,
            metadata={"review_state": "approved", "boundary_status": "approved"},
        )

    def test_updates_space_geometry_and_demotes_provenance_to_review_required(self):
        result = update_physical_space_geometry_from_visual_review(
            self.space.pk,
            x="25",
            y="35",
            width="55",
            depth="25",
            reviewer="operator",
            notes="Aligned to the rendered wall line.",
            site=self.site,
            spatial_frame=self.frame,
        )

        self.assertTrue(result.changed)
        self.assertEqual(result.original_geometry["x"], "20.000")
        self.assertEqual(result.updated_geometry["x"], "25.000")
        self.assertEqual(result.updated_geometry["y"], "35.000")
        self.assertEqual(result.updated_geometry["width"], "55.000")
        self.assertEqual(result.updated_geometry["depth"], "25.000")
        self.assertEqual(result.updated_geometry["x_max"], "80.000")
        self.assertEqual(result.updated_geometry["y_max"], "60.000")
        self.assertEqual(result.updated_geometry["coordinate_source"], VISUAL_GEOMETRY_SOURCE)
        self.assertEqual(
            result.updated_geometry["source_coordinate_source"],
            "madison_cad_detailed_space_decomposition",
        )

        self.space.refresh_from_db()
        self.assertEqual(self.space.confidence, SpatialConfidenceChoices.CONFIDENCE_DERIVED)
        self.assertEqual(self.space.boundary_geometry, result.updated_geometry)
        self.assertEqual(self.space.metadata["review_state"], VISUAL_GEOMETRY_REVIEW_STATE)
        self.assertEqual(self.space.metadata["boundary_status"], VISUAL_GEOMETRY_REVIEW_STATE)
        self.assertEqual(self.space.metadata["geometry_review_state"], VISUAL_GEOMETRY_CORRECTED_STATE)
        self.assertEqual(self.space.metadata["geometry_review_method"], "visual_spatial_review")
        self.assertEqual(self.space.metadata["geometry_reviewed_by"], "operator")
        self.assertEqual(self.space.metadata["geometry_review_notes"], "Aligned to the rendered wall line.")
        self.assertEqual(len(self.space.metadata["visual_geometry_review_history"]), 1)

        self.provenance.refresh_from_db()
        self.assertEqual(result.provenance.pk, self.provenance.pk)
        self.assertFalse(self.provenance.is_authoritative)
        self.assertEqual(self.provenance.confidence, SpatialConfidenceChoices.CONFIDENCE_DERIVED)
        self.assertEqual(self.provenance.metadata["review_state"], VISUAL_GEOMETRY_REVIEW_STATE)
        self.assertEqual(self.provenance.metadata["boundary_status"], VISUAL_GEOMETRY_REVIEW_STATE)
        self.assertEqual(
            self.provenance.metadata["latest_visual_geometry_review"]["updated_geometry"],
            result.updated_geometry,
        )

    def test_approves_corrected_space_geometry_and_promotes_provenance(self):
        update_physical_space_geometry_from_visual_review(
            self.space.pk,
            x="25",
            y="35",
            width="55",
            depth="25",
            reviewer="operator",
            notes="Aligned to the rendered wall line.",
            site=self.site,
            spatial_frame=self.frame,
        )

        result = approve_visual_geometry_correction(
            self.space.pk,
            reviewer="lead-operator",
            notes="Visual overlay checked.",
            site=self.site,
            spatial_frame=self.frame,
        )

        self.assertTrue(result.approved)
        self.space.refresh_from_db()
        self.assertEqual(self.space.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(self.space.metadata["review_state"], VISUAL_GEOMETRY_APPROVED_STATE)
        self.assertEqual(self.space.metadata["boundary_status"], VISUAL_GEOMETRY_APPROVED_STATE)
        self.assertEqual(self.space.metadata["geometry_review_state"], VISUAL_GEOMETRY_APPROVED_STATE)
        self.assertEqual(self.space.metadata["geometry_review_approved_by"], "lead-operator")
        self.assertEqual(self.space.metadata["geometry_review_approval_notes"], "Visual overlay checked.")
        self.assertEqual(self.space.metadata["boundary_review_method"], "visual_spatial_review")

        self.provenance.refresh_from_db()
        self.assertTrue(self.provenance.is_authoritative)
        self.assertEqual(self.provenance.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertEqual(self.provenance.metadata["review_state"], VISUAL_GEOMETRY_APPROVED_STATE)
        self.assertEqual(self.provenance.metadata["geometry_review_state"], VISUAL_GEOMETRY_APPROVED_STATE)

    def test_approval_requires_a_pending_visual_geometry_correction(self):
        with self.assertRaisesMessage(ValueError, "does not have a visual geometry correction"):
            approve_visual_geometry_correction(
                self.space.pk,
                reviewer="lead-operator",
                site=self.site,
                spatial_frame=self.frame,
            )

    def test_rejects_space_geometry_outside_the_spatial_frame(self):
        with self.assertRaisesMessage(ValueError, "fit inside the spatial frame width"):
            update_physical_space_geometry_from_visual_review(
                self.space.pk,
                x="190",
                y="35",
                width="20",
                depth="25",
                site=self.site,
                spatial_frame=self.frame,
            )

    def test_rejects_space_outside_the_current_site_scope(self):
        with self.assertRaisesMessage(ValueError, "does not belong to the current site"):
            update_physical_space_geometry_from_visual_review(
                self.space.pk,
                x="25",
                y="35",
                width="55",
                depth="25",
                site=self.other_site,
                spatial_frame=self.frame,
            )
