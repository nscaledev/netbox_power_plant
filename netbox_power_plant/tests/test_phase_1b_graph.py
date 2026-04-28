from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import NodeKindChoices, SegmentKindChoices, SupplyTypeChoices, TerminalDirectionChoices, TopologyStateChoices
from netbox_power_plant.models import ElectricalNode, ElectricalSegment, ElectricalTerminal, PowerSystem
from netbox_power_plant.services.graph import PowerGraphBuilder


class Phase1BGraphTestCase(TestCase):
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

    def test_snapshot_traces_upstream_and_downstream_nodes(self):
        source_node = self._create_node('Primary UPS', 'primary-ups', node_kind=NodeKindChoices.KIND_UPS)
        middle_node = self._create_node('Static Transfer Switch', 'static-transfer-switch', node_kind=NodeKindChoices.KIND_STS)
        destination_node = self._create_node('Row PDU', 'row-pdu')
        source_terminal = self._create_terminal(source_node, 'UPS Output', 'ups-output', TerminalDirectionChoices.DIRECTION_SOURCE)
        middle_input = self._create_terminal(middle_node, 'STS Input', 'sts-input', TerminalDirectionChoices.DIRECTION_SINK)
        middle_output = self._create_terminal(middle_node, 'STS Output', 'sts-output', TerminalDirectionChoices.DIRECTION_SOURCE)
        destination_terminal = self._create_terminal(destination_node, 'PDU Input', 'pdu-input', TerminalDirectionChoices.DIRECTION_SINK)
        self._create_segment(source_terminal, middle_input, 'UPS to STS', 'ups-to-sts')
        self._create_segment(middle_output, destination_terminal, 'STS to PDU', 'sts-to-pdu')

        snapshot = PowerGraphBuilder.build_for_power_system(self.power_system, node_states=(TopologyStateChoices.STATE_ACTIVE,), path_states=(TopologyStateChoices.STATE_ACTIVE,))

        self.assertSetEqual(snapshot.downstream_node_ids(source_node.pk), {middle_node.pk, destination_node.pk})
        self.assertSetEqual(snapshot.upstream_node_ids(destination_node.pk), {source_node.pk, middle_node.pk})

    def test_snapshot_detects_directed_cycle(self):
        node_a = self._create_node('Node A', 'node-a')
        node_b = self._create_node('Node B', 'node-b')
        output_a = self._create_terminal(node_a, 'Output A', 'output-a', TerminalDirectionChoices.DIRECTION_SOURCE)
        input_a = self._create_terminal(node_a, 'Input A', 'input-a', TerminalDirectionChoices.DIRECTION_SINK)
        output_b = self._create_terminal(node_b, 'Output B', 'output-b', TerminalDirectionChoices.DIRECTION_SOURCE)
        input_b = self._create_terminal(node_b, 'Input B', 'input-b', TerminalDirectionChoices.DIRECTION_SINK)
        self._create_segment(output_a, input_b, 'A to B', 'a-to-b')
        self._create_segment(output_b, input_a, 'B to A', 'b-to-a')

        snapshot = PowerGraphBuilder.build_for_power_system(self.power_system, node_states=(TopologyStateChoices.STATE_ACTIVE,), path_states=(TopologyStateChoices.STATE_ACTIVE,))

        self.assertSetEqual(snapshot.cycle_node_ids(), {node_a.pk, node_b.pk})

    def test_snapshot_detects_isolated_node_and_orphan_terminal(self):
        isolated_node = self._create_node('Isolated Panel', 'isolated-panel')
        orphan_terminal = self._create_terminal(isolated_node, 'Panel Output', 'panel-output', TerminalDirectionChoices.DIRECTION_SOURCE)

        snapshot = PowerGraphBuilder.build_for_power_system(self.power_system, node_states=(TopologyStateChoices.STATE_ACTIVE,), path_states=(TopologyStateChoices.STATE_ACTIVE,))

        self.assertSetEqual(snapshot.isolated_node_ids(), {isolated_node.pk})
        self.assertSetEqual(snapshot.orphan_terminal_ids(), {orphan_terminal.pk})