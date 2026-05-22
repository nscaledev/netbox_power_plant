from netbox_power_plant.choices import (
    NodeKindChoices,
    PhaseModeChoices,
    PlacementLabelModeChoices,
    PlacementSymbolKindChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TerminalRoleChoices,
)
from netbox_power_plant.models import (
    PowerArchitectureTemplate,
    TemplateNode,
    TemplatePlacementRule,
    TemplateSegment,
    TemplateTerminal,
)


REFERENCE_TEMPLATE_SLUGS = (
    "ai-pod-2n-ups-busway",
    "ai-pod-distributed-redundant-ups",
    "high-density-dc-48v",
)


def seed_reference_templates():
    seeded = []
    for spec in _reference_template_specs():
        seeded.append(_upsert_template(spec))
    return tuple(seeded)


def _upsert_template(spec):
    template, _ = PowerArchitectureTemplate.objects.update_or_create(
        slug=spec["slug"],
        defaults={
            "name": spec["name"],
            "version": spec.get("version", "1"),
            "is_active": True,
            "default_context": spec.get("default_context", {}),
        },
    )

    node_keys = {node_spec["key"] for node_spec in spec.get("nodes", ())}
    segment_keys = {segment_spec["key"] for segment_spec in spec.get("segments", ())}

    TemplateSegment.objects.filter(template=template).exclude(key__in=segment_keys).delete()
    TemplateNode.objects.filter(template=template).exclude(key__in=node_keys).delete()

    for node_spec in spec.get("nodes", ()):
        node, _ = TemplateNode.objects.update_or_create(
            template=template,
            key=node_spec["key"],
            defaults={
                "name": f"{template.name} {node_spec['name']}",
                "slug": f"{template.slug}-{node_spec['key']}",
                "name_format": node_spec.get("name_format", ""),
                "slug_format": node_spec.get("slug_format", ""),
                "parent_key": node_spec.get("parent_key", ""),
                "node_kind": node_spec.get("node_kind", NodeKindChoices.KIND_CUSTOM),
                "equipment_role": node_spec.get("equipment_role", ""),
                "phase_mode": node_spec.get("phase_mode", PhaseModeChoices.MODE_THREE_PHASE),
                "install_state": node_spec.get("install_state", "planned"),
                "topology_state": node_spec.get("topology_state", "planned"),
                "attributes": node_spec.get("attributes", {}),
            },
        )

        terminal_keys = {terminal_spec["key"] for terminal_spec in node_spec.get("terminals", ())}
        TemplateTerminal.objects.filter(template_node=node).exclude(key__in=terminal_keys).delete()
        for terminal_spec in node_spec.get("terminals", ()):
            TemplateTerminal.objects.update_or_create(
                template_node=node,
                key=terminal_spec["key"],
                defaults={
                    "name": f"{template.name} {node_spec['name']} {terminal_spec['name']} {terminal_spec['key']}",
                    "slug": f"{template.slug}-{node_spec['key']}-{terminal_spec['key']}",
                    "name_format": terminal_spec.get("name_format", ""),
                    "slug_format": terminal_spec.get("slug_format", ""),
                    "terminal_role": terminal_spec.get("terminal_role", TerminalRoleChoices.ROLE_CUSTOM),
                    "direction": terminal_spec.get("direction", TerminalDirectionChoices.DIRECTION_BIDIRECTIONAL),
                    "supply_type": terminal_spec.get("supply_type", SupplyTypeChoices.SUPPLY_AC),
                    "position_index": terminal_spec.get("position_index"),
                    "attributes": terminal_spec.get("attributes", {}),
                },
            )

        if node_spec.get("placement"):
            placement = node_spec["placement"]
            TemplatePlacementRule.objects.update_or_create(
                template_node=node,
                defaults={
                    "name": f"{template.name} {node_spec['name']} Placement",
                    "slug": f"{template.slug}-{node_spec['key']}-placement",
                    **placement,
                },
            )
        else:
            TemplatePlacementRule.objects.filter(template_node=node).delete()

    for segment_spec in spec.get("segments", ()):
        TemplateSegment.objects.update_or_create(
            template=template,
            key=segment_spec["key"],
            defaults={
                "name": f"{template.name} {segment_spec['name']}",
                "slug": f"{template.slug}-{segment_spec['key']}",
                "name_format": segment_spec.get("name_format", ""),
                "slug_format": segment_spec.get("slug_format", ""),
                "from_node_key": segment_spec["from_node_key"],
                "from_terminal_key": segment_spec["from_terminal_key"],
                "to_node_key": segment_spec["to_node_key"],
                "to_terminal_key": segment_spec["to_terminal_key"],
                "segment_kind": segment_spec.get("segment_kind", SegmentKindChoices.KIND_FEEDER),
                "path_state": segment_spec.get("path_state", "planned"),
                "attributes": segment_spec.get("attributes", {}),
            },
        )

    return template


