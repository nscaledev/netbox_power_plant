from django.core.exceptions import ValidationError
from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import (
    InternalPowerBusAttachmentRoleChoices,
    NodeKindChoices,
    PhaseModeChoices,
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
)


class Phase1BModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.other_site = Site.objects.create(name='Other Site', slug='other-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.other_location = Location.objects.create(site=cls.other_site, name='Electrical Room B', slug='electrical-room-b')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.other_power_system = PowerSystem.objects.create(
            name='Secondary Hall Power',
            slug='secondary-hall-power',
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.power_domain = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        cls.rack = Rack.objects.create(
            name='Rack A1',
            site=cls.site,
            location=cls.location,
        )
        cls.other_site_rack = Rack.objects.create(
            name='Rack B1',
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.other_location_same_site = Location.objects.create(site=cls.site, name='Electrical Room C', slug='electrical-room-c')
        cls.other_location_rack = Rack.objects.create(
            name='Rack A2',
            site=cls.site,
            location=cls.other_location_same_site,
        )
        cls.manufacturer = Manufacturer.objects.create(name='Test Manufacturer', slug='test-manufacturer')
        cls.device_type = DeviceType.objects.create(model='Boundary Device', slug='boundary-device', manufacturer=cls.manufacturer)
        cls.device_role = DeviceRole.objects.create(name='Boundary Role', slug='boundary-role', color='ff0000')
        cls.device = Device.objects.create(
            name='Boundary Device A',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='PSU A')
        cls.other_location_device = Device.objects.create(
            name='Boundary Device B',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.other_location_same_site,
        )
        cls.other_location_power_port = PowerPort.objects.create(device=cls.other_location_device, name='PSU A')

    def test_node_rejects_parent_from_another_power_system(self):
        parent_node = ElectricalNode.objects.create(
            name='Secondary UPS',
            slug='secondary-ups',
            power_system=self.other_power_system,
            site=self.other_site,
            location=self.other_location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        node = ElectricalNode(
            name='Primary PDU',
            slug='primary-pdu',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_PDU,
            parent_node=parent_node,
        )

        with self.assertRaises(ValidationError):
            node.full_clean()

    def test_terminal_rejects_dc_supply_on_ac_node(self):
        node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_UPS,
            phase_mode=PhaseModeChoices.MODE_THREE_PHASE,
        )
        terminal = ElectricalTerminal(
            name='Battery Output',
            slug='battery-output',
            node=node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_DC,
        )

        with self.assertRaises(ValidationError):
            terminal.full_clean()

    def test_segment_rejects_terminals_outside_power_system(self):
        source_node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        foreign_node = ElectricalNode.objects.create(
            name='Foreign PDU',
            slug='foreign-pdu',
            power_system=self.other_power_system,
            site=self.other_site,
            location=self.other_location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        source_terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=source_node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        foreign_terminal = ElectricalTerminal.objects.create(
            name='Input A',
            slug='foreign-input-a',
            node=foreign_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        segment = ElectricalSegment(
            name='Cross System Feed',
            slug='cross-system-feed',
            power_system=self.power_system,
            from_terminal=source_terminal,
            to_terminal=foreign_terminal,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
        )

        with self.assertRaises(ValidationError):
            segment.full_clean()

    def test_segment_accepts_matching_terminals_with_domain(self):
        source_node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups-valid',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        destination_node = ElectricalNode.objects.create(
            name='Row PDU',
            slug='row-pdu-valid',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        source_terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a-valid',
            node=source_node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        destination_terminal = ElectricalTerminal.objects.create(
            name='Input A',
            slug='input-a-valid',
            node=destination_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        segment = ElectricalSegment(
            name='UPS to PDU Feed',
            slug='ups-to-pdu-feed',
            power_system=self.power_system,
            from_terminal=source_terminal,
            to_terminal=destination_terminal,
            power_domain=self.power_domain,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
        )

        segment.full_clean()

    def test_internal_power_bus_attachment_accepts_matching_load_port(self):
        bus = InternalPowerBus.objects.create(
            name='Rack A1 NVL72 Busbar',
            slug='rack-a1-nvl72-busbar',
            power_system=self.power_system,
            rack=self.rack,
        )
        rack_device = Device.objects.create(
            name='Rack A1 Load Device',
            device_type=self.device_type,
            role=self.device_role,
            site=self.site,
            location=self.location,
            rack=self.rack,
        )
        load_port = PowerPort.objects.create(device=rack_device, name='nvl72-busbar', type='nvl72-busbar')
        attachment = InternalPowerBusAttachment(
            name='Rack A1 Load Attachment',
            slug='rack-a1-load-attachment',
            internal_power_bus=bus,
            power_port=load_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )

        attachment.full_clean()

    def test_internal_power_bus_attachment_accepts_standard_power_port_type(self):
        bus = InternalPowerBus.objects.create(
            name='Rack A1 Standard Port Busbar',
            slug='rack-a1-standard-port-busbar',
            power_system=self.power_system,
            rack=self.rack,
        )
        rack_device = Device.objects.create(
            name='Rack A1 Standard Load Device',
            device_type=self.device_type,
            role=self.device_role,
            site=self.site,
            location=self.location,
            rack=self.rack,
        )
        load_port = PowerPort.objects.create(device=rack_device, name='PSU A', type='iec-60320-c14')
        attachment = InternalPowerBusAttachment(
            name='Rack A1 Standard Load Attachment',
            slug='rack-a1-standard-load-attachment',
            internal_power_bus=bus,
            power_port=load_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )

        attachment.full_clean()

    def test_internal_power_bus_attachment_rejects_power_port_outside_bus_rack(self):
        bus = InternalPowerBus.objects.create(
            name='Rack A1 Scope Busbar',
            slug='rack-a1-scope-busbar',
            power_system=self.power_system,
            rack=self.rack,
        )
        attachment = InternalPowerBusAttachment(
            name='Rack A1 Wrong Rack Attachment',
            slug='rack-a1-wrong-rack-attachment',
            internal_power_bus=bus,
            power_port=self.other_location_power_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )

        with self.assertRaises(ValidationError):
            attachment.full_clean()

    def test_power_handoff_point_requires_power_port_target(self):
        node = ElectricalNode.objects.create(
            name='Rack Boundary Node',
            slug='rack-boundary-node',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        terminal = ElectricalTerminal.objects.create(
            name='Rack Input',
            slug='rack-input',
            node=node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        point = PowerHandoffPoint(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=self.power_system,
            electrical_node=node,
            electrical_terminal=terminal,
        )

        with self.assertRaises(ValidationError):
            point.full_clean()

    def test_rack_delivery_point_rejects_terminal_node_mismatch(self):
        node_a = ElectricalNode.objects.create(
            name='Rack Boundary Node A',
            slug='rack-boundary-node-a',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        node_b = ElectricalNode.objects.create(
            name='Rack Boundary Node B',
            slug='rack-boundary-node-b',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        terminal = ElectricalTerminal.objects.create(
            name='Rack Input Mismatch',
            slug='rack-input-mismatch',
            node=node_a,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        point = PowerHandoffPoint(
            name='Rack Mismatch Delivery',
            slug='rack-mismatch-delivery',
            power_system=self.power_system,
            electrical_node=node_b,
            electrical_terminal=terminal,
            power_port=self.power_port,
        )

        with self.assertRaises(ValidationError):
            point.full_clean()

    def test_power_handoff_point_rejects_missing_power_port(self):
        node = ElectricalNode.objects.create(
            name='Rack Boundary Node Location',
            slug='rack-boundary-node-location',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        point = PowerHandoffPoint(
            name='Rack Wrong Location Delivery',
            slug='rack-wrong-location-delivery',
            power_system=self.power_system,
            electrical_node=node,
        )

        with self.assertRaises(ValidationError):
            point.full_clean()

    def test_rack_delivery_point_rejects_power_port_outside_power_system_location(self):
        node = ElectricalNode.objects.create(
            name='Rack Boundary Node Power Port Location',
            slug='rack-boundary-node-power-port-location',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        point = PowerHandoffPoint(
            name='Power Port Wrong Location Delivery',
            slug='power-port-wrong-location-delivery',
            power_system=self.power_system,
            electrical_node=node,
            power_port=self.other_location_power_port,
        )

        with self.assertRaises(ValidationError):
            point.full_clean()

    def test_power_handoff_point_accepts_matching_terminal_and_power_port(self):
        node = ElectricalNode.objects.create(
            name='Rack Boundary Node Valid',
            slug='rack-boundary-node-valid',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        terminal = ElectricalTerminal.objects.create(
            name='Rack Input Valid',
            slug='rack-input-valid',
            node=node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        point = PowerHandoffPoint(
            name='Rack Valid Delivery',
            slug='rack-valid-delivery',
            power_system=self.power_system,
            electrical_node=node,
            electrical_terminal=terminal,
            power_port=self.power_port,
            feed_label='A-feed',
        )

        point.full_clean()

    def test_rack_delivery_point_accepts_matching_power_port(self):
        node = ElectricalNode.objects.create(
            name='Rack Boundary Node Power Port Valid',
            slug='rack-boundary-node-power-port-valid',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        terminal = ElectricalTerminal.objects.create(
            name='Rack Input Power Port Valid',
            slug='rack-input-power-port-valid',
            node=node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        point = PowerHandoffPoint(
            name='Power Port Valid Delivery',
            slug='power-port-valid-delivery',
            power_system=self.power_system,
            electrical_node=node,
            electrical_terminal=terminal,
            power_port=self.power_port,
            feed_label='A-feed',
        )

        point.full_clean()
