from django.urls import reverse

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site
from utilities.testing import APITestCase

from netbox_power_plant.choices import (
    InternalPowerBusAttachmentRoleChoices,
    NodeKindChoices,
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
    RackDeliveryPoint,
)


class Phase1BAPITestCase(APITestCase):
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
        cls.power_domain = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
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
        cls.delivery_point = RackDeliveryPoint.objects.create(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=cls.power_system,
            electrical_node=destination_node,
            electrical_terminal=destination_terminal,
            rack=cls.rack,
            feed_label='A-feed',
        )
        cls.power_port_delivery_point = RackDeliveryPoint.objects.create(
            name='Power Port Delivery',
            slug='power-port-delivery',
            power_system=cls.power_system,
            electrical_node=destination_node,
            electrical_terminal=destination_terminal,
            power_port=cls.power_port,
            feed_label='A-feed-port',
        )
    def test_api_root_includes_topology_endpoints(self):
        response = self.client.get(reverse('plugins-api:netbox_power_plant-api:api-root'), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('electrical-nodes', response.data)
        self.assertIn('electrical-terminals', response.data)
        self.assertIn('electrical-segments', response.data)
        self.assertIn('rack-delivery-points', response.data)
        self.assertIn('internal-power-buses', response.data)
        self.assertIn('internal-power-bus-attachments', response.data)

    def test_electrical_node_list_endpoint_returns_objects(self):
        self.add_permissions('netbox_power_plant.view_electricalnode')
        response = self.client.get(reverse('plugins-api:netbox_power_plant-api:electricalnode-list'), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(response.data['results'][0]['name'], self.node.name)

    def test_electrical_segment_detail_includes_terminals_and_domain(self):
        self.add_permissions('netbox_power_plant.view_electricalsegment')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:electricalsegment-detail', kwargs={'pk': self.segment.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.segment.name)
        self.assertEqual(response.data['power_domain']['id'], self.power_domain.pk)
        self.assertEqual(response.data['from_terminal']['name'], self.terminal.name)
        self.assertEqual(response.data['to_terminal']['name'], 'Input A')

    def test_rack_delivery_point_detail_includes_boundary_objects(self):
        self.add_permissions('netbox_power_plant.view_rackdeliverypoint')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:rackdeliverypoint-detail', kwargs={'pk': self.delivery_point.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.delivery_point.name)
        self.assertEqual(response.data['feed_label'], 'A-feed')
        self.assertEqual(response.data['rack']['name'], self.rack.name)
        self.assertEqual(response.data['electrical_terminal']['name'], 'Input A')

    def test_rack_delivery_point_detail_includes_power_port_target(self):
        self.add_permissions('netbox_power_plant.view_rackdeliverypoint')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:rackdeliverypoint-detail', kwargs={'pk': self.power_port_delivery_point.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertIsNone(response.data['rack'])
        self.assertIsNone(response.data['device'])
        self.assertEqual(response.data['power_port']['name'], self.power_port.name)

    def test_rack_delivery_point_list_filters_by_power_port(self):
        self.add_permissions('netbox_power_plant.view_rackdeliverypoint')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:rackdeliverypoint-list'),
            {'power_port_id': [self.power_port.pk]},
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.power_port_delivery_point.pk)

    def test_internal_power_bus_detail_includes_rack(self):
        self.add_permissions('netbox_power_plant.view_internalpowerbus')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:internalpowerbus-detail', kwargs={'pk': self.internal_power_bus.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.internal_power_bus.name)
        self.assertEqual(response.data['rack']['name'], self.rack.name)

    def test_internal_power_bus_attachment_detail_includes_native_power_port(self):
        self.add_permissions('netbox_power_plant.view_internalpowerbusattachment')
        response = self.client.get(
            reverse(
                'plugins-api:netbox_power_plant-api:internalpowerbusattachment-detail',
                kwargs={'pk': self.bus_attachment.pk},
            ),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.bus_attachment.name)
        self.assertEqual(response.data['power_port']['name'], self.power_port.name)
        self.assertEqual(response.data['power_port_device']['name'], self.device.name)