def _reference_template_specs():
    return (
        _ai_pod_2n_ups_busway(),
        _ai_pod_distributed_redundant_ups(),
        _high_density_dc_48v(),
    )


def _terminal(
    key,
    name,
    role,
    direction,
    *,
    supply_type=SupplyTypeChoices.SUPPLY_AC,
    position_index=1,
    attributes=None,
):
    return {
        "key": key,
        "name": name,
        "terminal_role": role,
        "direction": direction,
        "supply_type": supply_type,
        "position_index": position_index,
        "attributes": attributes or {},
    }


def _input_terminal(key="input", name="Input", *, supply_type=SupplyTypeChoices.SUPPLY_AC, position_index=1):
    return _terminal(
        key,
        name,
        TerminalRoleChoices.ROLE_INPUT,
        TerminalDirectionChoices.DIRECTION_SINK,
        supply_type=supply_type,
        position_index=position_index,
    )


def _output_terminal(key="output", name="Output", *, supply_type=SupplyTypeChoices.SUPPLY_AC, position_index=1):
    return _terminal(
        key,
        name,
        TerminalRoleChoices.ROLE_OUTPUT,
        TerminalDirectionChoices.DIRECTION_SOURCE,
        supply_type=supply_type,
        position_index=position_index,
    )


def _placement(
    x,
    y,
    width="5.00",
    height="2.50",
    *,
    symbol_kind=PlacementSymbolKindChoices.KIND_EQUIPMENT,
    color="",
    z_index=100,
):
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "symbol_kind": symbol_kind,
        "label_mode": PlacementLabelModeChoices.MODE_NAME_KIND,
        "color": color,
        "z_index": z_index,
    }


def _rack_handoff(feed, *, terminal_key="input", context_prefix="rack_feed", index_key="rack_feed_index"):
    feed_lower = feed.lower()
    return {
        "key": f"{feed_lower}-handoff-{{{index_key}}}",
        "terminal_key": terminal_key,
        "name_format": f"{{power_system}} {feed} rack feed {{{index_key}}}",
        "slug_format": f"{{power_system_slug}}-{feed_lower}-rack-feed-{{{index_key}}}",
        "power_port_context_key": f"{context_prefix}_{feed_lower}_power_port_{{{index_key}}}",
        "expected_redundancy_group_context_key": f"{context_prefix}_redundancy_group_id",
        "feed_label": f"{feed}-feed",
        "delivery_role": "primary" if feed == "A" else "redundant",
    }


def _dc_handoff():
    return {
        "key": "dc-handoff-{dc_feed_index}",
        "terminal_key": "input",
        "name_format": "{power_system} DC rack terminal {dc_feed_index}",
        "slug_format": "{power_system_slug}-dc-rack-terminal-{dc_feed_index}",
        "power_port_context_key": "rack_dc_power_port_{dc_feed_index}",
        "expected_redundancy_group_context_key": "dc_redundancy_group_id",
        "feed_label": "48V-DC",
        "delivery_role": "dc-primary",
    }


def _common_default_context(topology, feed_count_key, feed_count):
    return {
        "pod_label": "AI Pod",
        "topology": topology,
        feed_count_key: feed_count,
        "rack_feed_redundancy_group_id": "",
        "rack_pdu_redundancy_group_id": "",
        "dc_redundancy_group_id": "",
        "power_domains": {
            "A": {"label": "Critical A", "isolation_role": "primary"},
            "B": {"label": "Critical B", "isolation_role": "redundant"},
            "DC": {"label": "48V DC", "isolation_role": "direct-current"},
        },
        "repeatables": {
            feed_count_key: {
                "label": "rack power handoff count",
                "start": 1,
                "operator_context_pattern": f"{feed_count_key}=N",
            },
        },
    }


