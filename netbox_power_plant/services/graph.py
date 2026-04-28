from collections import defaultdict, deque
from dataclasses import dataclass

from netbox_power_plant.choices import TopologyStateChoices


@dataclass(frozen=True)
class TraversalContext:
    start_node_id: int
    direction: str


@dataclass
class PowerGraphSnapshot:
    power_system_id: int
    nodes_by_id: dict
    terminals_by_id: dict
    segments_by_id: dict
    inbound_neighbors: dict
    outbound_neighbors: dict
    inbound_segments_by_terminal_id: dict
    outbound_segments_by_terminal_id: dict
    node_terminal_ids: dict

    def upstream_node_ids(self, start_node_id):
        return self._traverse(start_node_id, self.inbound_neighbors)

    def downstream_node_ids(self, start_node_id):
        return self._traverse(start_node_id, self.outbound_neighbors)

    def isolated_node_ids(self):
        isolated_ids = set()
        for node_id in self.nodes_by_id:
            if self.inbound_neighbors.get(node_id) or self.outbound_neighbors.get(node_id):
                continue
            isolated_ids.add(node_id)
        return isolated_ids

    def orphan_terminal_ids(self):
        orphan_ids = set()
        for terminal_id in self.terminals_by_id:
            if self.inbound_segments_by_terminal_id.get(terminal_id) or self.outbound_segments_by_terminal_id.get(terminal_id):
                continue
            orphan_ids.add(terminal_id)
        return orphan_ids

    def cycle_node_ids(self):
        visited = set()
        stack = []
        stack_index = {}
        cycle_node_ids = set()

        def visit(node_id):
            if node_id in stack_index:
                cycle_start = stack_index[node_id]
                cycle_node_ids.update(stack[cycle_start:])
                cycle_node_ids.add(node_id)
                return
            if node_id in visited:
                return

            visited.add(node_id)
            stack_index[node_id] = len(stack)
            stack.append(node_id)

            for neighbor_id in self.outbound_neighbors.get(node_id, set()):
                visit(neighbor_id)

            stack.pop()
            stack_index.pop(node_id, None)

        for node_id in self.nodes_by_id:
            visit(node_id)

        return cycle_node_ids

    def _traverse(self, start_node_id, adjacency):
        traversal = TraversalContext(start_node_id=start_node_id, direction='downstream' if adjacency is self.outbound_neighbors else 'upstream')
        del traversal
        visited = set()
        queue = deque([start_node_id])

        while queue:
            current_id = queue.popleft()
            for neighbor_id in adjacency.get(current_id, set()):
                if neighbor_id in visited or neighbor_id == start_node_id:
                    continue
                visited.add(neighbor_id)
                queue.append(neighbor_id)

        return visited


class PowerGraphBuilder:
    DEFAULT_PATH_STATES = (
        TopologyStateChoices.STATE_PLANNED,
        TopologyStateChoices.STATE_ACTIVE,
    )
    DEFAULT_NODE_STATES = (
        TopologyStateChoices.STATE_PLANNED,
        TopologyStateChoices.STATE_ACTIVE,
    )

    @classmethod
    def build_for_power_system(cls, power_system, *, path_states=None, node_states=None):
        from netbox_power_plant.models import ElectricalNode, ElectricalSegment, ElectricalTerminal

        path_states = tuple(path_states or cls.DEFAULT_PATH_STATES)
        node_states = tuple(node_states or cls.DEFAULT_NODE_STATES)

        nodes = list(
            ElectricalNode.objects.filter(power_system=power_system, topology_state__in=node_states)
        )
        node_ids = [node.pk for node in nodes]
        terminals = list(
            ElectricalTerminal.objects.filter(node_id__in=node_ids)
        )
        terminal_ids = [terminal.pk for terminal in terminals]
        segments = list(
            ElectricalSegment.objects.select_related('from_terminal__node', 'to_terminal__node').filter(
                power_system=power_system,
                path_state__in=path_states,
                from_terminal_id__in=terminal_ids,
                to_terminal_id__in=terminal_ids,
            )
        )

        inbound_neighbors = defaultdict(set)
        outbound_neighbors = defaultdict(set)
        inbound_segments_by_terminal_id = defaultdict(set)
        outbound_segments_by_terminal_id = defaultdict(set)
        node_terminal_ids = defaultdict(set)

        for terminal in terminals:
            node_terminal_ids[terminal.node_id].add(terminal.pk)

        for segment in segments:
            source_node_id = segment.from_terminal.node_id
            destination_node_id = segment.to_terminal.node_id
            outbound_neighbors[source_node_id].add(destination_node_id)
            inbound_neighbors[destination_node_id].add(source_node_id)
            outbound_segments_by_terminal_id[segment.from_terminal_id].add(segment.pk)
            inbound_segments_by_terminal_id[segment.to_terminal_id].add(segment.pk)

        return PowerGraphSnapshot(
            power_system_id=power_system.pk,
            nodes_by_id={node.pk: node for node in nodes},
            terminals_by_id={terminal.pk: terminal for terminal in terminals},
            segments_by_id={segment.pk: segment for segment in segments},
            inbound_neighbors=dict(inbound_neighbors),
            outbound_neighbors=dict(outbound_neighbors),
            inbound_segments_by_terminal_id=dict(inbound_segments_by_terminal_id),
            outbound_segments_by_terminal_id=dict(outbound_segments_by_terminal_id),
            node_terminal_ids=dict(node_terminal_ids),
        )