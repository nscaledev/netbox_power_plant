from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PhysicalElementKindChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PowerSystem,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.physical_validation import (
    build_physical_plant_health_summary,
    run_physical_plant_checks,
)


class PhysicalPlantValidationServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Primary Site", slug="primary-site")
        cls.other_site = Site.objects.create(name="Other Site", slug="other-site")
        cls.location = Location.objects.create(site=cls.site, name="Electrical Room A", slug="electrical-room-a")
        cls.other_location = Location.objects.create(site=cls.other_site, name="Electrical Room B", slug="electrical-room-b")
        cls.power_system = PowerSystem.objects.create(
            name="Primary Hall Power",
            slug="primary-hall-power",
            site=cls.site,
            location=cls.location,
        )
        cls.other_power_system = PowerSystem.objects.create(
            name="Other Hall Power",
            slug="other-hall-power",
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.node = ElectricalNode.objects.create(
            name="UPS A",
            slug="ups-a",
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.other_node = ElectricalNode.objects.create(
            name="Other UPS",
            slug="other-ups",
            power_system=cls.other_power_system,
            site=cls.other_site,
            location=cls.other_location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.element_type = PhysicalElementType.objects.create(
            name="UPS Footprint",
            slug="validation-ups-footprint",
            element_kind=PhysicalElementKindChoices.KIND_UPS,
            default_height="4.000",
        )
        cls.space = PhysicalSpace.objects.create(
            name="Electrical Room A Space",
            slug="validation-electrical-room-a-space",
            site=cls.site,
            location=cls.location,
            z_min="0.000",
            z_max="3.000",
        )
        cls.frame = SpatialFrame.objects.create(
            name="Electrical Room A Frame",
            slug="validation-electrical-room-a-frame",
            site=cls.site,
            location=cls.location,
            width="10.000",
            height="10.000",
        )
        cls.source_document = PlantSourceDocument.objects.create(
            name="Validation Electrical Plan",
            slug="validation-electrical-plan",
            site=cls.site,
            location=cls.location,
        )

    def test_reports_unbound_unplaced_and_missing_provenance_for_blueprint_element(self):
        element = PhysicalElement.objects.create(
            name="Unmodeled UPS Footprint",
            slug="unmodeled-ups-footprint",
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.space,
            source_label="UPS-X",
            metadata={"source_key": "UPS-X"},
        )

        findings = run_physical_plant_checks(power_system=self.power_system)
        finding_types = {finding.finding_type for finding in findings if finding.object == element}

        self.assertIn("unbound_physical_element", finding_types)
        self.assertIn("unplaced_physical_element", finding_types)
        self.assertIn("source_provenance_missing", finding_types)

    def test_reports_out_of_bounds_and_elevation_placement_findings(self):
        element = PhysicalElement.objects.create(
            name="Placed UPS Footprint",
            slug="placed-ups-footprint",
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.space,
            source_label="UPS-A",
        )
        PlantProvenance.objects.create(
            name="Placed UPS Provenance",
            slug="placed-ups-provenance",
            assigned_object_type=ContentType.objects.get_for_model(element),
            assigned_object_id=element.pk,
            source_document=self.source_document,
        )
        SpatialPlacement.objects.create(
            name="Bad UPS Placement",
            slug="bad-ups-placement",
            spatial_frame=self.frame,
            assigned_object_type=ContentType.objects.get_for_model(element),
            assigned_object_id=element.pk,
            x="9.000",
            y="9.000",
            z="2.000",
            width="4.000",
            depth="4.000",
            height="4.000",
        )

        findings = run_physical_plant_checks(power_system=self.power_system)
        finding_types = {finding.finding_type for finding in findings}

        self.assertIn("placement_outside_frame_bounds", finding_types)
        self.assertIn("placement_outside_space_elevation", finding_types)

    def test_reports_binding_scope_and_duplicate_primary_binding_findings(self):
        element = PhysicalElement.objects.create(
            name="Bound UPS Footprint",
            slug="bound-ups-footprint",
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.space,
        )
        assigned_object_type = ContentType.objects.get_for_model(self.other_node)
        for index in (1, 2):
            PhysicalObjectBinding.objects.create(
                name=f"Bad Binding {index}",
                slug=f"bad-binding-{index}",
                physical_element=element,
                assigned_object_type=assigned_object_type,
                assigned_object_id=self.other_node.pk,
                is_primary=True,
            )

        findings = run_physical_plant_checks(power_system=self.power_system)
        finding_types = {finding.finding_type for finding in findings}

        self.assertIn("binding_site_mismatch", finding_types)
        self.assertIn("duplicate_primary_binding", finding_types)

    def test_health_summary_includes_scope_counts_and_finding_counts(self):
        PhysicalElement.objects.create(
            name="Summary UPS Footprint",
            slug="summary-ups-footprint",
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.space,
        )

        summary = build_physical_plant_health_summary(power_system=self.power_system)

        self.assertFalse(summary.is_healthy)
        self.assertEqual(summary.scope_summary["spaces"], 1)
        self.assertEqual(summary.scope_summary["elements"], 1)
        self.assertGreater(summary.finding_counts["unbound_physical_element"], 0)
