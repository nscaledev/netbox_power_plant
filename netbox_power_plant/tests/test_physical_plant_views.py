from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from dcim.models import Location, Site
from utilities.testing import TestCase
from utilities.testing.utils import post_data

from netbox_power_plant.choices import (
    DesignStateChoices,
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantSourceLayerKindChoices,
    PlantSourceTypeChoices,
    SpatialConfidenceChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    PowerSystem,
)


class PhysicalPlantViewTestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_plantsourcedocument',
        'netbox_power_plant.view_plantsourcesheet',
        'netbox_power_plant.view_plantsourcelayer',
        'netbox_power_plant.view_physicalspace',
        'netbox_power_plant.view_physicalelementtype',
        'netbox_power_plant.view_physicalelement',
        'netbox_power_plant.view_physicalobjectbinding',
    )

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
        cls.source_document = PlantSourceDocument.objects.create(
            name='Electrical One-Line Package',
            slug='electrical-one-line-package',
            site=cls.site,
            location=cls.location,
            source_type=PlantSourceTypeChoices.TYPE_PDF,
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
            document_id='E-101',
            revision='A',
        )
        cls.source_sheet = PlantSourceSheet.objects.create(
            name='E-101 Sheet',
            slug='e-101-sheet',
            source_document=cls.source_document,
            sheet_number='E-101',
            title='Electrical Room Plan',
            scale='1/8 inch = 1 foot',
            page_index=1,
        )
        cls.source_layer = PlantSourceLayer.objects.create(
            name='Equipment Layer',
            slug='equipment-layer',
            source_sheet=cls.source_sheet,
            layer_name='EQUIP',
            layer_kind=PlantSourceLayerKindChoices.KIND_EQUIPMENT,
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
        )
        cls.physical_space = PhysicalSpace.objects.create(
            name='Electrical Room A Space',
            slug='electrical-room-a-space',
            site=cls.site,
            location=cls.location,
            space_kind=PhysicalSpaceKindChoices.KIND_ELECTRICAL_ROOM,
            floor_label='L1',
            source_document=cls.source_document.name,
            source_ref='E-101',
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        )
        cls.element_type = PhysicalElementType.objects.create(
            name='Rack Footprint',
            slug='rack-footprint',
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
            element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
            default_color='9e9e9e',
        )
        cls.physical_element = PhysicalElement.objects.create(
            name='Rack A1 Footprint',
            slug='rack-a1-footprint',
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.physical_space,
            label='Rack A1',
            role='Rack footprint',
            install_state=TopologyStateChoices.STATE_PLANNED,
            design_state=DesignStateChoices.STATE_PLANNED,
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        )
        cls.assigned_object_type = ContentType.objects.get_for_model(PowerSystem)
        cls.binding = PhysicalObjectBinding.objects.create(
            name='Rack A1 Power System Binding',
            slug='rack-a1-power-system-binding',
            physical_element=cls.physical_element,
            assigned_object_type=cls.assigned_object_type,
            assigned_object_id=cls.power_system.pk,
            binding_role=PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            is_primary=True,
        )

    def test_representative_list_pages_render(self):
        for url_name, expected_text in (
            ('plugins:netbox_power_plant:plantsourcedocument_list', self.source_document.name),
            ('plugins:netbox_power_plant:physicalspace_list', self.physical_space.name),
            ('plugins:netbox_power_plant:physicalelement_list', self.physical_element.name),
            ('plugins:netbox_power_plant:physicalobjectbinding_list', self.binding.name),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertHttpStatus(response, 200)
                self.assertContains(response, expected_text)

    def test_representative_detail_pages_render(self):
        for url_name, pk, expected_text in (
            ('plugins:netbox_power_plant:plantsourcedocument', self.source_document.pk, 'Plant Source Document Details'),
            ('plugins:netbox_power_plant:physicalspace', self.physical_space.pk, 'Physical Space Details'),
            ('plugins:netbox_power_plant:physicalelement', self.physical_element.pk, 'Physical Element Details'),
            ('plugins:netbox_power_plant:physicalobjectbinding', self.binding.pk, 'Physical Object Binding Details'),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs={'pk': pk}))
                self.assertHttpStatus(response, 200)
                self.assertContains(response, expected_text)

    def test_source_document_add_and_edit_views_accept_post(self):
        self.add_permissions(
            'netbox_power_plant.add_plantsourcedocument',
            'netbox_power_plant.change_plantsourcedocument',
        )
        response = self.client.post(
            reverse('plugins:netbox_power_plant:plantsourcedocument_add'),
            post_data({
                'name': 'Electrical Riser Package',
                'slug': 'electrical-riser-package',
                'site': self.site,
                'location': self.location,
                'source_type': PlantSourceTypeChoices.TYPE_PDF,
                'discipline': PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
                'document_id': 'E-201',
                'revision': '0',
                'issued_at': '',
                'source_uri': '',
                'checksum': '',
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created = PlantSourceDocument.objects.get(slug='electrical-riser-package')

        response = self.client.post(
            reverse('plugins:netbox_power_plant:plantsourcedocument_edit', kwargs={'pk': created.pk}),
            post_data({
                'name': created.name,
                'slug': created.slug,
                'site': self.site,
                'location': self.location,
                'source_type': PlantSourceTypeChoices.TYPE_PDF,
                'discipline': PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
                'document_id': 'E-201',
                'revision': '1',
                'issued_at': '',
                'source_uri': '',
                'checksum': '',
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created.refresh_from_db()
        self.assertEqual(created.revision, '1')

    def test_physical_space_add_and_edit_views_accept_post(self):
        self.add_permissions(
            'netbox_power_plant.add_physicalspace',
            'netbox_power_plant.change_physicalspace',
        )
        response = self.client.post(
            reverse('plugins:netbox_power_plant:physicalspace_add'),
            post_data({
                'name': 'Battery Room Space',
                'slug': 'battery-room-space',
                'site': self.site,
                'location': self.location,
                'spatial_frame': None,
                'parent_space': self.physical_space,
                'space_kind': PhysicalSpaceKindChoices.KIND_ELECTRICAL_ROOM,
                'floor_label': 'L1',
                'z_min': '',
                'z_max': '',
                'boundary_geometry': '{}',
                'source_document': self.source_document.name,
                'source_ref': 'E-102',
                'confidence': SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created = PhysicalSpace.objects.get(slug='battery-room-space')

        response = self.client.post(
            reverse('plugins:netbox_power_plant:physicalspace_edit', kwargs={'pk': created.pk}),
            post_data({
                'name': created.name,
                'slug': created.slug,
                'site': self.site,
                'location': self.location,
                'spatial_frame': None,
                'parent_space': self.physical_space,
                'space_kind': PhysicalSpaceKindChoices.KIND_ELECTRICAL_ROOM,
                'floor_label': 'L2',
                'z_min': '',
                'z_max': '',
                'boundary_geometry': '{}',
                'source_document': self.source_document.name,
                'source_ref': 'E-102',
                'confidence': SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created.refresh_from_db()
        self.assertEqual(created.floor_label, 'L2')

    def test_physical_element_add_and_edit_views_accept_post(self):
        self.add_permissions(
            'netbox_power_plant.add_physicalelement',
            'netbox_power_plant.change_physicalelement',
        )
        response = self.client.post(
            reverse('plugins:netbox_power_plant:physicalelement_add'),
            post_data({
                'name': 'UPS 1 Footprint',
                'slug': 'ups-1-footprint',
                'element_type': self.element_type,
                'site': self.site,
                'location': self.location,
                'physical_space': self.physical_space,
                'label': 'UPS-1',
                'role': 'UPS footprint',
                'manufacturer': '',
                'model_name': '',
                'asset_tag': '',
                'install_state': TopologyStateChoices.STATE_PLANNED,
                'design_state': DesignStateChoices.STATE_PLANNED,
                'source_label': 'UPS-1',
                'confidence': SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created = PhysicalElement.objects.get(slug='ups-1-footprint')

        response = self.client.post(
            reverse('plugins:netbox_power_plant:physicalelement_edit', kwargs={'pk': created.pk}),
            post_data({
                'name': created.name,
                'slug': created.slug,
                'element_type': self.element_type,
                'site': self.site,
                'location': self.location,
                'physical_space': self.physical_space,
                'label': 'UPS-1',
                'role': 'UPS cabinet footprint',
                'manufacturer': '',
                'model_name': '',
                'asset_tag': '',
                'install_state': TopologyStateChoices.STATE_PLANNED,
                'design_state': DesignStateChoices.STATE_PLANNED,
                'source_label': 'UPS-1',
                'confidence': SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created.refresh_from_db()
        self.assertEqual(created.role, 'UPS cabinet footprint')

    def test_physical_object_binding_add_and_edit_views_accept_post(self):
        self.add_permissions(
            'netbox_power_plant.add_physicalobjectbinding',
            'netbox_power_plant.change_physicalobjectbinding',
        )
        response = self.client.post(
            reverse('plugins:netbox_power_plant:physicalobjectbinding_add'),
            post_data({
                'name': 'UPS Binding',
                'slug': 'ups-binding',
                'physical_element': self.physical_element,
                'spatial_placement': None,
                'assigned_object_type': self.assigned_object_type,
                'assigned_object_id': self.power_system.pk,
                'binding_role': PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
                'confidence': SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
                'is_primary': False,
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created = PhysicalObjectBinding.objects.get(slug='ups-binding')

        response = self.client.post(
            reverse('plugins:netbox_power_plant:physicalobjectbinding_edit', kwargs={'pk': created.pk}),
            post_data({
                'name': created.name,
                'slug': created.slug,
                'physical_element': self.physical_element,
                'spatial_placement': None,
                'assigned_object_type': self.assigned_object_type,
                'assigned_object_id': self.power_system.pk,
                'binding_role': PhysicalObjectBindingRoleChoices.ROLE_SOURCE_OF_TRUTH,
                'confidence': SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
                'is_primary': True,
                'metadata': '{}',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created.refresh_from_db()
        self.assertEqual(created.binding_role, PhysicalObjectBindingRoleChoices.ROLE_SOURCE_OF_TRUTH)
