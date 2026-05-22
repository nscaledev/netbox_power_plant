from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PlantExtractionMethodChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    PowerSystem,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.physical_plant import (
    bind_physical_element_to_object,
    bind_spatial_placement_to_object,
    build_physical_scope_summary,
    create_provenance_record,
    get_bindings_for_object,
    get_physical_elements_for_object,
    get_spatial_placements_for_object,
)


class PhysicalPlantServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Primary Site", slug="primary-site")
        cls.location = Location.objects.create(site=cls.site, name="Electrical Room A", slug="electrical-room-a")
        cls.power_system = PowerSystem.objects.create(
            name="Primary Hall Power",
            slug="primary-hall-power",
            site=cls.site,
            location=cls.location,
        )
        cls.node = ElectricalNode.objects.create(
            name="UPS A",
            slug="ups-a",
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.element_type = PhysicalElementType.objects.create(
            name="UPS Element Type",
            slug="ups-element-type",
            element_kind=PhysicalElementKindChoices.KIND_UPS,
        )
        cls.space = PhysicalSpace.objects.create(
            name="Electrical Room A Space",
            slug="electrical-room-a-space",
            site=cls.site,
            location=cls.location,
        )
        cls.element = PhysicalElement.objects.create(
            name="UPS A Element",
            slug="ups-a-element",
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.space,
        )
        cls.frame = SpatialFrame.objects.create(
            name="Electrical Room A Frame",
            slug="electrical-room-a-frame",
            site=cls.site,
            location=cls.location,
        )

        cls.other_site = Site.objects.create(name="Other Site", slug="other-site")
        cls.other_location = Location.objects.create(site=cls.other_site, name="Other Room", slug="other-room")
        cls.other_power_system = PowerSystem.objects.create(
            name="Other Hall Power",
            slug="other-hall-power",
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.other_node = ElectricalNode.objects.create(
            name="Other UPS",
            slug="other-ups",
            power_system=cls.other_power_system,
            site=cls.other_site,
            location=cls.other_location,
            node_kind=NodeKindChoices.KIND_UPS,
        )

    def test_binding_helpers_create_and_lookup_physical_element_binding(self):
        binding = bind_physical_element_to_object(
            self.element,
            self.node,
            binding_role=PhysicalObjectBindingRoleChoices.ROLE_TOPOLOGY_NODE_FOR,
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            is_primary=True,
            metadata={"matched_by": "source_label"},
        )

        self.assertEqual(
            binding.assigned_object_type,
            ContentType.objects.get_for_model(self.node, for_concrete_model=False),
        )
        self.assertEqual(binding.assigned_object_id, self.node.pk)
        self.assertEqual(binding.physical_element, self.element)
        self.assertEqual(binding.binding_role, PhysicalObjectBindingRoleChoices.ROLE_TOPOLOGY_NODE_FOR)
        self.assertEqual(binding.confidence, SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE)
        self.assertTrue(binding.is_primary)
        self.assertEqual(binding.metadata, {"matched_by": "source_label"})
        self.assertEqual(list(get_bindings_for_object(self.node)), [binding])
        self.assertEqual(list(get_physical_elements_for_object(self.node)), [self.element])

    def test_spatial_placement_binding_is_returned_for_object(self):
        placement = self._create_placement("UPS A Footprint", "ups-a-footprint", self.element)

        binding = bind_spatial_placement_to_object(
            placement,
            self.node,
            physical_element=self.element,
            binding_role=PhysicalObjectBindingRoleChoices.ROLE_PLACEMENT_FOR,
            confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
        )

        self.assertEqual(binding.spatial_placement, placement)
        self.assertEqual(binding.physical_element, self.element)
        self.assertEqual(list(get_spatial_placements_for_object(self.node)), [placement])
        self.assertEqual(list(get_spatial_placements_for_object(self.element)), [placement])

    def test_create_provenance_record_infers_source_hierarchy(self):
        source_document = PlantSourceDocument.objects.create(
            name="Electrical Plan",
            slug="electrical-plan",
            site=self.site,
            location=self.location,
        )
        source_sheet = PlantSourceSheet.objects.create(
            name="Electrical Plan E1",
            slug="electrical-plan-e1",
            source_document=source_document,
            sheet_number="E1",
        )
        source_layer = PlantSourceLayer.objects.create(
            name="Electrical Equipment Layer",
            slug="electrical-equipment-layer",
            source_sheet=source_sheet,
            layer_name="E-EQPM",
        )

        record = create_provenance_record(
            self.element,
            source_layer=source_layer,
            extraction_method=PlantExtractionMethodChoices.METHOD_PARSED_SVG,
            source_ref="symbol:ups-a",
            confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            is_authoritative=True,
            metadata={"bbox": [10, 20, 30, 40]},
        )

        self.assertEqual(
            record.assigned_object_type,
            ContentType.objects.get_for_model(self.element, for_concrete_model=False),
        )
        self.assertEqual(record.assigned_object_id, self.element.pk)
        self.assertEqual(record.source_document, source_document)
        self.assertEqual(record.source_sheet, source_sheet)
        self.assertEqual(record.source_layer, source_layer)
        self.assertEqual(record.extraction_method, PlantExtractionMethodChoices.METHOD_PARSED_SVG)
        self.assertEqual(record.source_ref, "symbol:ups-a")
        self.assertEqual(record.confidence, SpatialConfidenceChoices.CONFIDENCE_DERIVED)
        self.assertTrue(record.is_authoritative)
        self.assertEqual(record.metadata, {"bbox": [10, 20, 30, 40]})
        self.assertEqual(PlantProvenance.objects.count(), 1)

    def test_scope_summary_counts_filtered_physical_inventory(self):
        placed_element = self._create_element("Placed UPS Element", "placed-ups-element")
        bound_unplaced_element = self._create_element("Bound Unplaced UPS Element", "bound-unplaced-ups-element")
        placement = self._create_placement("Placed UPS Footprint", "placed-ups-footprint", placed_element)
        bind_spatial_placement_to_object(placement, self.node, physical_element=placed_element)
        bind_physical_element_to_object(bound_unplaced_element, self.node)
        self._create_out_of_scope_inventory()

        summary = build_physical_scope_summary(site=self.site, location=self.location)

        self.assertEqual(
            summary,
            {
                "spaces": 1,
                "elements": 3,
                "placements": 1,
                "bindings": 2,
                "unbound_elements": 1,
                "unplaced_elements": 2,
            },
        )

    def _create_element(self, name, slug):
        return PhysicalElement.objects.create(
            name=name,
            slug=slug,
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.space,
        )

    def _create_placement(self, name, slug, element):
        return SpatialPlacement.objects.create(
            name=name,
            slug=slug,
            spatial_frame=self.frame,
            assigned_object_type=ContentType.objects.get_for_model(element, for_concrete_model=False),
            assigned_object_id=element.pk,
            x="10.000",
            y="20.000",
            width="30.000",
            depth="40.000",
        )

    def _create_out_of_scope_inventory(self):
        other_space = PhysicalSpace.objects.create(
            name="Other Room Space",
            slug="other-room-space",
            site=self.other_site,
            location=self.other_location,
        )
        other_element = PhysicalElement.objects.create(
            name="Other UPS Element",
            slug="other-ups-element",
            element_type=self.element_type,
            site=self.other_site,
            location=self.other_location,
            physical_space=other_space,
        )
        other_frame = SpatialFrame.objects.create(
            name="Other Room Frame",
            slug="other-room-frame",
            site=self.other_site,
            location=self.other_location,
        )
        other_placement = SpatialPlacement.objects.create(
            name="Other UPS Footprint",
            slug="other-ups-footprint",
            spatial_frame=other_frame,
            assigned_object_type=ContentType.objects.get_for_model(other_element, for_concrete_model=False),
            assigned_object_id=other_element.pk,
            x="10.000",
            y="20.000",
        )
        bind_spatial_placement_to_object(other_placement, self.other_node, physical_element=other_element)
        self.assertEqual(PhysicalObjectBinding.objects.filter(physical_element=other_element).count(), 1)
