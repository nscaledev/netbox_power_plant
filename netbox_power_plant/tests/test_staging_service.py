from decimal import Decimal

from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Site

from netbox_power_plant.choices import NodeKindChoices, TerminalDirectionChoices
from netbox_power_plant.models import ElectricalNode, ElectricalTerminal, PowerDomain, PowerHandoffPoint, PowerSystem
from netbox_power_plant.services.staging import (
    StagedCircuitEndpoint,
    bind_handoff_to_power_port,
    stage_circuit_endpoint,
)


class MadisonStagingServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='MAD-1', slug='mad-1')
        cls.location = Location.objects.create(site=cls.site, name='Data Hall 1', slug='data-hall-1')
        cls.power_system = PowerSystem.objects.create(
            name='MAD-1 Power Plant',
            slug='mad-1-power-plant',
            site=cls.site,
            location=cls.location,
        )
        cls.power_domain = PowerDomain.objects.create(
            name='MAD-1 A Feed',
            slug='mad-1-a-feed',
            power_system=cls.power_system,
            code='A',
        )
        cls.manufacturer = Manufacturer.objects.create(name='Test Manufacturer', slug='test-manufacturer')
        cls.device_type = DeviceType.objects.create(
            manufacturer=cls.manufacturer,
            model='Rack PDU',
            slug='rack-pdu',
        )
        cls.device_role = DeviceRole.objects.create(name='Rack PDU', slug='rack-pdu', color='ff0000')
        cls.device = Device.objects.create(
            name='MAD1-RACK-A1-PDU-A',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='Input A')

    def test_stage_circuit_endpoint_creates_unresolved_node_and_terminal_only(self):
        endpoint = StagedCircuitEndpoint(
            source_key='MAD1-RPP-01-L21-A1-A',
            source_name='Electrical schedule row 21',
            cabinet_label='A1',
            feed_label='A-feed',
            domain_code='A',
            voltage_nominal='415',
            amperage_rating='60',
            power_kw='34.6',
        )

        result = stage_circuit_endpoint(self.power_system, endpoint)

        self.assertTrue(result.node_created)
        self.assertTrue(result.terminal_created)
        self.assertEqual(result.power_domain, self.power_domain)
        self.assertEqual(result.node.node_kind, NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR)
        self.assertEqual(result.node.power_system, self.power_system)
        self.assertEqual(result.node.site, self.site)
        self.assertEqual(result.node.location, self.location)
        self.assertEqual(result.node.usable_capacity_kw, Decimal('34.6'))
        self.assertEqual(result.terminal.node, result.node)
        self.assertEqual(result.terminal.direction, TerminalDirectionChoices.DIRECTION_SINK)
        self.assertEqual(result.terminal.voltage_nominal, Decimal('415'))
        self.assertEqual(result.terminal.amperage_rating, Decimal('60'))
        self.assertEqual(PowerHandoffPoint.objects.count(), 0)

    def test_stage_circuit_endpoint_is_idempotent_by_source_key(self):
        endpoint = {
            'source_key': 'MAD1-RPP-01-L22-A1-B',
            'cabinet_label': 'A1',
            'feed_label': 'B-feed',
            'voltage_nominal': '415',
        }

        first = stage_circuit_endpoint(self.power_system, endpoint)
        second = stage_circuit_endpoint(self.power_system, {**endpoint, 'voltage_nominal': '400'})

        self.assertEqual(first.node, second.node)
        self.assertEqual(first.terminal, second.terminal)
        self.assertFalse(second.node_created)
        self.assertFalse(second.terminal_created)
        self.assertEqual(ElectricalNode.objects.count(), 1)
        self.assertEqual(ElectricalTerminal.objects.count(), 1)
        second.terminal.refresh_from_db()
        self.assertEqual(second.terminal.voltage_nominal, Decimal('400'))
        self.assertEqual(PowerHandoffPoint.objects.count(), 0)

    def test_bind_handoff_to_power_port_creates_power_port_handoff(self):
        endpoint = StagedCircuitEndpoint(
            source_key='MAD1-RPP-01-L23-A2-A',
            cabinet_label='A2',
            feed_label='A-feed',
            domain_code='A',
        )

        handoff = bind_handoff_to_power_port(self.power_system, endpoint, self.power_port)

        self.assertEqual(PowerHandoffPoint.objects.count(), 1)
        self.assertEqual(handoff.power_port, self.power_port)
        self.assertEqual(handoff.power_system, self.power_system)
        self.assertEqual(handoff.electrical_terminal.node, handoff.electrical_node)
        self.assertEqual(handoff.feed_label, 'A-feed')

    def test_bind_handoff_to_power_port_is_idempotent(self):
        endpoint = StagedCircuitEndpoint(
            source_key='MAD1-RPP-01-L24-A2-B',
            cabinet_label='A2',
            feed_label='B-feed',
        )

        first = bind_handoff_to_power_port(self.power_system, endpoint, self.power_port)
        second = bind_handoff_to_power_port(self.power_system, endpoint, self.power_port, delivery_role='redundant')

        self.assertEqual(first, second)
        self.assertEqual(PowerHandoffPoint.objects.count(), 1)
        second.refresh_from_db()
        self.assertEqual(second.delivery_role, 'redundant')

    def test_bind_handoff_requires_real_power_port(self):
        endpoint = StagedCircuitEndpoint(
            source_key='MAD1-RPP-01-L25-A3-A',
            cabinet_label='A3',
            feed_label='A-feed',
        )

        with self.assertRaises(TypeError):
            bind_handoff_to_power_port(self.power_system, endpoint, self.device)
