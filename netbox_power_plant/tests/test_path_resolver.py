from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalSegment,
    ElectricalTerminal,
    PowerDomain,
    PowerHandoffPoint,
    PowerSystem,
)
from netbox_power_plant.services.paths import PowerPathResolver


class PowerPathResolverTestCase(TestCase):
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
        cls.domain_a = PowerDomain.objects.create(
            name="Domain A",
            slug="domain-a",
            power_system=cls.power_system,
            code="A",
        )
        cls.rack = Rack.objects.create(name="Rack A1", site=cls.site, location=cls.location)
        cls.manufacturer = Manufacturer.objects.create(name="Path Manufacturer", slug="path-manufacturer")
        cls.device_type = DeviceType.objects.create(
            model="Path Device", slug="path-device", manufacturer=cls.manufacturer
        )
        cls.device_role = DeviceRole.objects.create(name="Path Role", slug="path-role", color="ff0000")
        cls.device = Device.objects.create(
            name="Path Device A",
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name="PSU A")

    def _create_node(
        self, name, slug, *, node_kind=NodeKindChoices.KIND_PDU, topology_state=TopologyStateChoices.STATE_ACTIVE
    ):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=node_kind,
            topology_state=topology_state,
        )

    def _create_terminal(self, node, name, slug, direction):
        return ElectricalTerminal.objects.create(
            name=name,
            slug=slug,
            node=node,
            direction=direction,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )

    def _create_segment(
        self, source_terminal, destination_terminal, name, slug, *, path_state=TopologyStateChoices.STATE_ACTIVE
    ):
        return ElectricalSegment.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            from_terminal=source_terminal,
            to_terminal=destination_terminal,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
            path_state=path_state,
            power_domain=self.domain_a,
        )

    def _create_handoff(self, node, terminal, power_port=None, *, name="Rack Handoff", slug="rack-handoff"):
        return PowerHandoffPoint.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            electrical_node=node,
            electrical_terminal=terminal,
            power_port=power_port or self.power_port,
        )

    def test_resolves_direct_path_to_handoff(self):
        source_node = self._create_node("Primary UPS", "primary-ups", node_kind=NodeKindChoices.KIND_UPS)
        load_node = self._create_node(
            "Rack Boundary A", "rack-boundary-a", node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR
        )
        source_terminal = self._create_terminal(
            source_node, "Output A", "output-a", TerminalDirectionChoices.DIRECTION_SOURCE
        )
        load_terminal = self._create_terminal(load_node, "Input A", "input-a", TerminalDirectionChoices.DIRECTION_SINK)
        segment = self._create_segment(
            source_terminal,
            load_terminal,
            "UPS to Rack A",
            "ups-to-rack-a",
            path_state=TopologyStateChoices.STATE_PLANNED,
        )
        handoff = self._create_handoff(load_node, load_terminal)

        result = PowerPathResolver.resolve_by_handoff(source_node=source_node, handoff=handoff)

        self.assertTrue(result.path_found)
        self.assertEqual(result.source, source_node)
        self.assertEqual(result.handoff, handoff)
        self.assertEqual(result.power_port, self.power_port)
        self.assertEqual(result.nodes, (source_node, load_node))
        self.assertEqual(result.terminals, (source_terminal, load_terminal))
        self.assertEqual(result.segments, (segment,))
        self.assertEqual(result.domains, (self.domain_a,))
        self.assertEqual(result.finding, "path_found")

    def test_returns_unresolved_when_no_path_exists(self):
        source_node = self._create_node("Primary UPS", "primary-ups-no-path", node_kind=NodeKindChoices.KIND_UPS)
        load_node = self._create_node(
            "Rack Boundary A", "rack-boundary-a-no-path", node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR
        )
        load_terminal = self._create_terminal(
            load_node, "Input A", "input-a-no-path", TerminalDirectionChoices.DIRECTION_SINK
        )
        handoff = self._create_handoff(load_node, load_terminal, name="No Path Handoff", slug="no-path-handoff")

        result = PowerPathResolver.resolve_by_handoff(source_node=source_node, handoff=handoff)

        self.assertFalse(result.path_found)
        self.assertEqual(result.source, source_node)
        self.assertEqual(result.handoff, handoff)
        self.assertEqual(result.power_port, self.power_port)
        self.assertEqual(result.nodes, ())
        self.assertEqual(result.segments, ())
        self.assertEqual(result.finding, "path_not_found")

    def test_respects_terminal_specific_handoff(self):
        source_node = self._create_node(
            "Primary UPS", "primary-ups-terminal-specific", node_kind=NodeKindChoices.KIND_UPS
        )
        load_node = self._create_node(
            "Rack Boundary A",
            "rack-boundary-a-terminal-specific",
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        source_terminal = self._create_terminal(
            source_node, "Output A", "output-a-terminal-specific", TerminalDirectionChoices.DIRECTION_SOURCE
        )
        load_terminal_a = self._create_terminal(
            load_node, "Input A", "input-a-terminal-specific", TerminalDirectionChoices.DIRECTION_SINK
        )
        load_terminal_b = self._create_terminal(
            load_node, "Input B", "input-b-terminal-specific", TerminalDirectionChoices.DIRECTION_SINK
        )
        self._create_segment(source_terminal, load_terminal_a, "UPS to Rack A", "ups-to-rack-a-terminal-specific")
        handoff = self._create_handoff(load_node, load_terminal_b, name="Terminal B Handoff", slug="terminal-b-handoff")

        result = PowerPathResolver.resolve_by_handoff(source_terminal=source_terminal, handoff=handoff)

        self.assertFalse(result.path_found)
        self.assertEqual(result.source, source_terminal)
        self.assertEqual(result.finding, "path_not_found")

    def test_resolves_by_power_port_lookup(self):
        source_node = self._create_node("Primary UPS", "primary-ups-power-port", node_kind=NodeKindChoices.KIND_UPS)
        load_node = self._create_node(
            "Rack Boundary A", "rack-boundary-a-power-port", node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR
        )
        source_terminal = self._create_terminal(
            source_node, "Output A", "output-a-power-port", TerminalDirectionChoices.DIRECTION_SOURCE
        )
        load_terminal = self._create_terminal(
            load_node, "Input A", "input-a-power-port", TerminalDirectionChoices.DIRECTION_SINK
        )
        segment = self._create_segment(source_terminal, load_terminal, "UPS to Rack A", "ups-to-rack-a-power-port")
        handoff = self._create_handoff(load_node, load_terminal, name="Power Port Handoff", slug="power-port-handoff")

        result = PowerPathResolver.resolve_by_power_port(source_node=source_node, power_port=self.power_port)

        self.assertTrue(result.path_found)
        self.assertEqual(result.handoff, handoff)
        self.assertEqual(result.power_port, self.power_port)
        self.assertEqual(result.segments, (segment,))
