from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import NodeKindChoices
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


class PhysicalPlantModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.other_site = Site.objects.create(name='Other Site', slug='other-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.same_site_other_location = Location.objects.create(
            site=cls.site,
            name='Electrical Room C',
            slug='electrical-room-c',
        )
        cls.other_location = Location.objects.create(site=cls.other_site, name='Electrical Room B', slug='electrical-room-b')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.other_power_system = PowerSystem.objects.create(
            name='Other Hall Power',
            slug='other-hall-power',
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.node = ElectricalNode.objects.create(
            name='Row PDU A',
            slug='row-pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.other_node = ElectricalNode.objects.create(
            name='Foreign PDU',
            slug='foreign-pdu',
            power_system=cls.other_power_system,
            site=cls.other_site,
            location=cls.other_location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.node_type = ContentType.objects.get_for_model(ElectricalNode)

        cls.source_document = PlantSourceDocument.objects.create(
            name='Primary Electrical Plan',
            slug='primary-electrical-plan',
            site=cls.site,
            location=cls.location,
        )
        cls.other_source_document = PlantSourceDocument.objects.create(
            name='Other Electrical Plan',
            slug='other-electrical-plan',
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.source_sheet = PlantSourceSheet.objects.create(
            name='Primary One-Line Sheet',
            slug='primary-one-line-sheet',
            source_document=cls.source_document,
            sheet_number='E-101',
        )
        cls.other_source_sheet = PlantSourceSheet.objects.create(
            name='Other One-Line Sheet',
            slug='other-one-line-sheet',
            source_document=cls.other_source_document,
            sheet_number='E-201',
        )
        cls.source_layer = PlantSourceLayer.objects.create(
            name='Primary Equipment Layer',
            slug='primary-equipment-layer',
            source_sheet=cls.source_sheet,
            layer_name='EQUIP',
        )
        cls.other_source_layer = PlantSourceLayer.objects.create(
            name='Other Equipment Layer',
            slug='other-equipment-layer',
            source_sheet=cls.other_source_sheet,
            layer_name='EQUIP',
        )

        cls.spatial_frame = SpatialFrame.objects.create(
            name='Primary Room Frame',
            slug='primary-room-frame',
            site=cls.site,
            location=cls.location,
        )
        cls.same_site_other_location_frame = SpatialFrame.objects.create(
            name='Primary Other Room Frame',
            slug='primary-other-room-frame',
            site=cls.site,
            location=cls.same_site_other_location,
        )
        cls.other_site_frame = SpatialFrame.objects.create(
            name='Other Room Frame',
            slug='other-room-frame',
            site=cls.other_site,
            location=cls.other_location,
        )

        cls.element_type = PhysicalElementType.objects.create(
            name='PDU Footprint',
            slug='pdu-footprint',
        )
        cls.physical_space = PhysicalSpace.objects.create(
            name='Primary Electrical Room',
            slug='primary-electrical-room',
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.spatial_frame,
        )
        cls.same_site_other_location_space = PhysicalSpace.objects.create(
            name='Primary Mechanical Room',
            slug='primary-mechanical-room',
            site=cls.site,
            location=cls.same_site_other_location,
            spatial_frame=cls.same_site_other_location_frame,
        )
        cls.other_site_space = PhysicalSpace.objects.create(
            name='Other Electrical Room',
            slug='other-electrical-room',
            site=cls.other_site,
            location=cls.other_location,
            spatial_frame=cls.other_site_frame,
        )
        cls.physical_element = PhysicalElement.objects.create(
            name='PDU A Footprint',
            slug='pdu-a-footprint',
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.physical_space,
        )

        cls.spatial_placement = SpatialPlacement.objects.create(
            name='PDU A Placement',
            slug='pdu-a-placement',
            spatial_frame=cls.spatial_frame,
            assigned_object_type=cls.node_type,
            assigned_object_id=cls.node.pk,
            x='10.000',
            y='20.000',
        )
        cls.other_site_placement = SpatialPlacement.objects.create(
            name='Foreign PDU Placement',
            slug='foreign-pdu-placement',
            spatial_frame=cls.other_site_frame,
            assigned_object_type=cls.node_type,
            assigned_object_id=cls.other_node.pk,
            x='10.000',
            y='20.000',
        )

    def assertValidationErrorField(self, instance, field_name):
        with self.assertRaises(ValidationError) as context:
            instance.full_clean()

        self.assertIn(field_name, context.exception.message_dict)

    def test_source_document_accepts_location_from_same_site(self):
        document = PlantSourceDocument(
            name='Primary As-Built',
            slug='primary-as-built',
            site=self.site,
            location=self.location,
        )

        document.full_clean()

    def test_source_document_rejects_location_from_another_site(self):
        document = PlantSourceDocument(
            name='Wrong Site Source',
            slug='wrong-site-source',
            site=self.site,
            location=self.other_location,
        )

        self.assertValidationErrorField(document, 'location')

    def test_provenance_accepts_consistent_source_document_sheet_and_layer(self):
        provenance = PlantProvenance(
            name='PDU A Provenance',
            slug='pdu-a-provenance',
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
            source_document=self.source_document,
            source_sheet=self.source_sheet,
            source_layer=self.source_layer,
        )

        provenance.full_clean()

    def test_provenance_rejects_sheet_from_another_source_document(self):
        provenance = PlantProvenance(
            name='Mismatched Source Sheet',
            slug='mismatched-source-sheet',
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
            source_document=self.source_document,
            source_sheet=self.other_source_sheet,
        )

        self.assertValidationErrorField(provenance, 'source_sheet')

    def test_provenance_rejects_layer_from_another_source_sheet(self):
        provenance = PlantProvenance(
            name='Mismatched Source Layer',
            slug='mismatched-source-layer',
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
            source_document=self.source_document,
            source_sheet=self.source_sheet,
            source_layer=self.other_source_layer,
        )

        self.assertValidationErrorField(provenance, 'source_layer')

    def test_provenance_rejects_layer_from_another_source_document(self):
        provenance = PlantProvenance(
            name='Mismatched Layer Document',
            slug='mismatched-layer-document',
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
            source_document=self.source_document,
            source_layer=self.other_source_layer,
        )

        self.assertValidationErrorField(provenance, 'source_layer')

    def test_physical_space_accepts_matching_site_location_frame_and_elevation(self):
        space = PhysicalSpace(
            name='Valid Physical Space',
            slug='valid-physical-space',
            site=self.site,
            location=self.location,
            spatial_frame=self.spatial_frame,
            z_min='0.000',
            z_max='12.000',
        )

        space.full_clean()

    def test_physical_space_rejects_location_from_another_site(self):
        space = PhysicalSpace(
            name='Wrong Site Physical Space',
            slug='wrong-site-physical-space',
            site=self.site,
            location=self.other_location,
        )

        self.assertValidationErrorField(space, 'location')

    def test_physical_space_rejects_frame_from_another_site(self):
        space = PhysicalSpace(
            name='Wrong Site Frame Space',
            slug='wrong-site-frame-space',
            site=self.site,
            spatial_frame=self.other_site_frame,
        )

        self.assertValidationErrorField(space, 'spatial_frame')

    def test_physical_space_rejects_frame_location_mismatch(self):
        space = PhysicalSpace(
            name='Wrong Room Frame Space',
            slug='wrong-room-frame-space',
            site=self.site,
            location=self.location,
            spatial_frame=self.same_site_other_location_frame,
        )

        self.assertValidationErrorField(space, 'spatial_frame')

    def test_physical_space_rejects_inverted_elevation_bounds(self):
        space = PhysicalSpace(
            name='Inverted Elevation Space',
            slug='inverted-elevation-space',
            site=self.site,
            z_min='12.000',
            z_max='0.000',
        )

        self.assertValidationErrorField(space, 'z_max')

    def test_physical_element_accepts_matching_site_location_and_space(self):
        element = PhysicalElement(
            name='Valid Physical Element',
            slug='valid-physical-element',
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.physical_space,
        )

        element.full_clean()

    def test_physical_element_rejects_location_from_another_site(self):
        element = PhysicalElement(
            name='Wrong Site Physical Element',
            slug='wrong-site-physical-element',
            element_type=self.element_type,
            site=self.site,
            location=self.other_location,
        )

        self.assertValidationErrorField(element, 'location')

    def test_physical_element_rejects_space_from_another_site(self):
        element = PhysicalElement(
            name='Wrong Site Space Element',
            slug='wrong-site-space-element',
            element_type=self.element_type,
            site=self.site,
            physical_space=self.other_site_space,
        )

        self.assertValidationErrorField(element, 'physical_space')

    def test_physical_element_rejects_space_location_mismatch(self):
        element = PhysicalElement(
            name='Wrong Room Space Element',
            slug='wrong-room-space-element',
            element_type=self.element_type,
            site=self.site,
            location=self.location,
            physical_space=self.same_site_other_location_space,
        )

        self.assertValidationErrorField(element, 'physical_space')

    def test_physical_object_binding_accepts_physical_element_only(self):
        binding = PhysicalObjectBinding(
            name='PDU A Element Binding',
            slug='pdu-a-element-binding',
            physical_element=self.physical_element,
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
        )

        binding.full_clean()

    def test_physical_object_binding_accepts_spatial_placement_only(self):
        binding = PhysicalObjectBinding(
            name='PDU A Placement Binding',
            slug='pdu-a-placement-binding',
            spatial_placement=self.spatial_placement,
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
        )

        binding.full_clean()

    def test_physical_object_binding_requires_element_or_spatial_placement(self):
        binding = PhysicalObjectBinding(
            name='Missing Physical Target Binding',
            slug='missing-physical-target-binding',
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
        )

        self.assertValidationErrorField(binding, 'physical_element')

    def test_physical_object_binding_rejects_cross_site_element_and_placement(self):
        binding = PhysicalObjectBinding(
            name='Cross Site Physical Binding',
            slug='cross-site-physical-binding',
            physical_element=self.physical_element,
            spatial_placement=self.other_site_placement,
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
        )

        self.assertValidationErrorField(binding, 'spatial_placement')