def _ai_pod_2n_ups_busway():
    return {
        "name": "AI Pod 2N UPS Busway",
        "slug": "ai-pod-2n-ups-busway",
        "default_context": _common_default_context("2n-ups-busway", "rack_feed_count", 2),
        "nodes": (
            _node(
                "utility",
                "Utility Service",
                NodeKindChoices.KIND_UTILITY_SERVICE,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "0.00", "3.00", symbol_kind=PlacementSymbolKindChoices.KIND_SOURCE, color="0d6efd"
                ),
                attributes={"power_domain_codes": ["utility"], "source_role": "normal-utility"},
            ),
            _node(
                "generator-a",
                "Generator A",
                NodeKindChoices.KIND_GENERATOR,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "7.00", "0.00", symbol_kind=PlacementSymbolKindChoices.KIND_SOURCE, color="198754"
                ),
                attributes={"power_domain_codes": ["A"], "redundancy_role": "2n-a-generator"},
            ),
            _node(
                "generator-b",
                "Generator B",
                NodeKindChoices.KIND_GENERATOR,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "7.00", "6.00", symbol_kind=PlacementSymbolKindChoices.KIND_SOURCE, color="198754"
                ),
                attributes={"power_domain_codes": ["B"], "redundancy_role": "2n-b-generator"},
            ),
            _node(
                "ats",
                "Automatic Transfer Switch",
                NodeKindChoices.KIND_ATS,
                terminals=(
                    _input_terminal("utility-input", "Utility Input", position_index=1),
                    _input_terminal("generator-a-input", "Generator A Input", position_index=2),
                    _input_terminal("generator-b-input", "Generator B Input", position_index=3),
                    _output_terminal(position_index=4),
                ),
                placement=_placement("14.00", "3.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION),
                attributes={"power_domain_codes": ["A", "B"], "transfer_role": "2n-source-selection"},
            ),
            _node(
                "lv-switchboard-a",
                "LV Switchboard A",
                NodeKindChoices.KIND_LV_SWITCHBOARD,
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "21.00", "0.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="0dcaf0"
                ),
                attributes={"power_domain_codes": ["A"], "redundancy_role": "2n-a-distribution"},
            ),
            _node(
                "lv-switchboard-b",
                "LV Switchboard B",
                NodeKindChoices.KIND_LV_SWITCHBOARD,
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "21.00", "6.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="fd7e14"
                ),
                attributes={"power_domain_codes": ["B"], "redundancy_role": "2n-b-distribution"},
            ),
            _node(
                "ups-bank-a",
                "UPS Bank A",
                NodeKindChoices.KIND_UPS,
                parent_key="lv-switchboard-a",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement("29.00", "0.00", color="0dcaf0"),
                attributes={"power_domain_codes": ["A"], "redundancy_role": "2n-a-ups-bank"},
            ),
            _node(
                "ups-bank-b",
                "UPS Bank B",
                NodeKindChoices.KIND_UPS,
                parent_key="lv-switchboard-b",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement("29.00", "6.00", color="fd7e14"),
                attributes={"power_domain_codes": ["B"], "redundancy_role": "2n-b-ups-bank"},
            ),
            _node(
                "busway-a",
                "Busway A",
                NodeKindChoices.KIND_BUSWAY_RUN,
                parent_key="ups-bank-a",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "37.00", "0.00", "9.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="0dcaf0"
                ),
                attributes={"power_domain_codes": ["A"], "bus_role": "rack-row-a"},
            ),
            _node(
                "busway-b",
                "Busway B",
                NodeKindChoices.KIND_BUSWAY_RUN,
                parent_key="ups-bank-b",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "37.00", "6.00", "9.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="fd7e14"
                ),
                attributes={"power_domain_codes": ["B"], "bus_role": "rack-row-b"},
            ),
            _node(
                "rack-feed-a",
                "Rack PDU Feed A",
                NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
                parent_key="busway-a",
                name_format="{power_system} A rack feed {rack_feed_index}",
                terminals=(_input_terminal(supply_type=SupplyTypeChoices.SUPPLY_AC),),
                attributes={
                    "power_domain_codes": ["A"],
                    "domain_metadata": {"domain": "A", "rack_boundary": True},
                    "repeat": {
                        "count_context_key": "rack_feed_count",
                        "context_key": "rack_feed_index",
                        "key_format": "rack-feed-a-{rack_feed_index}",
                    },
                    "power_handoffs": (_rack_handoff("A"),),
                },
            ),
            _node(
                "rack-feed-b",
                "Rack PDU Feed B",
                NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
                parent_key="busway-b",
                name_format="{power_system} B rack feed {rack_feed_index}",
                terminals=(_input_terminal(supply_type=SupplyTypeChoices.SUPPLY_AC),),
                attributes={
                    "power_domain_codes": ["B"],
                    "domain_metadata": {"domain": "B", "rack_boundary": True},
                    "repeat": {
                        "count_context_key": "rack_feed_count",
                        "context_key": "rack_feed_index",
                        "key_format": "rack-feed-b-{rack_feed_index}",
                    },
                    "power_handoffs": (_rack_handoff("B"),),
                },
            ),
        ),
        "segments": (
            _segment("utility-to-ats", "Utility to ATS", "utility", "output", "ats", "utility-input", ["utility"]),
            _segment(
                "generator-a-to-ats", "Generator A to ATS", "generator-a", "output", "ats", "generator-a-input", ["A"]
            ),
            _segment(
                "generator-b-to-ats", "Generator B to ATS", "generator-b", "output", "ats", "generator-b-input", ["B"]
            ),
            _segment("ats-to-lv-a", "ATS to LV Switchboard A", "ats", "output", "lv-switchboard-a", "input", ["A"]),
            _segment("ats-to-lv-b", "ATS to LV Switchboard B", "ats", "output", "lv-switchboard-b", "input", ["B"]),
            _segment("lv-a-to-ups-a", "LV A to UPS A", "lv-switchboard-a", "output", "ups-bank-a", "input", ["A"]),
            _segment("lv-b-to-ups-b", "LV B to UPS B", "lv-switchboard-b", "output", "ups-bank-b", "input", ["B"]),
            _segment("ups-a-to-busway-a", "UPS A to Busway A", "ups-bank-a", "output", "busway-a", "input", ["A"]),
            _segment("ups-b-to-busway-b", "UPS B to Busway B", "ups-bank-b", "output", "busway-b", "input", ["B"]),
            _repeat_segment(
                "busway-a-to-rack-feed",
                "Busway A to Rack Feed",
                "busway-a",
                "output",
                "rack-feed-a",
                "input",
                ["A"],
                "rack_feed_count",
                "rack_feed_index",
                "rack-feed-a-{rack_feed_index}",
            ),
            _repeat_segment(
                "busway-b-to-rack-feed",
                "Busway B to Rack Feed",
                "busway-b",
                "output",
                "rack-feed-b",
                "input",
                ["B"],
                "rack_feed_count",
                "rack_feed_index",
                "rack-feed-b-{rack_feed_index}",
            ),
        ),
    }


