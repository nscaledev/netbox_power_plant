from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import (
    InternalPowerBusAttachmentRoleChoices,
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
    InternalPowerBus,
    InternalPowerBusAttachment,
    PowerHandoffPoint,
    PowerSystem,
)
from netbox_power_plant.services.completeness import (
    build_completeness_findings,
    build_power_system_completeness_summary,
)
from netbox_power_plant.services.validation import run_topology_checks


class CompletenessServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Primary Site", slug="primary-site")
        cls.location = Location.objects.create(site=cls.site, name="Electrical Room A", slug="electrical-room-a")
        cls.other_location = Location.objects.create(site=cls.site, name="Electrical Room B", slug="electrical-room-b")
        cls.power_system = PowerSystem.objects.create(
            name="Primary Hall Power",
            slug="primary-hall-power",
            site=cls.site,
            location=cls.location,
        )
        cls.manufacturer = Manufacturer.objects.create(
            name="Completeness Manufacturer", slug="completeness-manufacturer"
        )
        cls.device_type = DeviceType.objects.create(
            model="Completeness Device",
            slug="completeness-device",
            manufacturer=cls.manufacturer,
        )
        cls.device_role = DeviceRole.objects.create(name="Completeness Role", slug="completeness-role", color="ff0000")

    def test_summary_counts_handoff_paths_and_unmodeled_power_ports(self):
        rack = self._rack("Rack A1")
        source_node = self._node("UPS A", "ups-a", NodeKindChoices.KIND_UPS)
        source_terminal = self._terminal(
            source_node,
            "Output A",
            "output-a",
            TerminalDirectionChoices.DIRECTION_SOURCE,
        )

        modeled_port = self._power_port("Rack A1 Server A", rack, "PSU A")
        modeled_node = self._node(
            "Rack A1 Boundary A",
            "rack-a1-boundary-a",
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        modeled_terminal = self._terminal(
            modeled_node,
            "Input A",
            "input-a",
            TerminalDirectionChoices.DIRECTION_SINK,
        )
        self._segment(source_terminal, modeled_terminal, "UPS to Rack A1 A", "ups-to-rack-a1-a")
        modeled_handoff = PowerHandoffPoint.objects.create(
            name="Rack A1 Handoff A",
            slug="rack-a1-handoff-a",
            power_system=self.power_system,
            electrical_node=modeled_node,
            electrical_terminal=modeled_terminal,
            power_port=modeled_port,
        )

        unmodeled_node = self._node(
            "Rack A1 Boundary B",
            "rack-a1-boundary-b",
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        unmodeled_terminal = self._terminal(
            unmodeled_node,
            "Input B",
            "input-b",
            TerminalDirectionChoices.DIRECTION_SINK,
        )
        self._segment(source_terminal, unmodeled_terminal, "UPS to Rack A1 B", "ups-to-rack-a1-b")

        no_path_port = self._power_port("Rack A1 Server B", rack, "PSU A")
        no_path_node = self._node(
            "Rack A1 Boundary C",
            "rack-a1-boundary-c",
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        no_path_terminal = self._terminal(
            no_path_node,
            "Input C",
            "input-c",
            TerminalDirectionChoices.DIRECTION_SINK,
        )
        no_path_handoff = PowerHandoffPoint.objects.create(
            name="Rack A1 Handoff C",
            slug="rack-a1-handoff-c",
            power_system=self.power_system,
            electrical_node=no_path_node,
            electrical_terminal=no_path_terminal,
            power_port=no_path_port,
        )
        unmodeled_port = self._power_port("Rack A1 Server C", rack, "PSU A")

        summary = build_power_system_completeness_summary(self.power_system)

        self.assertEqual(summary.total_rack_boundary_candidates, 3)
        self.assertEqual(summary.modeled_handoff_count, 2)
        self.assertEqual(summary.handoffs_with_active_graph_path_count, 1)
        self.assertEqual(summary.handoffs_without_active_path_count, 1)
        self.assertEqual(summary.target_power_ports_missing_or_stale_count, 0)
        self.assertEqual(summary.unmodeled_power_ports, (unmodeled_port,))
        self.assertEqual(summary.handoffs_with_active_path, (modeled_handoff,))
        self.assertEqual(summary.handoffs_without_active_path, (no_path_handoff,))

        finding_types = {finding["finding_type"] for finding in summary.findings}
        self.assertIn("unmodeled_rack_boundary_candidate", finding_types)
        self.assertIn("handoff_missing_active_path", finding_types)
        self.assertIn("unmodeled_power_port", finding_types)
        self.assertEqual(build_completeness_findings(self.power_system), summary.findings)

        topology_finding_types = {finding["finding_type"] for finding in run_topology_checks(self.power_system)["findings"]}
        self.assertIn("unmodeled_rack_boundary_candidate", topology_finding_types)

    def test_flags_stale_handoff_power_port_targets_outside_scope(self):
        rack = self._rack("Rack B1")
        other_rack = self._rack("Rack B2", location=self.other_location)
        source_node = self._node("UPS B", "ups-b", NodeKindChoices.KIND_UPS)
        source_terminal = self._terminal(
            source_node,
            "Output B",
            "output-b",
            TerminalDirectionChoices.DIRECTION_SOURCE,
        )
        boundary_node = self._node(
            "Rack B1 Boundary A",
            "rack-b1-boundary-a",
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        boundary_terminal = self._terminal(
            boundary_node,
            "Input A",
            "input-b1-a",
            TerminalDirectionChoices.DIRECTION_SINK,
        )
        self._segment(source_terminal, boundary_terminal, "UPS to Rack B1 A", "ups-to-rack-b1-a")
        stale_port = self._power_port("Rack B2 Server A", other_rack, "PSU A", location=self.other_location)
        handoff = PowerHandoffPoint.objects.create(
            name="Rack B1 Handoff A",
            slug="rack-b1-handoff-a",
            power_system=self.power_system,
            electrical_node=boundary_node,
            electrical_terminal=boundary_terminal,
            power_port=stale_port,
        )

        summary = build_power_system_completeness_summary(self.power_system)

        self.assertEqual(summary.handoffs_with_active_graph_path_count, 1)
        self.assertEqual(summary.target_power_ports_missing_or_stale_count, 1)
        self.assertEqual(summary.target_power_port_issues[0].owner, handoff)
        self.assertEqual(summary.target_power_port_issues[0].power_port, stale_port)
        self.assertEqual(summary.target_power_port_issues[0].finding_type, "power_port_target_stale")
        self.assertIn("power_port_target_stale", {finding["finding_type"] for finding in summary.findings})

    def test_internal_bus_attachment_coverage_tracks_covered_uncovered_and_stale_ports(self):
        bus_rack = self._rack("Rack C1")
        other_rack = self._rack("Rack C2")
        covered_port = self._power_port("Rack C1 Server A", bus_rack, "PSU A")
        uncovered_port = self._power_port("Rack C1 Server B", bus_rack, "PSU A")
        stale_port = self._power_port("Rack C2 Server A", other_rack, "PSU A")
        bus = InternalPowerBus.objects.create(
            name="Rack C1 Bus",
            slug="rack-c1-bus",
            power_system=self.power_system,
            rack=bus_rack,
        )
        InternalPowerBusAttachment.objects.create(
            name="Rack C1 Bus Load A",
            slug="rack-c1-bus-load-a",
            internal_power_bus=bus,
            power_port=covered_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )
        stale_attachment = InternalPowerBusAttachment.objects.create(
            name="Rack C1 Bus Stale Load",
            slug="rack-c1-bus-stale-load",
            internal_power_bus=bus,
            power_port=stale_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )

        summary = build_power_system_completeness_summary(self.power_system)
        coverage = summary.internal_bus_coverage

        self.assertEqual(coverage.bus_count, 1)
        self.assertEqual(coverage.attachment_count, 2)
        self.assertEqual(coverage.candidate_power_port_count, 2)
        self.assertEqual(coverage.covered_power_ports, (covered_port,))
        self.assertEqual(coverage.uncovered_power_ports, (uncovered_port,))
        self.assertEqual(coverage.stale_attachment_count, 1)
        self.assertEqual(coverage.stale_attachments[0].owner, stale_attachment)
        self.assertEqual(coverage.load_attachment_count, 2)

        finding_types = {finding["finding_type"] for finding in summary.findings}
        self.assertIn("internal_bus_power_port_unattached", finding_types)
        self.assertIn("internal_bus_attachment_power_port_stale", finding_types)

    def _rack(self, name, *, location=None):
        return Rack.objects.create(name=name, site=self.site, location=location or self.location)

    def _device(self, name, rack, *, location=None):
        return Device.objects.create(
            name=name,
            device_type=self.device_type,
            role=self.device_role,
            site=self.site,
            location=location or self.location,
            rack=rack,
        )

    def _power_port(self, device_name, rack, port_name, *, location=None):
        return PowerPort.objects.create(
            device=self._device(device_name, rack, location=location),
            name=port_name,
        )

    def _node(self, name, slug, node_kind):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=node_kind,
            topology_state=TopologyStateChoices.STATE_ACTIVE,
        )

    def _terminal(self, node, name, slug, direction):
        return ElectricalTerminal.objects.create(
            name=name,
            slug=slug,
            node=node,
            direction=direction,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )

    def _segment(self, source_terminal, destination_terminal, name, slug):
        return ElectricalSegment.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            from_terminal=source_terminal,
            to_terminal=destination_terminal,
            segment_kind=SegmentKindChoices.KIND_RACK_FEED,
            path_state=TopologyStateChoices.STATE_ACTIVE,
        )
