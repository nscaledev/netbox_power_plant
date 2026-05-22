from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Location, Rack, Site

from netbox_power_plant.choices import PhysicalElementKindChoices
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.physical_validation import run_physical_plant_checks


class MadisonUnderlayValidationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Madison Site", slug="madison-site")
        cls.location = Location.objects.create(site=cls.site, name="Madison Hall", slug="madison-hall")
        cls.other_site = Site.objects.create(name="Other Madison Site", slug="other-madison-site")
        cls.rack_type = ContentType.objects.get_for_model(Rack, for_concrete_model=False)
        cls.element_type = ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False)
        cls.rack_footprint_type = PhysicalElementType.objects.create(
            name="Madison Rack Footprint",
            slug="madison-rack-footprint",
            element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
        )
        cls.space = PhysicalSpace.objects.create(
            name="Madison Rack Hall",
            slug="madison-rack-hall",
            site=cls.site,
            location=cls.location,
        )
        cls.frame = SpatialFrame.objects.create(
            name="Madison Underlay Frame",
            slug="madison-underlay-frame",
            site=cls.site,
            location=cls.location,
            width="100.000",
            height="100.000",
        )

    def test_reports_netbox_rack_without_physical_footprint_binding(self):
        rack = Rack.objects.create(name="Rack M01", site=self.site, location=self.location)
        Rack.objects.create(name="Rack Other", site=self.other_site)

        findings = run_physical_plant_checks(site=self.site)

        self.assertFinding(findings, "unbound_netbox_rack", rack)
        self.assertFalse(
            any(
                finding.finding_type == "unbound_netbox_rack" and finding.object.site == self.other_site
                for finding in findings
            )
        )

    def test_reports_duplicate_rack_footprint_elements_for_same_netbox_rack(self):
        rack = Rack.objects.create(name="Rack M02", site=self.site, location=self.location)
        first_element = self.create_rack_footprint("Rack M02 Footprint A", "rack-m02-footprint-a")
        second_element = self.create_rack_footprint("Rack M02 Footprint B", "rack-m02-footprint-b")

        self.bind_rack(first_element, rack, "rack-m02-binding-a")
        self.bind_rack(second_element, rack, "rack-m02-binding-b")

        findings = run_physical_plant_checks(site=self.site)
        finding = self.assertFinding(findings, "duplicate_rack_footprint_binding")

        self.assertEqual(finding.details["element_count"], 2)
        self.assertEqual(finding.related_object, rack)

    def test_reports_rack_footprints_with_same_frame_and_coordinates(self):
        first_element = self.create_rack_footprint("Rack M03 Footprint", "rack-m03-footprint")
        second_element = self.create_rack_footprint("Rack M04 Footprint", "rack-m04-footprint")

        first_placement = self.create_placement("Rack M03 Placement", "rack-m03-placement", first_element)
        self.create_placement("Rack M04 Placement", "rack-m04-placement", second_element)

        findings = run_physical_plant_checks(site=self.site)
        finding = self.assertFinding(findings, "overlapping_rack_footprint_placement", first_placement)

        self.assertEqual(finding.related_object, self.frame)
        self.assertEqual(finding.details["placement_count"], 2)
        self.assertEqual(finding.details["x"], "10.000")
        self.assertEqual(finding.details["y"], "20.000")

    def test_reports_source_documents_without_provenance_or_modeled_objects(self):
        empty_document = PlantSourceDocument.objects.create(
            name="Madison Empty Underlay",
            slug="madison-empty-underlay",
            site=self.site,
            location=self.location,
        )
        stale_document = PlantSourceDocument.objects.create(
            name="Madison Stale Underlay",
            slug="madison-stale-underlay",
            site=self.site,
            location=self.location,
        )
        modeled_document = PlantSourceDocument.objects.create(
            name="Madison Modeled Underlay",
            slug="madison-modeled-underlay",
            site=self.site,
            location=self.location,
        )
        modeled_element = self.create_rack_footprint("Rack M05 Footprint", "rack-m05-footprint")
        PlantProvenance.objects.create(
            name="Stale Madison Underlay Provenance",
            slug="stale-madison-underlay-provenance",
            assigned_object_type=self.element_type,
            assigned_object_id=999999,
            source_document=stale_document,
        )
        PlantProvenance.objects.create(
            name="Modeled Madison Underlay Provenance",
            slug="modeled-madison-underlay-provenance",
            assigned_object_type=self.element_type,
            assigned_object_id=modeled_element.pk,
            source_document=modeled_document,
        )

        findings = run_physical_plant_checks(site=self.site)

        self.assertFinding(findings, "source_document_without_provenance", empty_document)
        self.assertFinding(findings, "source_document_without_modeled_objects", stale_document)
        self.assertFalse(
            any(
                finding.finding_type.startswith("source_document_without_") and finding.object == modeled_document
                for finding in findings
            )
        )

    def create_rack_footprint(self, name, slug):
        return PhysicalElement.objects.create(
            name=name,
            slug=slug,
            element_type=self.rack_footprint_type,
            site=self.site,
            location=self.location,
            physical_space=self.space,
        )

    def create_placement(self, name, slug, element):
        return SpatialPlacement.objects.create(
            name=name,
            slug=slug,
            spatial_frame=self.frame,
            assigned_object_type=self.element_type,
            assigned_object_id=element.pk,
            x="10.000",
            y="20.000",
            z="0.000",
            width="2.000",
            depth="4.000",
        )

    def bind_rack(self, element, rack, slug):
        return PhysicalObjectBinding.objects.create(
            name=slug.replace("-", " ").title(),
            slug=slug,
            physical_element=element,
            assigned_object_type=self.rack_type,
            assigned_object_id=rack.pk,
        )

    def assertFinding(self, findings, finding_type, obj=None):
        for finding in findings:
            if finding.finding_type == finding_type and (obj is None or finding.object == obj):
                return finding
        found = [(finding.finding_type, finding.object) for finding in findings]
        self.fail(f"Expected finding {finding_type!r} for {obj!r}; found {found!r}.")
