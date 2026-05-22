from decimal import Decimal

from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PhaseModeChoices,
    PowerFindingSeverityChoices,
    RedundancyTopologyChoices,
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
    RedundancyGroup,
)
from netbox_power_plant.services.operational_planning import (
    build_capacity_planning_summary,
    build_maintenance_impact_summary,
    build_operational_planning_summary,
)


class OperationalPlanningServiceTestCase(TestCase):
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

        cls.manufacturer = Manufacturer.objects.create(name="Planning Manufacturer", slug="planning-manufacturer")
        cls.device_type = DeviceType.objects.create(
            model="Planning Device",
            slug="planning-device",
            manufacturer=cls.manufacturer,
        )
        cls.device_role = DeviceRole.objects.create(name="Planning Role", slug="planning-role", color="ff0000")
        cls.rack = Rack.objects.create(name="Rack A1", site=cls.site, location=cls.location)
        cls.device = Device.objects.create(
            name="Rack A1 Server",
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name="PSU A", allocated_draw=600)
        cls.unmodeled_power_port = PowerPort.objects.create(device=cls.device, name="PSU B")

        cls.domain_a = cls._create_domain("Domain A", "domain-a", "A")
        cls.domain_b = cls._create_domain("Domain B", "domain-b", "B")
        cls.redundancy_group = RedundancyGroup.objects.create(
            name="Rack A/B Contract",
            slug="rack-a-b-contract",
            power_system=cls.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        cls.redundancy_group.power_domains.set([cls.domain_a, cls.domain_b])

        cls.source_a = cls._create_node(
            "UPS A",
            "ups-a",
            NodeKindChoices.KIND_UPS,
            usable_capacity_kw=Decimal("1.00"),
        )
        cls.source_b = cls._create_node("UPS B", "ups-b", NodeKindChoices.KIND_UPS)
        cls.rack_node = cls._create_node(
            "Rack A1 Boundary",
            "rack-a1-boundary",
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            parent_node=cls.source_a,
            usable_capacity_kw=Decimal("2.00"),
        )
        cls.sink_terminal = cls._create_terminal(
            cls.rack_node,
            "Rack Input A",
            "rack-input-a",
            TerminalDirectionChoices.DIRECTION_SINK,
        )

        cls.segment_a = cls._create_segment(
            cls._create_terminal(
                cls.source_a,
                "UPS A Output",
                "ups-a-output",
                TerminalDirectionChoices.DIRECTION_SOURCE,
            ),
            cls.sink_terminal,
            "UPS A to Rack A1",
            "ups-a-to-rack-a1",
            cls.domain_a,
        )
        cls.segment_b = cls._create_segment(
            cls._create_terminal(
                cls.source_b,
                "UPS B Output",
                "ups-b-output",
                TerminalDirectionChoices.DIRECTION_SOURCE,
            ),
            cls.sink_terminal,
            "UPS B to Rack A1",
            "ups-b-to-rack-a1",
            cls.domain_b,
        )
        cls.handoff = PowerHandoffPoint.objects.create(
            name="Rack A1 Handoff A",
            slug="rack-a1-handoff-a",
            power_system=cls.power_system,
            electrical_node=cls.rack_node,
            electrical_terminal=cls.sink_terminal,
            power_port=cls.power_port,
            expected_redundancy_group=cls.redundancy_group,
        )

    @classmethod
    def _create_domain(cls, name, slug, code):
        return PowerDomain.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            code=code,
        )

    @classmethod
    def _create_node(cls, name, slug, node_kind, *, parent_node=None, usable_capacity_kw=None):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            parent_node=parent_node,
            node_kind=node_kind,
            topology_state=TopologyStateChoices.STATE_ACTIVE,
            phase_mode=PhaseModeChoices.MODE_SINGLE_PHASE,
            usable_capacity_kw=usable_capacity_kw,
        )

    @classmethod
    def _create_terminal(cls, node, name, slug, direction):
        return ElectricalTerminal.objects.create(
            name=name,
            slug=slug,
            node=node,
            direction=direction,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )

    @classmethod
    def _create_segment(cls, source_terminal, destination_terminal, name, slug, power_domain):
        return ElectricalSegment.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            from_terminal=source_terminal,
            to_terminal=destination_terminal,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
            path_state=TopologyStateChoices.STATE_ACTIVE,
            power_domain=power_domain,
            voltage_nominal=Decimal("120"),
            ampacity_a=Decimal("10"),
        )

    def test_capacity_plan_projects_reserved_load_and_capacity_findings(self):
        summary = build_capacity_planning_summary(
            self.power_system,
            reserved_kw_by_power_port_id={
                self.power_port.pk: Decimal("0.500"),
                self.unmodeled_power_port.pk: Decimal("0.250"),
            },
        )

        source_rollup = next(rollup for rollup in summary.node_rollups if rollup.node == self.source_a)
        handoff_load = summary.handoff_loads[0]

        self.assertEqual(summary.capacity_summary.total_load_kw, Decimal("0.600"))
        self.assertEqual(summary.reserved_load_kw, Decimal("0.500"))
        self.assertEqual(summary.projected_load_kw, Decimal("1.100"))
        self.assertEqual(summary.projected_headroom_kw, Decimal("-0.100"))
        self.assertEqual(handoff_load.current_load_kw, Decimal("0.600"))
        self.assertEqual(handoff_load.reserved_load_kw, Decimal("0.500"))
        self.assertEqual(handoff_load.projected_load_kw, Decimal("1.100"))
        self.assertEqual(source_rollup.reserved_load_kw, Decimal("0.500"))
        self.assertEqual(source_rollup.projected_load_kw, Decimal("1.100"))
        self.assertEqual(source_rollup.projected_headroom_kw, Decimal("-0.100"))
        self.assertEqual(
            summary.unmatched_reserved_kw_by_power_port_id,
            {self.unmodeled_power_port.pk: Decimal("0.250")},
        )
        self.assertIn(
            "projected_capacity_exceeded",
            {finding["finding_type"] for finding in summary.projected_capacity_findings},
        )
        self.assertIn(
            "unmatched_reserved_power_port",
            {finding["finding_type"] for finding in summary.projected_capacity_findings},
        )
        self.assertEqual(
            summary.top_projected_capacity_findings[0]["severity"],
            PowerFindingSeverityChoices.SEVERITY_CRITICAL,
        )

    def test_maintenance_impact_reports_impacted_assets_and_redundancy_losses(self):
        summary = build_maintenance_impact_summary(
            self.power_system,
            power_domain_ids=(self.domain_a.pk,),
            electrical_segment_ids=(self.segment_b.pk,),
        )

        self.assertEqual(summary.impacted_handoffs, (self.handoff,))
        self.assertEqual(summary.impacted_devices, (self.device,))
        self.assertEqual(summary.impacted_racks, (self.rack,))
        self.assertEqual(summary.impacted_handoff_count, 1)
        self.assertEqual(summary.impacted_device_count, 1)
        self.assertEqual(summary.impacted_rack_count, 1)
        self.assertEqual(summary.redundancy_loss_count, 1)
        redundancy_loss = summary.redundancy_losses[0]
        self.assertEqual(redundancy_loss.handoff, self.handoff)
        self.assertEqual(redundancy_loss.device, self.device)
        self.assertEqual(redundancy_loss.rack, self.rack)
        self.assertEqual(redundancy_loss.redundancy_group, self.redundancy_group)
        self.assertEqual(
            set(redundancy_loss.finding_types),
            {"distinct_path_count_not_met", "domain_isolation_not_met"},
        )
        self.assertIn("scenario_handoff_unreachable", {finding["finding_type"] for finding in summary.findings})

    def test_operational_plan_combines_capacity_and_maintenance_inputs(self):
        plan = build_operational_planning_summary(
            self.power_system,
            reserved_kw_by_power_port_id={self.power_port.pk: Decimal("0.400")},
            power_domain_ids=(self.domain_a.pk,),
        )

        self.assertEqual(plan.power_system, self.power_system)
        self.assertEqual(plan.capacity_plan.reserved_load_kw, Decimal("0.400"))
        self.assertEqual(plan.capacity_plan.projected_load_kw, Decimal("1.000"))
        self.assertEqual(plan.maintenance_impact.impacted_handoffs, ())
        self.assertEqual(plan.maintenance_impact.redundancy_loss_count, 1)
