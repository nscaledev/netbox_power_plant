from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PowerFindingStatusChoices,
    PowerValidationRunKindChoices,
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
    PowerFinding,
    PowerHandoffPoint,
    PowerSystem,
    RedundancyGroup,
)
from netbox_power_plant.services.findings import run_and_persist_scenario_findings
from netbox_power_plant.services.impact import domain_lost, node_offline, segment_cut
from netbox_power_plant.services.scenarios import PowerOutageScenario, simulate_power_scenario


class ScenarioServiceTestCase(TestCase):
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
        cls.manufacturer = Manufacturer.objects.create(name='Test Manufacturer', slug='test-manufacturer')
        cls.device_type = DeviceType.objects.create(
            model='Scenario Device',
            slug='scenario-device',
            manufacturer=cls.manufacturer,
        )
        cls.device_role = DeviceRole.objects.create(name='Scenario Role', slug='scenario-role', color='ff0000')
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.device = Device.objects.create(
            name='Rack A1 Server',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='PSU A', allocated_draw=800)

        cls.domain_a = cls._create_domain('Domain A', 'domain-a', 'A')
        cls.domain_b = cls._create_domain('Domain B', 'domain-b', 'B')
        cls.redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=cls.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        cls.redundancy_group.power_domains.set([cls.domain_a, cls.domain_b])

        cls.source_a = cls._create_node('UPS A', 'ups-a', NodeKindChoices.KIND_UPS)
        cls.source_b = cls._create_node('UPS B', 'ups-b', NodeKindChoices.KIND_UPS)
        cls.unrelated_source = cls._create_node('Maintenance UPS', 'maintenance-ups', NodeKindChoices.KIND_UPS)
        cls.rack_node = cls._create_node(
            'Rack A1 Boundary',
            'rack-a1-boundary',
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        cls.sink_terminal = cls._create_terminal(
            cls.rack_node,
            'Rack Input A',
            'rack-input-a',
            TerminalDirectionChoices.DIRECTION_SINK,
        )

        cls.segment_a = cls._create_segment(
            cls._create_terminal(
                cls.source_a,
                'UPS A Output',
                'ups-a-output',
                TerminalDirectionChoices.DIRECTION_SOURCE,
            ),
            cls.sink_terminal,
            'UPS A to Rack A1',
            'ups-a-to-rack-a1',
            cls.domain_a,
        )
        cls.segment_b = cls._create_segment(
            cls._create_terminal(
                cls.source_b,
                'UPS B Output',
                'ups-b-output',
                TerminalDirectionChoices.DIRECTION_SOURCE,
            ),
            cls.sink_terminal,
            'UPS B to Rack A1',
            'ups-b-to-rack-a1',
            cls.domain_b,
        )
        cls.non_required_segment = cls._create_segment(
            cls._create_terminal(
                cls.unrelated_source,
                'Maintenance Output',
                'maintenance-output',
                TerminalDirectionChoices.DIRECTION_SOURCE,
            ),
            cls._create_terminal(
                cls._create_node('Maintenance Load', 'maintenance-load', NodeKindChoices.KIND_PDU),
                'Maintenance Input',
                'maintenance-input',
                TerminalDirectionChoices.DIRECTION_SINK,
            ),
            'Maintenance Segment',
            'maintenance-segment',
            None,
        )
        cls.handoff = PowerHandoffPoint.objects.create(
            name='Rack A1 Handoff A',
            slug='rack-a1-handoff-a',
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
    def _create_node(cls, name, slug, node_kind):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=node_kind,
            topology_state=TopologyStateChoices.STATE_ACTIVE,
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
        )

    def test_redundant_handoff_stays_compliant_when_non_required_segment_is_out(self):
        result = simulate_power_scenario(
            self.power_system,
            PowerOutageScenario(electrical_segments=(self.non_required_segment,)),
            include_capacity=False,
        )

        self.assertEqual(result.impacted_handoff_count, 0)
        self.assertEqual(result.redundancy_violation_count, 0)
        self.assertEqual(
            {domain.pk for domain in result.remaining_domains_by_handoff[self.handoff.pk]},
            {self.domain_a.pk, self.domain_b.pk},
        )

    def test_disabling_one_domain_reports_redundancy_loss(self):
        result = simulate_power_scenario(
            self.power_system,
            PowerOutageScenario(power_domains=(self.domain_a,)),
            include_capacity=False,
        )

        self.assertEqual(result.impacted_handoffs, ())
        self.assertEqual(result.redundancy_violation_count, 1)
        violation = result.redundancy_violations[0]
        self.assertEqual(violation.handoff, self.handoff)
        self.assertEqual(set(violation.finding_types), {'distinct_path_count_not_met', 'domain_isolation_not_met'})
        self.assertEqual({domain.pk for domain in violation.matched_domains}, {self.domain_b.pk})
        self.assertEqual(
            {finding['finding_type'] for finding in result.findings},
            {'scenario_distinct_path_count_not_met', 'scenario_domain_isolation_not_met'},
        )

    def test_disabling_feed_segments_reports_unreachable_handoff(self):
        result = simulate_power_scenario(
            self.power_system,
            PowerOutageScenario(electrical_segments=(self.segment_a, self.segment_b)),
            include_capacity=False,
        )

        self.assertEqual(result.impacted_handoffs, (self.handoff,))
        self.assertEqual(result.impacted_devices, (self.device,))
        self.assertEqual(result.impacted_racks, (self.rack,))
        self.assertIn('unreachable', result.handoff_impacts[0].impact_reasons)
        self.assertIn('scenario_handoff_unreachable', {finding['finding_type'] for finding in result.findings})

    def test_scenario_findings_are_persisted(self):
        result = run_and_persist_scenario_findings(
            self.power_system,
            PowerOutageScenario(power_domains=(self.domain_a,)),
            name='Domain A Maintenance',
        )

        self.assertEqual(result.run.run_kind, PowerValidationRunKindChoices.KIND_SCENARIO)
        self.assertEqual(result.open_count, 2)
        self.assertEqual(
            set(PowerFinding.objects.filter(run=result.run).values_list('finding_type', flat=True)),
            {'scenario_distinct_path_count_not_met', 'scenario_domain_isolation_not_met'},
        )
        self.assertTrue(
            PowerFinding.objects.filter(
                run=result.run,
                finding_type='scenario_distinct_path_count_not_met',
                status=PowerFindingStatusChoices.STATUS_OPEN,
                assigned_object_id=self.handoff.pk,
            ).exists()
        )

    def test_impact_service_groups_degraded_rack_for_single_domain_loss(self):
        report = domain_lost(self.power_system, self.domain_a)

        self.assertEqual(report['summary']['degraded_rack_count'], 1)
        self.assertEqual(report['summary']['critical_rack_count'], 0)
        self.assertEqual(report['racks'][0]['rack']['id'], self.rack.pk)
        self.assertEqual(report['racks'][0]['severity'], 'degraded')
        self.assertEqual(report['racks'][0]['handoffs'][0]['handoff']['id'], self.handoff.pk)
        self.assertIn('distinct_path_count_not_met', report['racks'][0]['handoffs'][0]['impact_reasons'])

    def test_impact_service_groups_critical_rack_when_handoff_node_is_offline(self):
        report = segment_cut(self.power_system, self.segment_a)

        self.assertEqual(report['summary']['degraded_rack_count'], 1)
        self.assertEqual(report['summary']['critical_rack_count'], 0)

        critical_report = node_offline(self.power_system, self.rack_node)
        self.assertEqual(critical_report['summary']['critical_rack_count'], 1)
        self.assertEqual(critical_report['racks'][0]['severity'], 'critical')
        self.assertIn('node_out_of_service', critical_report['racks'][0]['handoffs'][0]['impact_reasons'])
