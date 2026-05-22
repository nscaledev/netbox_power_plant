from django.urls import reverse
from utilities.testing import APITestCase, TestCase
from utilities.testing.utils import post_data

from dcim.models import Location, Rack, Site
from tenancy.models import Tenant

from netbox_power_plant.choices import CapacityReservationStatusChoices, NodeKindChoices, TopologyStateChoices
from netbox_power_plant.models import (
    BESSDetail,
    BuswaySectionDetail,
    CapacityReservation,
    ElectricalNode,
    GeneratorDetail,
    InstantiationRun,
    PowerArchitectureTemplate,
    PowerSystem,
    TemplateNode,
    TransformerDetail,
    UPSDetail,
)


class NeocloudOperatorWorkflowUITestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'dcim.view_rack',
        'tenancy.view_tenant',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_powerarchitecturetemplate',
        'netbox_power_plant.view_instantiationrun',
        'netbox_power_plant.view_instantiationartifact',
        'netbox_power_plant.view_capacityreservation',
        'netbox_power_plant.view_electricalnode',
        'netbox_power_plant.view_electricalsegment',
        'netbox_power_plant.view_powerdomain',
        'netbox_power_plant.view_upsdetail',
        'netbox_power_plant.view_generatordetail',
        'netbox_power_plant.view_transformerdetail',
        'netbox_power_plant.view_bessdetail',
        'netbox_power_plant.view_buswaysectiondetail',
    )

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Hall A', slug='hall-a')
        cls.power_system = PowerSystem.objects.create(
            name='AI Hall Power',
            slug='ai-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.tenant = Tenant.objects.create(name='GPU Tenant', slug='gpu-tenant')
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.ups_node = cls._node('UPS A', 'ups-a', NodeKindChoices.KIND_UPS)
        cls.unmodeled_ups_node = cls._node('UPS B', 'ups-b', NodeKindChoices.KIND_UPS)
        cls.generator_node = cls._node('Generator A', 'generator-a', NodeKindChoices.KIND_GENERATOR)
        cls.transformer_node = cls._node('Transformer A', 'transformer-a', NodeKindChoices.KIND_TRANSFORMER)
        cls.bess_node = cls._node('BESS A', 'bess-a', NodeKindChoices.KIND_BESS)
        cls.busway_node = cls._node('Busway A', 'busway-a', NodeKindChoices.KIND_BUSWAY_RUN)
        cls.reservation = CapacityReservation.objects.create(
            name='Rack A1 Reservation',
            slug='rack-a1-reservation',
            node=cls.ups_node,
            tenant=cls.tenant,
            rack=cls.rack,
            reserved_kw='2.50',
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        cls.ups_detail = UPSDetail.objects.create(node=cls.ups_node, ups_topology='double-conversion')
        cls.generator_detail = GeneratorDetail.objects.create(node=cls.generator_node, fuel_type='diesel')
        cls.transformer_detail = TransformerDetail.objects.create(node=cls.transformer_node, kva_rating='2500.00')
        cls.bess_detail = BESSDetail.objects.create(node=cls.bess_node, technology='Li-ion')
        cls.busway_detail = BuswaySectionDetail.objects.create(
            node=cls.busway_node,
            busway_system=cls.busway_node,
            section_index=1,
        )
        cls.template = PowerArchitectureTemplate.objects.create(
            name='Operator AI Pod Template',
            slug='operator-ai-pod-template',
            version='1',
        )
        TemplateNode.objects.create(
            name='Template UPS',
            slug='template-ups',
            template=cls.template,
            key='ups',
            node_kind=NodeKindChoices.KIND_UPS,
        )

    @classmethod
    def _node(cls, name, slug, node_kind):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=node_kind,
            topology_state=TopologyStateChoices.STATE_ACTIVE,
        )

    def test_operator_integration_pages_render(self):
        for url_name, kwargs, expected_text in (
            ('plugins:netbox_power_plant:neocloud_cockpit', None, 'Neocloud Cockpit'),
            ('plugins:netbox_power_plant:template_workflow', None, 'Template Workflow'),
            ('plugins:netbox_power_plant:capacityreservation_list', None, self.reservation.name),
            ('plugins:netbox_power_plant:capacityreservation', {'pk': self.reservation.pk}, 'Capacity Reservation Details'),
            ('plugins:netbox_power_plant:upsdetail_list', None, self.ups_node.name),
            ('plugins:netbox_power_plant:upsdetail', {'pk': self.ups_detail.pk}, 'UPS Detail'),
            ('plugins:netbox_power_plant:generatordetail', {'pk': self.generator_detail.pk}, 'Generator Detail'),
            ('plugins:netbox_power_plant:transformerdetail', {'pk': self.transformer_detail.pk}, 'Transformer Detail'),
            ('plugins:netbox_power_plant:bessdetail', {'pk': self.bess_detail.pk}, 'BESS Detail'),
            ('plugins:netbox_power_plant:buswaysectiondetail', {'pk': self.busway_detail.pk}, 'Busway Section Detail'),
            ('plugins:netbox_power_plant:powerarchitecturetemplate', {'pk': self.template.pk}, 'Architecture Template Details'),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs=kwargs))
                self.assertHttpStatus(response, 200)
                self.assertContains(response, expected_text)

    def test_template_workflow_creates_operator_review_dry_run(self):
        self.add_permissions('netbox_power_plant.add_instantiationrun')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:template_workflow'),
            post_data({
                'action': 'dry_run_template',
                'power_system': self.power_system,
                'template': self.template,
                'context_json': '{"row": "A"}',
            }),
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Run Result')
        self.assertEqual(InstantiationRun.objects.count(), 1)
        self.assertTrue(InstantiationRun.objects.get().dry_run)

    def test_plain_equipment_detail_add_and_edit_workflow(self):
        self.add_permissions('netbox_power_plant.add_upsdetail', 'netbox_power_plant.change_upsdetail')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:upsdetail_add'),
            post_data({
                'node': self.unmodeled_ups_node,
                'ups_topology': 'line-interactive',
                'battery_autonomy_minutes': '',
                'module_count': '',
                'module_rating_kw': '',
                'parallel_group_id': '',
                'maintenance_bypass_present': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        created = UPSDetail.objects.get(node=self.unmodeled_ups_node)

        response = self.client.post(
            reverse('plugins:netbox_power_plant:upsdetail_edit', kwargs={'pk': created.pk}),
            post_data({
                'node': self.unmodeled_ups_node,
                'ups_topology': 'double-conversion',
                'battery_autonomy_minutes': '',
                'module_count': '',
                'module_rating_kw': '',
                'parallel_group_id': '',
                'maintenance_bypass_present': 'on',
            }),
        )

        self.assertHttpStatus(response, 302)
        created.refresh_from_db()
        self.assertEqual(created.ups_topology, 'double-conversion')
        self.assertTrue(created.maintenance_bypass_present)


class NeocloudOperatorWorkflowAPITestCase(APITestCase):
    view_namespace = 'plugins-api:netbox_power_plant'

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Hall A', slug='hall-a')
        cls.power_system = PowerSystem.objects.create(
            name='AI Hall Power',
            slug='ai-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.tenant = Tenant.objects.create(name='GPU Tenant', slug='gpu-tenant')
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.ups_node = ElectricalNode.objects.create(
            name='UPS A',
            slug='ups-a-api',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.reservation = CapacityReservation.objects.create(
            name='Rack A1 API Reservation',
            slug='rack-a1-api-reservation',
            node=cls.ups_node,
            tenant=cls.tenant,
            rack=cls.rack,
            reserved_kw='2.50',
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        cls.ups_detail = UPSDetail.objects.create(node=cls.ups_node, ups_topology='double-conversion')

    def test_capacity_reservation_api_endpoint_is_registered(self):
        self.add_permissions('netbox_power_plant.view_capacityreservation')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:capacityreservation-detail', kwargs={'pk': self.reservation.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.reservation.name)
        self.assertEqual(response.data['node']['id'], self.ups_node.pk)

    def test_equipment_detail_api_endpoint_is_registered(self):
        self.add_permissions('netbox_power_plant.view_upsdetail')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:upsdetail-detail', kwargs={'pk': self.ups_detail.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['node']['id'], self.ups_node.pk)
        self.assertEqual(response.data['ups_topology'], 'double-conversion')
