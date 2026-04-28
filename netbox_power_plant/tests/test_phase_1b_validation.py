from collections import defaultdict

from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    RedundancyTopologyChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import ElectricalNode, ElectricalSegment, ElectricalTerminal, PowerDomain, PowerSystem, RedundancyGroup
from netbox_power_plant.services.validation import run_topology_checks


class Phase1BValidationTestCase(TestCase):
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

    def _create_node(self, name, slug, *, node_kind=NodeKindChoices.KIND_PDU, topology_state=TopologyStateChoices.STATE_ACTIVE):
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

    def _create_segment(self, source_terminal, destination_terminal, name, slug):
        return ElectricalSegment.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            from_terminal=source_terminal,
            to_terminal=destination_terminal,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
            path_state=TopologyStateChoices.STATE_ACTIVE,
        )

    def _create_domain(self, name, slug, code):
        return PowerDomain.objects.create(
            name=name,
            slug=slug,
            power_system=self.power_system,
            code=code,
        )

    def test_validation_reports_missing_terminal_and_orphan_terminal(self):
        node_without_terminals = self._create_node('Empty Panel', 'empty-panel')
        node_with_orphan = self._create_node('Lonely UPS', 'lonely-ups', node_kind=NodeKindChoices.KIND_UPS)
        orphan_terminal = self._create_terminal(node_with_orphan, 'Lonely Output', 'lonely-output', TerminalDirectionChoices.DIRECTION_SOURCE)

        result = run_topology_checks(self.power_system)
        findings_by_type = defaultdict(list)
        for finding in result['findings']:
            findings_by_type[finding['finding_type']].append(finding)

        self.assertTrue(any(finding['object'].pk == node_without_terminals.pk for finding in findings_by_type['missing_terminal']))
        self.assertTrue(any(finding['object'].pk == orphan_terminal.pk for finding in findings_by_type['orphan_terminal']))

    def test_validation_reports_isolated_node_and_cycle(self):
        isolated_node = self._create_node('Isolated Panel', 'isolated-panel')
        self._create_terminal(isolated_node, 'Panel Output', 'panel-output', TerminalDirectionChoices.DIRECTION_SOURCE)

        node_a = self._create_node('Node A', 'node-a')
        node_b = self._create_node('Node B', 'node-b')
        output_a = self._create_terminal(node_a, 'Output A', 'output-a', TerminalDirectionChoices.DIRECTION_SOURCE)
        input_a = self._create_terminal(node_a, 'Input A', 'input-a', TerminalDirectionChoices.DIRECTION_SINK)
        output_b = self._create_terminal(node_b, 'Output B', 'output-b', TerminalDirectionChoices.DIRECTION_SOURCE)
        input_b = self._create_terminal(node_b, 'Input B', 'input-b', TerminalDirectionChoices.DIRECTION_SINK)
        self._create_segment(output_a, input_b, 'A to B', 'a-to-b')
        self._create_segment(output_b, input_a, 'B to A', 'b-to-a')

        result = run_topology_checks(self.power_system)
        findings_by_type = defaultdict(list)
        for finding in result['findings']:
            findings_by_type[finding['finding_type']].append(finding)

        self.assertTrue(any(finding['object'].pk == isolated_node.pk for finding in findings_by_type['isolated_node']))
        self.assertTrue(findings_by_type['cycle_detected'])
        self.assertSetEqual(set(findings_by_type['cycle_detected'][0]['node_ids']), {node_a.pk, node_b.pk})

    def test_validation_reports_redundancy_shortfall_for_rack_delivery(self):
        domain_a = self._create_domain('Domain A', 'domain-a', 'A')
        domain_b = self._create_domain('Domain B', 'domain-b', 'B')
        redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=self.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        redundancy_group.power_domains.set([domain_a, domain_b])

        source_node = self._create_node('Row PDU A', 'row-pdu-a')
        rack_node = self._create_node(
            'Rack Boundary A',
            'rack-boundary-a',
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
        )
        source_terminal = self._create_terminal(source_node, 'PDU Output A', 'pdu-output-a', TerminalDirectionChoices.DIRECTION_SOURCE)
        rack_terminal = self._create_terminal(rack_node, 'Rack Input A', 'rack-input-a', TerminalDirectionChoices.DIRECTION_SINK)
        segment = self._create_segment(source_terminal, rack_terminal, 'PDU to Rack A', 'pdu-to-rack-a')
        segment.power_domain = domain_a
        segment.save(update_fields=['power_domain'])

        result = run_topology_checks(self.power_system)
        findings_by_type = defaultdict(list)
        for finding in result['findings']:
            findings_by_type[finding['finding_type']].append(finding)

        self.assertTrue(any(finding['object'].pk == rack_terminal.pk for finding in findings_by_type['distinct_path_count_not_met']))
        self.assertTrue(any(finding['object'].pk == rack_terminal.pk for finding in findings_by_type['domain_isolation_not_met']))
        self.assertEqual(findings_by_type['distinct_path_count_not_met'][0]['redundancy_group'].pk, redundancy_group.pk)