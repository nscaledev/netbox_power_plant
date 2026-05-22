from django.urls import reverse

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site
from utilities.testing import TestCase
from utilities.testing.utils import post_data

from netbox_power_plant.choices import (
    InternalPowerBusAttachmentRoleChoices,
    NodeKindChoices,
    RedundancyTopologyChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalSegment,
    ElectricalTerminal,
    InternalPowerBus,
    InternalPowerBusAttachment,
    PowerDomain,
    PowerSystem,
    PowerHandoffPoint,
    RedundancyGroup,
)
from netbox_power_plant.template_extensions import PowerPortPowerPlantContext


class Phase1BViewTestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_powerdomain',
        'netbox_power_plant.view_redundancygroup',
        'netbox_power_plant.view_electricalnode',
        'netbox_power_plant.view_electricalterminal',
        'netbox_power_plant.view_electricalsegment',
        'netbox_power_plant.view_internalpowerbus',
        'netbox_power_plant.view_internalpowerbusattachment',
        'netbox_power_plant.view_powerhandoffpoint',
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
        cls.power_domain = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        cls.power_domain_b = PowerDomain.objects.create(
            name='Domain B',
            slug='domain-b',
            power_system=cls.power_system,
            code='B',
        )
        cls.redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=cls.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        cls.redundancy_group.power_domains.set([cls.power_domain, cls.power_domain_b])
        cls.node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=cls.node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        destination_node = ElectricalNode.objects.create(
            name='Row PDU',
            slug='row-pdu',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        destination_terminal = ElectricalTerminal.objects.create(
            name='Input A',
            slug='input-a',
            node=destination_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        cls.segment = ElectricalSegment.objects.create(
            name='UPS to PDU Feed',
            slug='ups-to-pdu-feed',
            power_system=cls.power_system,
            power_domain=cls.power_domain,
            from_terminal=cls.terminal,
            to_terminal=destination_terminal,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
        )
        cls.rack_node = ElectricalNode.objects.create(
            name='Rack Boundary A',
            slug='rack-boundary-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            topology_state='active',
        )
        cls.rack_terminal = ElectricalTerminal.objects.create(
            name='Rack Input A',
            slug='rack-input-a',
            node=cls.rack_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        cls.rack_segment = ElectricalSegment.objects.create(
            name='PDU to Rack Feed',
            slug='pdu-to-rack-feed',
            power_system=cls.power_system,
            power_domain=cls.power_domain,
            from_terminal=destination_terminal,
            to_terminal=cls.rack_terminal,
            segment_kind=SegmentKindChoices.KIND_RACK_FEED,
            path_state='active',
        )
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.manufacturer = Manufacturer.objects.create(name='Test Manufacturer', slug='test-manufacturer')
        cls.device_type = DeviceType.objects.create(model='Boundary Device', slug='boundary-device', manufacturer=cls.manufacturer)
        cls.device_role = DeviceRole.objects.create(name='Boundary Role', slug='boundary-role', color='ff0000')
        cls.device = Device.objects.create(
            name='Boundary Device A',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='PSU A')
        cls.power_port_b = PowerPort.objects.create(device=cls.device, name='PSU B')
        cls.internal_power_bus = InternalPowerBus.objects.create(
            name='Rack A1 Busbar',
            slug='rack-a1-busbar',
            power_system=cls.power_system,
            rack=cls.rack,
        )
        cls.bus_attachment = InternalPowerBusAttachment.objects.create(
            name='Rack A1 PSU A Attachment',
            slug='rack-a1-psu-a-attachment',
            internal_power_bus=cls.internal_power_bus,
            power_port=cls.power_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )
        cls.delivery_point = PowerHandoffPoint.objects.create(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=cls.power_system,
            electrical_node=cls.rack_node,
            electrical_terminal=cls.rack_terminal,
            power_port=cls.power_port,
            expected_redundancy_group=cls.redundancy_group,
            feed_label='A-feed',
            delivery_role='primary',
        )

    def test_topology_detail_pages_render(self):
        for url_name, expected_text in (
            ('plugins:netbox_power_plant:electricalnode', self.node.name),
            ('plugins:netbox_power_plant:electricalterminal', self.terminal.name),
            ('plugins:netbox_power_plant:electricalsegment', self.segment.name),
            ('plugins:netbox_power_plant:internalpowerbus', self.internal_power_bus.name),
            ('plugins:netbox_power_plant:internalpowerbusattachment', self.bus_attachment.name),
            ('plugins:netbox_power_plant:powerhandoffpoint', self.delivery_point.name),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs={'pk': self._resolve_pk(url_name)}))
                self.assertHttpStatus(response, 200)
                self.assertContains(response, expected_text)

    def test_electrical_node_add_view_accepts_minimal_post(self):
        self.add_permissions('netbox_power_plant.add_electricalnode')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:electricalnode_add'),
            post_data({
                'name': 'Static Transfer Switch',
                'slug': 'static-transfer-switch',
                'power_system': self.power_system,
                'site': self.site,
                'location': self.location,
                'node_kind': 'sts',
                'install_state': 'planned',
                'topology_state': 'planned',
                'phase_mode': '3ph',
                'description': '',
                'comments': '',
            }),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ElectricalNode.objects.filter(slug='static-transfer-switch').exists())

    def test_rack_delivery_point_add_view_accepts_minimal_post(self):
        self.add_permissions('netbox_power_plant.add_powerhandoffpoint', 'dcim.view_powerport')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:powerhandoffpoint_add'),
            post_data({
                'name': 'Rack A Delivery Secondary',
                'slug': 'rack-a-delivery-secondary',
                'power_system': self.power_system,
                'electrical_node': self.rack_node,
                'electrical_terminal': self.rack_terminal,
                'power_port': self.power_port_b,
                'expected_redundancy_group': self.redundancy_group,
                'delivery_role': 'redundant',
                'feed_label': 'B-feed',
                'design_state': 'planned',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(PowerHandoffPoint.objects.filter(slug='rack-a-delivery-secondary').exists())

    def test_rack_delivery_point_add_view_accepts_power_port_target(self):
        self.add_permissions('netbox_power_plant.add_powerhandoffpoint', 'dcim.view_powerport')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:powerhandoffpoint_add'),
            post_data({
                'name': 'Power Port Delivery',
                'slug': 'power-port-delivery',
                'power_system': self.power_system,
                'electrical_node': self.rack_node,
                'electrical_terminal': self.rack_terminal,
                'rack': None,
                'device': None,
                'power_port': self.power_port,
                'expected_redundancy_group': self.redundancy_group,
                'delivery_role': 'redundant',
                'feed_label': 'A-feed-port',
                'design_state': 'planned',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(PowerHandoffPoint.objects.filter(slug='power-port-delivery', power_port=self.power_port).exists())

    def test_internal_power_bus_attachment_add_view_accepts_minimal_post(self):
        self.add_permissions('netbox_power_plant.add_internalpowerbusattachment', 'dcim.view_powerport')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:internalpowerbusattachment_add'),
            post_data({
                'name': 'Rack A1 PSU A Source Attachment',
                'slug': 'rack-a1-psu-a-source-attachment',
                'internal_power_bus': self.internal_power_bus,
                'power_port': self.power_port_b,
                'attachment_role': 'source',
                'position_index': 2,
                'design_state': 'planned',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(InternalPowerBusAttachment.objects.filter(slug='rack-a1-psu-a-source-attachment').exists())

    def test_power_port_template_extension_renders_power_plant_context(self):
        delivery_point = PowerHandoffPoint.objects.create(
            name='Power Port Extension Delivery',
            slug='power-port-extension-delivery',
            power_system=self.power_system,
            electrical_node=self.rack_node,
            electrical_terminal=self.rack_terminal,
            power_port=self.power_port,
            feed_label='A-feed-port',
        )
        content = PowerPortPowerPlantContext({'object': self.power_port}).right_page()

        self.assertIn('Power Plant', content)
        self.assertIn(delivery_point.name, content)
        self.assertIn(self.bus_attachment.name, content)

    def test_rack_delivery_summary_page_renders_derived_status(self):
        response = self.client.get(
            reverse('plugins:netbox_power_plant:powersystem_rack_delivery', kwargs={'pk': self.power_system.pk})
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Power Handoff Summary')
        self.assertContains(response, self.rack_node.name)
        self.assertContains(response, self.rack_terminal.name)
        self.assertContains(response, self.redundancy_group.name)
        self.assertContains(response, self.delivery_point.feed_label)
        self.assertContains(response, 'Modeled')
        self.assertContains(response, 'Needs attention')

    def _resolve_pk(self, url_name):
        if url_name.endswith('electricalnode'):
            return self.node.pk
        if url_name.endswith('electricalterminal'):
            return self.terminal.pk
        if url_name.endswith('internalpowerbus'):
            return self.internal_power_bus.pk
        if url_name.endswith('internalpowerbusattachment'):
            return self.bus_attachment.pk
        if url_name.endswith('powerhandoffpoint'):
            return self.delivery_point.pk
        return self.segment.pk
