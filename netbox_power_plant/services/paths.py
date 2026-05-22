from collections import deque
from dataclasses import dataclass

from dcim.models import PowerPort

from netbox_power_plant.models import PowerHandoffPoint
from netbox_power_plant.services.graph import PowerGraphBuilder


@dataclass(frozen=True)
class PowerPathResult:
    path_found: bool
    source: object
    handoff: PowerHandoffPoint | None
    power_port: PowerPort | None
    nodes: tuple
    terminals: tuple
    segments: tuple
    domains: tuple
    finding: str
    message: str


@dataclass(frozen=True)
class _QueuedPath:
    node_id: int
    segment_ids: tuple


class PowerPathResolver:
    @classmethod
    def resolve_by_handoff(
        cls,
        *,
        source_node=None,
        source_terminal=None,
        handoff,
        path_states=None,
        node_states=None,
    ):
        source_node = cls._normalize_source_node(source_node, source_terminal)
        if not source_node:
            return cls._unresolved(
                source=source_terminal,
                handoff=handoff,
                power_port=getattr(handoff, "power_port", None),
                finding="missing_source",
                message="Select a source electrical node or terminal.",
            )

        if source_terminal and source_terminal.node_id != source_node.pk:
            return cls._unresolved(
                source=source_terminal,
                handoff=handoff,
                power_port=getattr(handoff, "power_port", None),
                finding="source_mismatch",
                message="The source terminal does not belong to the source node.",
            )

        if handoff.power_system_id != source_node.power_system_id:
            return cls._unresolved(
                source=source_terminal or source_node,
                handoff=handoff,
                power_port=handoff.power_port,
                finding="power_system_mismatch",
                message="The source and handoff belong to different power systems.",
            )

        target_node = handoff.electrical_node
        target_terminal = handoff.electrical_terminal
        if target_terminal and target_node and target_terminal.node_id != target_node.pk:
            return cls._unresolved(
                source=source_terminal or source_node,
                handoff=handoff,
                power_port=handoff.power_port,
                finding="handoff_mismatch",
                message="The handoff terminal does not belong to the handoff node.",
            )
        if not target_node and target_terminal:
            target_node = target_terminal.node
        if not target_node:
            return cls._unresolved(
                source=source_terminal or source_node,
                handoff=handoff,
                power_port=handoff.power_port,
                finding="missing_handoff_topology",
                message="The handoff point is not attached to an electrical node or terminal.",
            )

        snapshot = PowerGraphBuilder.build_for_power_system(
            source_node.power_system,
            path_states=path_states,
            node_states=node_states,
        )
        return cls._resolve_in_snapshot(
            snapshot=snapshot,
            source_node=source_node,
            source_terminal=source_terminal,
            handoff=handoff,
            power_port=handoff.power_port,
            target_node=target_node,
            target_terminal=target_terminal,
        )

    @classmethod
    def resolve_by_power_port(
        cls,
        *,
        source_node=None,
        source_terminal=None,
        power_port,
        path_states=None,
        node_states=None,
    ):
        source_node = cls._normalize_source_node(source_node, source_terminal)
        if not source_node:
            return cls._unresolved(
                source=source_terminal,
                handoff=None,
                power_port=power_port,
                finding="missing_source",
                message="Select a source electrical node or terminal.",
            )

        handoffs = list(
            PowerHandoffPoint.objects.select_related(
                "power_port",
                "electrical_node",
                "electrical_terminal__node",
            ).filter(
                power_system=source_node.power_system,
                power_port=power_port,
            )
        )
        if not handoffs:
            return cls._unresolved(
                source=source_terminal or source_node,
                handoff=None,
                power_port=power_port,
                finding="handoff_not_found",
                message="No power handoff point targets this power port in the source power system.",
            )

        unresolved_results = []
        for handoff in handoffs:
            result = cls.resolve_by_handoff(
                source_node=source_node,
                source_terminal=source_terminal,
                handoff=handoff,
                path_states=path_states,
                node_states=node_states,
            )
            if result.path_found:
                return result
            unresolved_results.append(result)

        if unresolved_results:
            return unresolved_results[0]

        return cls._unresolved(
            source=source_terminal or source_node,
            handoff=None,
            power_port=power_port,
            finding="path_not_found",
            message="No path from the source to this power port was found.",
        )

    @classmethod
    def _resolve_in_snapshot(
        cls,
        *,
        snapshot,
        source_node,
        source_terminal,
        handoff,
        power_port,
        target_node,
        target_terminal,
    ):
        source = source_terminal or source_node
        if source_node.pk not in snapshot.nodes_by_id:
            return cls._unresolved(
                source=source,
                handoff=handoff,
                power_port=power_port,
                finding="source_not_in_topology",
                message="The source node is not present in the selected topology states.",
            )
        if source_terminal and source_terminal.pk not in snapshot.terminals_by_id:
            return cls._unresolved(
                source=source,
                handoff=handoff,
                power_port=power_port,
                finding="source_terminal_not_in_topology",
                message="The source terminal is not present in the selected topology states.",
            )
        if target_node.pk not in snapshot.nodes_by_id:
            return cls._unresolved(
                source=source,
                handoff=handoff,
                power_port=power_port,
                finding="target_not_in_topology",
                message="The handoff node is not present in the selected topology states.",
            )
        if target_terminal and target_terminal.pk not in snapshot.terminals_by_id:
            return cls._unresolved(
                source=source,
                handoff=handoff,
                power_port=power_port,
                finding="target_terminal_not_in_topology",
                message="The handoff terminal is not present in the selected topology states.",
            )

        segment_ids = cls._find_segment_path(
            snapshot=snapshot,
            source_node_id=source_node.pk,
            source_terminal_id=source_terminal.pk if source_terminal else None,
            target_node_id=target_node.pk,
            target_terminal_id=target_terminal.pk if target_terminal else None,
        )
        if segment_ids is None:
            return cls._unresolved(
                source=source,
                handoff=handoff,
                power_port=power_port,
                finding="path_not_found",
                message="No path from the source to this power handoff point was found.",
            )

        segments = tuple(snapshot.segments_by_id[segment_id] for segment_id in segment_ids)
        terminals = cls._ordered_terminals_for_segments(segments)
        nodes = cls._ordered_nodes_for_terminals(snapshot, terminals)
        domains = cls._ordered_domains_for_segments(segments)

        return PowerPathResult(
            path_found=True,
            source=source,
            handoff=handoff,
            power_port=power_port,
            nodes=nodes,
            terminals=terminals,
            segments=segments,
            domains=domains,
            finding="path_found",
            message="Path resolved from source to power handoff point.",
        )

    @classmethod
    def _find_segment_path(
        cls,
        *,
        snapshot,
        source_node_id,
        source_terminal_id,
        target_node_id,
        target_terminal_id,
    ):
        queue = deque([_QueuedPath(node_id=source_node_id, segment_ids=())])
        visited_node_ids = {source_node_id}

        while queue:
            queued = queue.popleft()
            for segment in cls._outbound_segments_for_node(snapshot, queued.node_id):
                if (
                    source_terminal_id
                    and queued.node_id == source_node_id
                    and segment.from_terminal_id != source_terminal_id
                ):
                    continue

                next_segment_ids = queued.segment_ids + (segment.pk,)
                destination_node_id = segment.to_terminal.node_id
                if destination_node_id == target_node_id and (
                    not target_terminal_id or segment.to_terminal_id == target_terminal_id
                ):
                    return next_segment_ids

                if destination_node_id in visited_node_ids:
                    continue
                visited_node_ids.add(destination_node_id)
                queue.append(_QueuedPath(node_id=destination_node_id, segment_ids=next_segment_ids))

        return None

    @staticmethod
    def _outbound_segments_for_node(snapshot, node_id):
        terminal_ids = snapshot.node_terminal_ids.get(node_id, set())
        segments = []
        for terminal_id in terminal_ids:
            for segment_id in snapshot.outbound_segments_by_terminal_id.get(terminal_id, set()):
                segments.append(snapshot.segments_by_id[segment_id])
        return sorted(segments, key=lambda segment: (segment.name, segment.pk))

    @staticmethod
    def _ordered_terminals_for_segments(segments):
        terminals = []
        seen_ids = set()
        for segment in segments:
            for terminal in (segment.from_terminal, segment.to_terminal):
                if terminal.pk in seen_ids:
                    continue
                seen_ids.add(terminal.pk)
                terminals.append(terminal)
        return tuple(terminals)

    @staticmethod
    def _ordered_nodes_for_terminals(snapshot, terminals):
        nodes = []
        seen_ids = set()
        for terminal in terminals:
            node_id = terminal.node_id
            if node_id in seen_ids:
                continue
            seen_ids.add(node_id)
            nodes.append(snapshot.nodes_by_id[node_id])
        return tuple(nodes)

    @staticmethod
    def _ordered_domains_for_segments(segments):
        domains = []
        seen_ids = set()
        for segment in segments:
            domain = segment.power_domain
            if not domain or domain.pk in seen_ids:
                continue
            seen_ids.add(domain.pk)
            domains.append(domain)
        return tuple(domains)

    @staticmethod
    def _normalize_source_node(source_node, source_terminal):
        if source_node:
            return source_node
        if source_terminal:
            return source_terminal.node
        return None

    @staticmethod
    def _unresolved(*, source, handoff, power_port, finding, message):
        return PowerPathResult(
            path_found=False,
            source=source,
            handoff=handoff,
            power_port=power_port,
            nodes=(),
            terminals=(),
            segments=(),
            domains=(),
            finding=finding,
            message=message,
        )
