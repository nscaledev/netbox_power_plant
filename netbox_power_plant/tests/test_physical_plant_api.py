from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from dcim.models import Location, Site
from utilities.testing import APITestCase

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantExtractionMethodChoices,
    PlantSourceLayerKindChoices,
    PlantSourceTypeChoices,
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
    PowerSystem,
    SpatialFrame,
    SpatialPlacement,
)


class PhysicalPlantAPITestCase(APITestCase):
    view_namespace = 'plugins-api:netbox_power_plant'

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.power_system_type = ContentType.objects.get_for_model(PowerSystem)

        cls.source_document = PlantSourceDocument.objects.create(
            name='Electrical Plan Set',
            slug='electrical-plan-set',
            site=cls.site,
            location=cls.location,
            source_type=PlantSourceTypeChoices.TYPE_PDF,
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
            document_id='E-100',
            revision='A',
        )
        cls.source_sheet = PlantSourceSheet.objects.create(
            name='Level 1 Power',
            slug='level-1-power',
            source_document=cls.source_document,
            sheet_number='E1.01',
            title='Level 1 Power Plan',
            page_index=1,
        )
        cls.source_layer = PlantSourceLayer.objects.create(
            name='Electrical Equipment Layer',
            slug='electrical-equipment-layer',
            source_sheet=cls.source_sheet,
            layer_name='E-Equipment',
            layer_kind=PlantSourceLayerKindChoices.KIND_EQUIPMENT,
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
        )

        cls.spatial_frame = SpatialFrame.objects.create(
            name='Room Frame',
            slug='room-frame',
            site=cls.site,
            location=cls.location,
        )
        cls.spatial_placement = SpatialPlacement.objects.create(
            name='Power System Placement',
            slug='power-system-placement',
            spatial_frame=cls.spatial_frame,
            assigned_object_type=cls.power_system_type,
            assigned_object_id=cls.power_system.pk,
            x='10.000',
            y='20.000',
        )
        cls.physical_space = PhysicalSpace.objects.create(
            name='Electrical Room A',
            slug='physical-electrical-room-a',
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.spatial_frame,
            space_kind=PhysicalSpaceKindChoices.KIND_ELECTRICAL_ROOM,
        )
        cls.element_type = PhysicalElementType.objects.create(
            name='UPS Footprint',
            slug='ups-footprint',
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
            element_kind=PhysicalElementKindChoices.KIND_UPS,
        )
        cls.physical_element = PhysicalElement.objects.create(
            name='UPS A Footprint',
            slug='ups-a-footprint',
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.physical_space,
            label='UPS-A',
        )
        cls.binding = PhysicalObjectBinding.objects.create(
            name='UPS A Power System Binding',
            slug='ups-a-power-system-binding',
            physical_element=cls.physical_element,
            spatial_placement=cls.spatial_placement,
            assigned_object_type=cls.power_system_type,
            assigned_object_id=cls.power_system.pk,
            binding_role=PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
        )
        cls.provenance = PlantProvenance.objects.create(
            name='UPS A Extraction',
            slug='ups-a-extraction',
            assigned_object_type=cls.power_system_type,
            assigned_object_id=cls.power_system.pk,
            source_document=cls.source_document,
            source_sheet=cls.source_sheet,
            source_layer=cls.source_layer,
            extraction_method=PlantExtractionMethodChoices.METHOD_MANUAL,
        )

    def test_api_root_includes_physical_plant_endpoints(self):
        response = self.client.get(reverse('plugins-api:netbox_power_plant-api:api-root'), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('plant-source-documents', response.data)
        self.assertIn('plant-source-sheets', response.data)
        self.assertIn('plant-source-layers', response.data)
        self.assertIn('plant-provenance-records', response.data)
        self.assertIn('physical-spaces', response.data)
        self.assertIn('physical-element-types', response.data)
        self.assertIn('physical-elements', response.data)
        self.assertIn('physical-object-bindings', response.data)

    def test_source_document_sheet_layer_list_and_create(self):
        self.add_permissions(
            'netbox_power_plant.view_plantsourcedocument',
            'netbox_power_plant.add_plantsourcedocument',
            'netbox_power_plant.view_plantsourcesheet',
            'netbox_power_plant.add_plantsourcesheet',
            'netbox_power_plant.view_plantsourcelayer',
            'netbox_power_plant.add_plantsourcelayer',
            'netbox_power_plant.view_plantprovenance',
            'netbox_power_plant.add_plantprovenance',
        )

        document_url = reverse('plugins-api:netbox_power_plant-api:plantsourcedocument-list')
        sheet_url = reverse('plugins-api:netbox_power_plant-api:plantsourcesheet-list')
        layer_url = reverse('plugins-api:netbox_power_plant-api:plantsourcelayer-list')
        provenance_url = reverse('plugins-api:netbox_power_plant-api:plantprovenance-list')

        response = self.client.get(document_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            document_url,
            {
                'name': 'Telecom Plan Set',
                'slug': 'telecom-plan-set',
                'site': self.site.pk,
                'location': self.location.pk,
                'source_type': PlantSourceTypeChoices.TYPE_SVG,
                'discipline': PlantDisciplineChoices.DISCIPLINE_TELECOM,
                'document_id': 'T-100',
                'revision': 'B',
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        document_id = response.data['id']
        self.assertEqual(response.data['source_type']['value'], PlantSourceTypeChoices.TYPE_SVG)

        response = self.client.get(sheet_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            sheet_url,
            {
                'name': 'Level 1 Telecom',
                'slug': 'level-1-telecom',
                'source_document': document_id,
                'sheet_number': 'T1.01',
                'title': 'Level 1 Telecom Plan',
                'page_index': 2,
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        sheet_id = response.data['id']

        response = self.client.get(layer_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            layer_url,
            {
                'name': 'Telecom Pathway Layer',
                'slug': 'telecom-pathway-layer',
                'source_sheet': sheet_id,
                'layer_name': 'T-Pathway',
                'layer_kind': PlantSourceLayerKindChoices.KIND_PATHWAY,
                'discipline': PlantDisciplineChoices.DISCIPLINE_TELECOM,
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        layer_id = response.data['id']
        self.assertEqual(response.data['layer_kind']['value'], PlantSourceLayerKindChoices.KIND_PATHWAY)

        response = self.client.post(
            provenance_url,
            {
                'name': 'Telecom Extraction',
                'slug': 'telecom-extraction',
                'assigned_object_type': self.power_system_type.pk,
                'assigned_object_id': self.power_system.pk,
                'source_document': document_id,
                'source_sheet': sheet_id,
                'source_layer': layer_id,
                'extraction_method': PlantExtractionMethodChoices.METHOD_MANUAL,
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        self.assertEqual(response.data['assigned_object']['id'], self.power_system.pk)

    def test_physical_space_element_type_element_list_and_create(self):
        self.add_permissions(
            'netbox_power_plant.view_physicalspace',
            'netbox_power_plant.add_physicalspace',
            'netbox_power_plant.view_physicalelementtype',
            'netbox_power_plant.add_physicalelementtype',
            'netbox_power_plant.view_physicalelement',
            'netbox_power_plant.add_physicalelement',
        )

        space_url = reverse('plugins-api:netbox_power_plant-api:physicalspace-list')
        type_url = reverse('plugins-api:netbox_power_plant-api:physicalelementtype-list')
        element_url = reverse('plugins-api:netbox_power_plant-api:physicalelement-list')

        response = self.client.get(space_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            space_url,
            {
                'name': 'Battery Room',
                'slug': 'battery-room',
                'site': self.site.pk,
                'location': self.location.pk,
                'spatial_frame': self.spatial_frame.pk,
                'space_kind': PhysicalSpaceKindChoices.KIND_ROOM,
                'floor_label': 'L1',
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        space_id = response.data['id']
        self.assertEqual(response.data['space_kind']['value'], PhysicalSpaceKindChoices.KIND_ROOM)

        response = self.client.get(type_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            type_url,
            {
                'name': 'Battery Cabinet',
                'slug': 'battery-cabinet',
                'discipline': PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
                'element_kind': PhysicalElementKindChoices.KIND_CUSTOM,
                'symbol_key': 'battery-cabinet',
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        element_type_id = response.data['id']

        response = self.client.get(element_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            element_url,
            {
                'name': 'Battery Cabinet A',
                'slug': 'battery-cabinet-a',
                'element_type': element_type_id,
                'site': self.site.pk,
                'location': self.location.pk,
                'physical_space': space_id,
                'label': 'BAT-A',
            },
            format='json',
            **self.header,
        )
        self.assertHttpStatus(response, 201)
        self.assertEqual(response.data['element_type']['id'], element_type_id)
        self.assertEqual(response.data['physical_space']['id'], space_id)

    def test_physical_object_binding_list_and_create(self):
        self.add_permissions(
            'netbox_power_plant.view_physicalobjectbinding',
            'netbox_power_plant.add_physicalobjectbinding',
        )
        binding_url = reverse('plugins-api:netbox_power_plant-api:physicalobjectbinding-list')

        response = self.client.get(binding_url, **self.header)
        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post(
            binding_url,
            {
                'name': 'UPS A Primary Binding',
                'slug': 'ups-a-primary-binding',
                'physical_element': self.physical_element.pk,
                'spatial_placement': self.spatial_placement.pk,
                'assigned_object_type': self.power_system_type.pk,
                'assigned_object_id': self.power_system.pk,
                'binding_role': PhysicalObjectBindingRoleChoices.ROLE_SOURCE_OF_TRUTH,
                'is_primary': True,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertEqual(response.data['physical_element']['id'], self.physical_element.pk)
        self.assertEqual(response.data['spatial_placement']['id'], self.spatial_placement.pk)
        self.assertEqual(response.data['assigned_object']['id'], self.power_system.pk)
        self.assertEqual(response.data['binding_role']['value'], PhysicalObjectBindingRoleChoices.ROLE_SOURCE_OF_TRUTH)