def _ai_pod_distributed_redundant_ups():
    return {
        "name": "AI Pod Distributed Redundant UPS",
        "slug": "ai-pod-distributed-redundant-ups",
        "default_context": _common_default_context("distributed-redundant-ups", "rack_pdu_count", 2),
        "nodes": (
            _node(
                "utility",
                "Utility Service",
                NodeKindChoices.KIND_UTILITY_SERVICE,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "0.00", "4.00", symbol_kind=PlacementSymbolKindChoices.KIND_SOURCE, color="0d6efd"
                ),
                attributes={"power_domain_codes": ["utility"]},
            ),
            _node(
                "generator-a",
                "Generator A",
                NodeKindChoices.KIND_GENERATOR,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "6.00", "0.00", symbol_kind=PlacementSymbolKindChoices.KIND_SOURCE, color="198754"
                ),
                attributes={"power_domain_codes": ["A"]},
            ),
            _node(
                "generator-b",
                "Generator B",
                NodeKindChoices.KIND_GENERATOR,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "6.00", "8.00", symbol_kind=PlacementSymbolKindChoices.KIND_SOURCE, color="198754"
                ),
                attributes={"power_domain_codes": ["B"]},
            ),
            _node(
                "paralleling-gear",
                "Generator Paralleling Gear",
                NodeKindChoices.KIND_PARALLELING_GEAR,
                terminals=(
                    _input_terminal("utility-input", "Utility Input", position_index=1),
                    _input_terminal("generator-a-input", "Generator A Input", position_index=2),
                    _input_terminal("generator-b-input", "Generator B Input", position_index=3),
                    _output_terminal("output-a", "Output A", position_index=4),
                    _output_terminal("output-b", "Output B", position_index=5),
                ),
                placement=_placement("13.00", "4.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION),
                attributes={"power_domain_codes": ["A", "B"], "parallel_group": "pod-source"},
            ),
            _node(
                "transformer-a",
                "Transformer A",
                NodeKindChoices.KIND_TRANSFORMER,
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement("21.00", "0.00", color="0dcaf0"),
                attributes={"power_domain_codes": ["A"], "redundancy_role": "distributed-a-transformer"},
            ),
            _node(
                "transformer-b",
                "Transformer B",
                NodeKindChoices.KIND_TRANSFORMER,
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement("21.00", "8.00", color="fd7e14"),
                attributes={"power_domain_codes": ["B"], "redundancy_role": "distributed-b-transformer"},
            ),
            _node(
                "lv-switchboard-a",
                "LV Switchboard A",
                NodeKindChoices.KIND_LV_SWITCHBOARD,
                parent_key="transformer-a",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "29.00", "0.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="0dcaf0"
                ),
                attributes={"power_domain_codes": ["A"]},
            ),
            _node(
                "lv-switchboard-b",
                "LV Switchboard B",
                NodeKindChoices.KIND_LV_SWITCHBOARD,
                parent_key="transformer-b",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "29.00", "8.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="fd7e14"
                ),
                attributes={"power_domain_codes": ["B"]},
            ),
            _node(
                "ups-a",
                "Distributed UPS A",
                NodeKindChoices.KIND_UPS,
                parent_key="lv-switchboard-a",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement("37.00", "0.00", color="0dcaf0"),
                attributes={"power_domain_codes": ["A"], "redundancy_role": "distributed-a-ups"},
            ),
            _node(
                "ups-b",
                "Distributed UPS B",
                NodeKindChoices.KIND_UPS,
                parent_key="lv-switchboard-b",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement("37.00", "8.00", color="fd7e14"),
                attributes={"power_domain_codes": ["B"], "redundancy_role": "distributed-b-ups"},
            ),
            _node(
                "busway-a",
                "Busway A",
                NodeKindChoices.KIND_BUSWAY_RUN,
                parent_key="ups-a",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "45.00", "0.00", "9.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="0dcaf0"
                ),
                attributes={"power_domain_codes": ["A"], "bus_role": "distributed-a-rack-row"},
            ),
            _node(
                "busway-b",
                "Busway B",
                NodeKindChoices.KIND_BUSWAY_RUN,
                parent_key="ups-b",
                terminals=(_input_terminal(), _output_terminal(position_index=2)),
                placement=_placement(
                    "45.00", "8.00", "9.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="fd7e14"
                ),
                attributes={"power_domain_codes": ["B"], "bus_role": "distributed-b-rack-row"},
            ),
            _node(
                "rack-pdu",
                "Dual-feed Rack PDU",
                NodeKindChoices.KIND_RACK_PDU,
                name_format="{power_system} rack PDU {rack_pdu_index}",
                terminals=(
                    _input_terminal("input-a", "Input A", position_index=1),
                    _input_terminal("input-b", "Input B", position_index=2),
                ),
                attributes={
                    "power_domain_codes": ["A", "B"],
                    "domain_metadata": {"domains": ["A", "B"], "rack_boundary": True, "feed_count": 2},
                    "repeat": {
                        "count_context_key": "rack_pdu_count",
                        "context_key": "rack_pdu_index",
                        "key_format": "rack-pdu-{rack_pdu_index}",
                    },
                    "power_handoffs": (
                        _rack_handoff(
                            "A", terminal_key="input-a", context_prefix="rack_pdu", index_key="rack_pdu_index"
                        ),
                        _rack_handoff(
                            "B", terminal_key="input-b", context_prefix="rack_pdu", index_key="rack_pdu_index"
                        ),
                    ),
                },
            ),
        ),
        "segments": (
            _segment(
                "utility-to-parallel",
                "Utility to Paralleling Gear",
                "utility",
                "output",
                "paralleling-gear",
                "utility-input",
                ["utility"],
            ),
            _segment(
                "gen-a-to-parallel",
                "Generator A to Paralleling Gear",
                "generator-a",
                "output",
                "paralleling-gear",
                "generator-a-input",
                ["A"],
            ),
            _segment(
                "gen-b-to-parallel",
                "Generator B to Paralleling Gear",
                "generator-b",
                "output",
                "paralleling-gear",
                "generator-b-input",
                ["B"],
            ),
            _segment(
                "parallel-to-transformer-a",
                "Paralleling Gear to Transformer A",
                "paralleling-gear",
                "output-a",
                "transformer-a",
                "input",
                ["A"],
            ),
            _segment(
                "parallel-to-transformer-b",
                "Paralleling Gear to Transformer B",
                "paralleling-gear",
                "output-b",
                "transformer-b",
                "input",
                ["B"],
            ),
            _segment(
                "transformer-a-to-lv-a",
                "Transformer A to LV A",
                "transformer-a",
                "output",
                "lv-switchboard-a",
                "input",
                ["A"],
            ),
            _segment(
                "transformer-b-to-lv-b",
                "Transformer B to LV B",
                "transformer-b",
                "output",
                "lv-switchboard-b",
                "input",
                ["B"],
            ),
            _segment("lv-a-to-ups-a", "LV A to UPS A", "lv-switchboard-a", "output", "ups-a", "input", ["A"]),
            _segment("lv-b-to-ups-b", "LV B to UPS B", "lv-switchboard-b", "output", "ups-b", "input", ["B"]),
            _segment("ups-a-to-busway-a", "UPS A to Busway A", "ups-a", "output", "busway-a", "input", ["A"]),
            _segment("ups-b-to-busway-b", "UPS B to Busway B", "ups-b", "output", "busway-b", "input", ["B"]),
            _repeat_segment(
                "busway-a-to-rack-pdu",
                "Busway A to Rack PDU",
                "busway-a",
                "output",
                "rack-pdu",
                "input-a",
                ["A"],
                "rack_pdu_count",
                "rack_pdu_index",
                "rack-pdu-{rack_pdu_index}",
                kind=SegmentKindChoices.KIND_RACK_FEED,
            ),
            _repeat_segment(
                "busway-b-to-rack-pdu",
                "Busway B to Rack PDU",
                "busway-b",
                "output",
                "rack-pdu",
                "input-b",
                ["B"],
                "rack_pdu_count",
                "rack_pdu_index",
                "rack-pdu-{rack_pdu_index}",
                kind=SegmentKindChoices.KIND_RACK_FEED,
            ),
        ),
    }


def _high_density_dc_48v():
    dc_input = _input_terminal(supply_type=SupplyTypeChoices.SUPPLY_DC)
    dc_output = _output_terminal(supply_type=SupplyTypeChoices.SUPPLY_DC, position_index=2)
    return {
        "name": "High Density DC 48V",
        "slug": "high-density-dc-48v",
        "default_context": _common_default_context("high-density-dc-48v", "dc_feed_count", 2)
        | {"distribution_voltage": "48"},
        "nodes": (
            _node(
                "lv-switchboard",
                "LV Switchboard",
                NodeKindChoices.KIND_LV_SWITCHBOARD,
                terminals=(_output_terminal(),),
                placement=_placement(
                    "0.00", "2.50", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="0d6efd"
                ),
                attributes={"power_domain_codes": ["AC"], "source_role": "rectifier-ac-source"},
            ),
            _node(
                "rectifier",
                "48V Rectifier Plant",
                NodeKindChoices.KIND_RECTIFIER,
                phase_mode=PhaseModeChoices.MODE_MIXED,
                terminals=(
                    _input_terminal("ac-input", "AC Input"),
                    _output_terminal(
                        "dc-output", "DC Output", supply_type=SupplyTypeChoices.SUPPLY_DC, position_index=2
                    ),
                ),
                placement=_placement("8.00", "2.50", color="198754"),
                attributes={"power_domain_codes": ["AC", "DC"], "nominal_voltage_vdc": 48},
            ),
            _node(
                "dc-bus",
                "48V DC Bus",
                NodeKindChoices.KIND_BUSWAY_RUN,
                parent_key="rectifier",
                phase_mode=PhaseModeChoices.MODE_DC,
                terminals=(dc_input, dc_output),
                placement=_placement(
                    "16.00", "2.50", "9.00", symbol_kind=PlacementSymbolKindChoices.KIND_DISTRIBUTION, color="20c997"
                ),
                attributes={"power_domain_codes": ["DC"], "bus_role": "rack-row-48v"},
            ),
            _node(
                "rack-dc-terminal",
                "Rack DC Terminal",
                NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
                parent_key="dc-bus",
                phase_mode=PhaseModeChoices.MODE_DC,
                name_format="{power_system} rack DC terminal {dc_feed_index}",
                terminals=(_input_terminal(supply_type=SupplyTypeChoices.SUPPLY_DC),),
                attributes={
                    "power_domain_codes": ["DC"],
                    "domain_metadata": {"domain": "DC", "rack_boundary": True, "nominal_voltage_vdc": 48},
                    "repeat": {
                        "count_context_key": "dc_feed_count",
                        "context_key": "dc_feed_index",
                        "key_format": "rack-dc-terminal-{dc_feed_index}",
                    },
                    "power_handoffs": (_dc_handoff(),),
                },
            ),
        ),
        "segments": (
            _segment(
                "lv-to-rectifier",
                "LV Switchboard to Rectifier",
                "lv-switchboard",
                "output",
                "rectifier",
                "ac-input",
                ["AC"],
            ),
            _segment(
                "rectifier-to-dc-bus",
                "Rectifier to 48V DC Bus",
                "rectifier",
                "dc-output",
                "dc-bus",
                "input",
                ["DC"],
                SegmentKindChoices.KIND_DC_LINK,
            ),
            _repeat_segment(
                "dc-bus-to-rack-terminal",
                "48V DC Bus to Rack Terminal",
                "dc-bus",
                "output",
                "rack-dc-terminal",
                "input",
                ["DC"],
                "dc_feed_count",
                "dc_feed_index",
                "rack-dc-terminal-{dc_feed_index}",
                kind=SegmentKindChoices.KIND_DC_LINK,
            ),
        ),
    }


def _node(
    key,
    name,
    node_kind,
    *,
    terminals,
    parent_key="",
    name_format="",
    phase_mode=PhaseModeChoices.MODE_THREE_PHASE,
    placement=None,
    attributes=None,
):
    return {
        "key": key,
        "name": name,
        "node_kind": node_kind,
        "parent_key": parent_key,
        "name_format": name_format,
        "phase_mode": phase_mode,
        "attributes": attributes or {},
        "terminals": terminals,
        "placement": placement,
    }


def _segment(key, name, from_node, from_terminal, to_node, to_terminal, domains, kind=SegmentKindChoices.KIND_FEEDER):
    return {
        "key": key,
        "name": name,
        "from_node_key": from_node,
        "from_terminal_key": from_terminal,
        "to_node_key": to_node,
        "to_terminal_key": to_terminal,
        "segment_kind": kind,
        "attributes": {"power_domain_codes": domains, "domain_metadata": {"domains": domains}},
    }


def _repeat_segment(
    key,
    name,
    from_node,
    from_terminal,
    to_node,
    to_terminal,
    domains,
    count_context_key,
    context_key,
    to_node_key_format,
    *,
    kind=SegmentKindChoices.KIND_TAP_CONNECTION,
):
    return {
        **_segment(key, name, from_node, from_terminal, to_node, to_terminal, domains, kind),
        "attributes": {
            "power_domain_codes": domains,
            "domain_metadata": {"domains": domains, "rack_boundary": True},
            "repeat": {
                "count_context_key": count_context_key,
                "context_key": context_key,
                "key_format": f"{key}-{{{context_key}}}",
            },
            "to_node_key_format": to_node_key_format,
        },
    }
