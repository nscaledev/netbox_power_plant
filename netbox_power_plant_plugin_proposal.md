# NetBox Power-Plant Plugin
## Markdown Implementation Plan

## 1. Purpose

This plugin extends NetBox so it can model the **facility-side electrical design** of modern data centers, not just the rack/device-side power objects already present in core NetBox.

The implementation is intentionally split into two cooperating layers:

- **Core NetBox remains the system of record for** sites, locations, racks, devices, modules, power ports, power outlets, power feeds, and physical cabling at the IT/device boundary.
- **The plugin owns** the upstream electrical graph: utility service, generators, switchgear, transformers, UPS plants, battery systems, ATS/STS, busway, PDUs/RPPs/panelboards, rack circuits, redundancy domains, protection, capacity, and bulk-instantiation workflows.

The plugin must satisfy two goals:

1. provide a data model that is actually expressive enough for real modern power-train design, including redundancy and templated repetition at scale;
2. provide UI and automation workflows that let operators define those designs once and stamp them into halls/rows/racks without hand-creating thousands of objects.

---

## 2. Non-Goals for v1

The initial release should **not** attempt to be a full EPMS/BMS platform.

Out of scope for v1:

- real-time telemetry polling and time-series storage;
- power-quality waveform analytics;
- full relay coordination / short-circuit study calculations;
- live breaker-trip simulation;
- CAD-grade one-line-diagram rendering;
- cost accounting / utility billing;
- construction project management.

These can be added later through integrations and specialized jobs.

---

## 3. Recommended Target Platform

### Baseline

- **NetBox target:** `>= 4.4`
- **Python target:** align to current supported NetBox plugin baseline
- **Database:** PostgreSQL, using standard NetBox deployment patterns

### Optional enhanced UX path

- **NetBox 4.5+** can optionally be used for newer programmatic UI components
- treat those UI components as **progressive enhancement**, not a hard dependency, because they are documented as new/beta in current NetBox docs

### Packaging posture

- ship as a standard NetBox plugin Python package
- expose docs via plugin `docs_url`
- support REST API from day one
- defer GraphQL until the relational and service layers have settled

---

## 4. Architectural Principles

### 4.1 Model the plant as a typed electrical graph

Do **not** attempt to represent the facility solely with simple parent/child foreign keys.

That approach collapses under:

- 2N and distributed-redundant designs;
- shared upstream segments;
- ATS/STS crossover behavior;
- busway plus tap-off patterns;
- parallel UPS blocks;
- AC and DC distribution domains;
- shared protection envelopes;
- hall-level templating.

The correct backbone is:

- **nodes** = equipment or logical electrical objects
- **terminals** = named electrical connection points on nodes
- **segments** = electrically meaningful connections between terminals
- **paths** = derived graph traversals from source to rack/device boundary

### 4.2 Separate topology, placement, and inventory identity

Every object should be understandable along three axes:

- **topology**: what powers what
- **placement**: where it physically lives
- **inventory identity**: what actual asset or design-instance it is

This separation is what makes templating and repeated instantiation workable.

### 4.3 Use core NetBox as the rack/device boundary

The plugin should not re-implement:

- devices
- racks
- power ports
- power outlets
- power feeds
- cables

Instead, it should introduce explicit **boundary models** that map plugin electrical objects onto those native NetBox objects.

### 4.4 Keep heavy logic out of forms and views

The application should have a strong service layer for:

- graph construction
- path traversal
- capacity rollups
- redundancy validation
- template instantiation
- import orchestration
- impact analysis

Think of Django models as storage contracts, not the whole brain.

---

## 5. High-Level Domain Model

## 5.1 Core plugin apps

Suggested internal app layout:

```text
netbox_powerplant/
  choices.py
  constants.py
  models/
    common.py
    systems.py
    topology.py
    equipment.py
    distribution.py
    protection.py
    templates.py
    bindings.py
    telemetry.py
  services/
    graph.py
    paths.py
    validation.py
    capacity.py
    instantiate.py
    naming.py
    importers.py
    diff.py
    summarization.py
  api/
    serializers.py
    viewsets.py
    urls.py
  filtersets.py
  forms/
    model_forms.py
    bulk_import_forms.py
    bulk_edit_forms.py
    filter_forms.py
    wizard_forms.py
  tables.py
  views/
    standard.py
    topology.py
    validation.py
    wizards.py
    reports.py
  jobs/
    instantiate_template.py
    recalculate_rollups.py
    validate_scope.py
    import_design.py
  navigation.py
  search.py
  signals.py
  template_content.py
```

---

## 5.2 Abstract base models

### `PowerPlantModel(NetBoxModel)`

Abstract base for most plugin models.

Common fields:

- `name`
- `slug`
- `status`
- `description`
- `comments`
- `tags`
- `custom_field_data` (via NetBox features)
- `site` FK (nullable where appropriate)
- `location` FK (nullable where appropriate)
- `tenant` FK (optional)
- `role` / `purpose` choice fields where relevant

Responsibilities:

- shared naming / human display
- standard feature enablement
- docs URL override
- audit/event-rule compatibility

### `ScopedDesignModel(PowerPlantModel)`

Adds deployment scoping:

- `power_system` FK
- `power_domain` FK nullable
- `redundancy_group` FK nullable
- `design_instance` FK nullable

Use this for objects that belong to a specific plant/system instance.

---

## 5.3 Top-level organizational models

### `PowerSystem`

Represents the top-level electrical system for a site, campus, building, hall, or another operator-defined scope.

Key fields:

- `scope_type` (`campus`, `building`, `hall`, `room`, `custom`)
- `upstream_supply_type` (`ac`, `dc`, `mixed`)
- `nominal_distribution_voltage`
- `frequency_hz`
- `is_template_derived`
- `design_state` (`planned`, `build-ready`, `active`, `decommissioning`)

Relationships:

- one-to-many with domains, nodes, segments, templates, validation summaries

### `PowerDomain`

Logical supply domain such as `A`, `B`, `Utility-A`, `UPS-B`, `Busway-West`, `DC-Bus-1`.

Key fields:

- `code`
- `kind` (`primary`, `redundant`, `maintenance`, `catcher`, `dc_bus`, `custom`)
- `color`
- `priority`
- `failure_isolation_depth`

Purpose:

- encode supply-separation and redundancy semantics independent of physical placement

### `RedundancyGroup`

Groups domains and/or downstream objects under a redundancy contract.

Key fields:

- `topology_type` (`none`, `n_plus_1`, `2n`, `2n_plus_1`, `distributed`, `catcher`, `custom`)
- `min_distinct_paths`
- `requires_domain_isolation`
- `notes_on_failover`

Purpose:

- gives validators something explicit to enforce

### `DesignInstance`

Represents a concrete instantiation of a template into a site/hall/row set.

Key fields:

- `template` FK
- `instantiation_run_id`
- `scope_summary`
- `version`
- `is_frozen`

Purpose:

- stable anchor for “this hall was stamped from template X version Y”

---

## 5.4 Graph backbone models

### `ElectricalNode`

This is the heart of the plugin.

Use **one concrete shared node model** rather than creating a totally separate topological structure for each equipment family.

Key fields:

- `power_system` FK
- `node_kind` choice
- `equipment_role` choice
- `manufacturer`
- `model`
- `serial`
- `asset_tag`
- `install_state`
- `topology_state`
- `site`, `location`
- `parent_node` nullable FK for enclosure/container relationships only
- `rated_input_voltage_min`
- `rated_input_voltage_max`
- `rated_output_voltage_min`
- `rated_output_voltage_max`
- `frequency_hz`
- `phase_mode` (`1ph`, `3ph`, `dc`, `mixed`)
- `pole_count`
- `installed_capacity_kw`
- `usable_capacity_kw`
- `derating_factor`
- `reserve_margin_pct`
- `telemetry_source_ref`

Recommended `node_kind` values:

- `utility_service`
- `generator`
- `paralleling_gear`
- `mv_switchgear`
- `lv_switchboard`
- `transformer`
- `ats`
- `sts`
- `maintenance_bypass`
- `ups`
- `battery_system`
- `bess`
- `rectifier`
- `inverter`
- `pdu`
- `rpp`
- `panelboard`
- `busway_run`
- `tap_off_box`
- `rack_circuit_terminator`
- `rack_pdu`
- `dc_distribution_panel`
- `custom`

Design note:

- `ElectricalNode` stores the common topology/inventory contract.
- Type-specific detail models hang off it one-to-one where needed.

### `ElectricalTerminal`

Named electrical endpoints on a node.

Key fields:

- `node` FK
- `name`
- `terminal_role` (`line`, `load`, `bypass`, `tie`, `battery`, `tap`, `branch`, `output`, `input`, `neutral`, `ground`, `custom`)
- `direction` (`source`, `sink`, `bidirectional`)
- `supply_type` (`ac`, `dc`, `mixed`)
- `voltage_nominal`
- `amperage_rating`
- `phase_designation`
- `pole_designation`
- `connector_type`
- `is_protected`
- `is_switchable`
- `is_monitored`
- `position_index`

Constraints:

- unique terminal name per node
- validator ensures terminal compatibility with node kind

### `ElectricalSegment`

Connects two terminals with electrical semantics.

Key fields:

- `power_system` FK
- `from_terminal` FK
- `to_terminal` FK
- `segment_kind` (`feeder`, `branch_circuit`, `busway_span`, `tap_connection`, `internal_tie`, `whip`, `rack_feed`, `dc_link`, `custom`)
- `path_state` (`candidate`, `planned`, `active`, `retired`)
- `length_m`
- `conductor_material`
- `conductor_count`
- `awg_or_mm2`
- `insulation_type`
- `breaker_size_a`
- `voltage_nominal`
- `ampacity_a`
- `derated_ampacity_a`
- `power_domain` FK nullable
- `protection_element` FK nullable
- `upstream_node` cached nullable FK
- `downstream_node` cached nullable FK

Constraints:

- no self-loop unless explicitly allowed for special internal ties
- no duplicate active segment between identical terminal pairs unless allowed by kind

### `PathSnapshot`

Materialized view / denormalized cache of derived source-to-boundary paths.

Key fields:

- `boundary_type`
- `boundary_id`
- `source_node` FK
- `path_hash`
- `domain_count`
- `hop_count`
- `total_reserved_kw`
- `is_redundancy_compliant`
- `last_calculated`

Purpose:

- accelerate UI validation pages and rack/device rollups

---

## 5.5 Type-specific detail models

Use these only where shared `ElectricalNode` fields are insufficient.

### `TransformerDetail`

- `node` O2O
- `primary_voltage`
- `secondary_voltage`
- `vector_group`
- `kva_rating`
- `impedance_pct`
- `cooling_type`

### `UPSDetail`

- `node` O2O
- `ups_topology` (`double_conversion`, `line_interactive`, `eco_mode`, `rotary`, `custom`)
- `battery_autonomy_minutes`
- `module_count`
- `module_rating_kw`
- `parallel_group_id`
- `maintenance_bypass_present`

### `TransferSwitchDetail`

Applicable to ATS and STS.

- `node` O2O
- `transfer_type` (`automatic`, `static`, `manual`)
- `source_preference`
- `open_transition`
- `closed_transition`
- `max_transfer_time_ms`

### `BuswayRunDetail`

- `node` O2O
- `run_identifier`
- `orientation`
- `start_location_ref`
- `end_location_ref`
- `tap_slot_count`
- `tap_spacing_mm`

### `TapOffBoxDetail`

- `node` O2O
- `busway_run` FK
- `slot_position`
- `tap_rating_a`
- `phases_present`

### `PanelDetail`

For panelboards, RPPs, PDUs where branch-position semantics matter.

- `node` O2O
- `circuit_position_count`
- `pole_layout`
- `main_breaker_rating_a`
- `distribution_style`

### `EnergyStorageDetail`

For battery plants / BESS.

- `node` O2O
- `storage_type`
- `energy_kwh`
- `discharge_kw`
- `charge_kw`
- `autonomy_minutes`
- `chemistry`

---

## 5.6 Protection and capacity models

### `ProtectionElement`

Represents breakers, fuses, relays, trip units, and related protective semantics.

Key fields:

- `name`
- `element_type` (`breaker`, `fuse`, `relay`, `electronic_trip`, `custom`)
- `trip_rating_a`
- `frame_rating_a`
- `interrupt_rating_ka`
- `curve_family`
- `selective_coordination_group`
- `ground_fault_enabled`
- `short_time_enabled`
- `long_time_enabled`
- `instantaneous_enabled`
- `attached_node` nullable FK
- `attached_segment` nullable FK

### `CapacityReservation`

Tracks reserved capacity for logical consumers before every physical device path is known.

Key fields:

- `power_system` FK
- `consumer_type` (`rack`, `rack_group`, `device`, `zone`, `template_slot`, `custom`)
- `consumer_object_type`
- `consumer_object_id`
- `requested_kw`
- `reserved_kw`
- `committed_kw`
- `diversity_factor`
- `power_domain` nullable FK

### `LoadProfile`

Optional abstraction for design-time expected draw.

Key fields:

- `name`
- `profile_type` (`steady`, `burst`, `training_cluster`, `storage`, `networking`, `custom`)
- `typical_kw`
- `peak_kw`
- `power_factor`
- `notes`

---

## 5.7 Rack/device boundary models

These are crucial. They prevent the plugin from fighting NetBox core.

### `RackDeliveryPoint`

Represents the plugin-side endpoint where facility distribution lands at a rack boundary.

Key fields:

- `rack` FK
- `name`
- `delivery_type` (`whip`, `tap_off`, `busway_drop`, `rack_feed`, `dc_feed`)
- `power_domain` FK
- `input_terminal` FK to `ElectricalTerminal`
- `expected_feed_count`

### `NetBoxPowerFeedBinding`

Maps plugin rack/facility delivery to NetBox `dcim.PowerFeed`.

Key fields:

- `rack_delivery_point` FK
- `power_feed` FK to NetBox model
- `binding_role` (`primary`, `redundant`, `maintenance`, `aux`)
- `is_authoritative_from_plugin`

### `NetBoxPowerPortBinding`

Maps a plugin boundary object to a device/module power port.

Key fields:

- `rack_delivery_point` or `segment` FK
- `power_port` FK to NetBox model
- `binding_path_role`
- `priority`

### `NetBoxPowerOutletBinding`

Maps plugin-side rack PDU / downstream panel outlet abstraction to NetBox `PowerOutlet`.

Key fields:

- `source_terminal` or `source_node` FK
- `power_outlet` FK to NetBox model
- `branch_circuit_label`

Design note:

- These bindings should be optional in early modeling phases and become required only when a design moves toward detailed rack/device realization.

---

## 5.8 Template and instantiation models

### `PowerArchitectureTemplate`

Represents a reusable electrical reference design.

Key fields:

- `name`
- `version`
- `template_scope` (`site`, `building`, `hall`, `row`, `rack_zone`)
- `description`
- `supports_ac`
- `supports_dc`
- `default_redundancy_topology`
- `is_published`

### `TemplateNode`

Template-time version of `ElectricalNode`.

### `TemplateTerminal`

Template-time version of `ElectricalTerminal`.

### `TemplateSegment`

Template-time version of `ElectricalSegment`.

### `TemplatePlacementRule`

Defines how a template expands spatially.

Key fields:

- `template` FK
- `placement_axis` (`hall`, `row`, `rack_range`, `electrical_room`, `busway_zone`)
- `selector_expression`
- `multiplier`
- `naming_policy` FK

### `NamingPolicy`

Deterministic naming convention for instantiated objects.

Key fields:

- `scope_type`
- `object_kind`
- `pattern`
- `sequence_strategy`
- `collision_policy`

### `InstantiationRun`

Tracks a wizard/job execution.

Key fields:

- `template` FK
- `requested_by`
- `scope_json`
- `mode` (`dry_run`, `apply`, `rollback`)
- `status`
- `summary_json`
- `diff_json`
- `job_id`

### `InstantiationArtifact`

Links created objects back to the run that produced them.

Key fields:

- `instantiation_run` FK
- `object_type`
- `object_id`
- `artifact_role`
- `created_name`

---

## 5.9 Validation and reporting models

### `ValidationRule`

Declarative or semi-declarative rule definitions.

Key fields:

- `name`
- `rule_family` (`capacity`, `topology`, `redundancy`, `compatibility`, `placement`, `protection`, `naming`)
- `severity`
- `scope_kind`
- `expression` or `engine_key`
- `is_enabled`

### `ValidationResult`

Stores violations and warnings.

Key fields:

- `rule` FK
- `power_system` FK
- `object_type`
- `object_id`
- `severity`
- `message`
- `details_json`
- `status` (`open`, `acknowledged`, `resolved`, `suppressed`)
- `first_seen`
- `last_seen`

### `ScopeSummary`

Denormalized summaries for hall/row/rack views.

Key fields:

- `scope_type`
- `scope_object_type`
- `scope_object_id`
- `installed_kw`
- `reserved_kw`
- `committed_kw`
- `available_kw`
- `primary_path_count`
- `redundant_path_count`
- `open_violation_count`
- `last_calculated`

---

## 6. Relationship Strategy

## 6.1 Relationship rules

Use explicit relationships instead of trying to infer everything from names.

Important relationship patterns:

- `PowerSystem -> PowerDomain`
- `PowerSystem -> ElectricalNode`
- `ElectricalNode -> ElectricalTerminal`
- `ElectricalTerminal -> ElectricalSegment`
- `ElectricalNode -> detail model` (O2O where needed)
- `ElectricalNode / Segment -> ProtectionElement`
- `Template -> TemplateNode / TemplateTerminal / TemplateSegment`
- `DesignInstance -> instantiated nodes/segments`
- `RackDeliveryPoint -> NetBox bindings`

## 6.2 Generic relations

Use `object_type` + `object_id` only where polymorphism is truly necessary, such as:

- `CapacityReservation`
- `ValidationResult`
- `InstantiationArtifact`
- some summary/report models

Avoid overusing GFKs in the hot topology path.

---

## 7. Choice Sets

Create stable `ChoiceSet` classes for every field with meaningful enumerations.

Priority enums:

- `PowerSupplyTypeChoices`
- `NodeKindChoices`
- `TerminalRoleChoices`
- `SegmentKindChoices`
- `RedundancyTopologyChoices`
- `ValidationSeverityChoices`
- `TemplateScopeChoices`
- `DesignStateChoices`

This will keep the UI, filters, serializers, and validators aligned.

---

## 8. Service Layer Design

## 8.1 `graph.py`

Responsibilities:

- build adjacency maps from nodes, terminals, and segments
- provide fast upstream/downstream traversal
- detect cycles / isolated nodes
- compute path candidates

Primary service objects:

- `PowerGraphBuilder`
- `PowerGraphSnapshot`
- `TraversalContext`

## 8.2 `paths.py`

Responsibilities:

- enumerate source-to-boundary paths
- calculate independent path sets
- classify domain diversity
- identify single points of failure

Primary service objects:

- `PathResolver`
- `IndependentPathAnalyzer`

## 8.3 `capacity.py`

Responsibilities:

- roll up installed / usable / reserved / committed capacity
- apply derating and reserve margins
- compute remaining capacity by node/domain/scope
- estimate stranded capacity

Primary service objects:

- `CapacityRollupService`
- `ReservationAllocator`

## 8.4 `validation.py`

Responsibilities:

- enforce compatibility rules
- enforce redundancy contracts
- enforce protection sanity rules
- enforce naming and template conformance

Primary service objects:

- `ValidationEngine`
- `RuleRegistry`
- `ValidationScopeRunner`

## 8.5 `instantiate.py`

Responsibilities:

- expand a template into a concrete deployment plan
- preview dry-run diffs
- apply bulk create/update operations
- create traceability links back to the instantiation run

Primary service objects:

- `TemplateExpander`
- `InstantiationPlanner`
- `InstantiationExecutor`

## 8.6 `naming.py`

Responsibilities:

- deterministic object naming
- collision avoidance
- site/hall/row/rack token expansion

## 8.7 `importers.py`

Responsibilities:

- support import from CSV/JSON/YAML
- map row-oriented import files into template and topology objects
- validate imports before persistence

## 8.8 `diff.py`

Responsibilities:

- compare desired template-derived state with current instantiated state
- produce human-readable change sets
- support safe re-apply operations

---

## 9. UI / UX Plan

## 9.1 Navigation structure

Suggested plugin menu groups:

```text
Power Plant
  Systems
    Power Systems
    Power Domains
    Redundancy Groups

  Topology
    Electrical Nodes
    Electrical Segments
    Protection Elements
    Rack Delivery Points

  Templates
    Architecture Templates
    Naming Policies
    Instantiation Runs

  Operations
    Validation Results
    Scope Summaries
    Recalculation Jobs
```

## 9.2 Standard object views

For most models, provide the normal NetBox object set:

- list
- detail
- add/edit
- delete
- bulk import
- bulk edit
- bulk delete
- filter/search
- REST endpoint

## 9.3 Purpose-built views

### System Overview page

Shows:

- domains
- installed/usable capacity
- open validation issues
- template origin
- top-level source objects

### Topology Explorer page

A graph-aware page, not just a table.

Capabilities:

- start from any node
- walk upstream/downstream
- highlight domains
- show derived paths to rack boundary
- collapse repeated template-derived subtrees

### Rack Delivery view

Per rack:

- plugin-side delivery points
- bound NetBox power feeds
- bound rack PDUs / ports / outlets
- A/B path status
- unresolved bindings

### Template Wizard

Steps:

1. choose template
2. select scope
3. define hall/row/rack ranges
4. preview object counts and names
5. run dry-run validation
6. apply as background job

### Validation Console

Shows:

- violations by severity
- violations by scope
- “show me every rack missing an independent B path” style queries
- suppress / acknowledge workflow

## 9.4 Editing ergonomics

Avoid making users manually create every terminal or segment.

Provide:

- inline child editing for terminals on node forms
- generated terminals based on node kind templates
- bulk “populate branch circuits 1-42” actions
- busway tap-off placement wizard
- rack-range creation workflow

---

## 10. API Plan

## 10.1 REST API

Create serializers and viewsets for all first-class models.

Priority REST resources:

- `/api/plugins/powerplant/power-systems/`
- `/api/plugins/powerplant/power-domains/`
- `/api/plugins/powerplant/electrical-nodes/`
- `/api/plugins/powerplant/electrical-terminals/`
- `/api/plugins/powerplant/electrical-segments/`
- `/api/plugins/powerplant/protection-elements/`
- `/api/plugins/powerplant/rack-delivery-points/`
- `/api/plugins/powerplant/templates/`
- `/api/plugins/powerplant/instantiation-runs/`
- `/api/plugins/powerplant/validation-results/`

## 10.2 Custom action endpoints

Add custom endpoints for high-value operations:

- `POST /templates/{id}/dry-run/`
- `POST /templates/{id}/instantiate/`
- `POST /power-systems/{id}/recalculate/`
- `GET /power-systems/{id}/topology/`
- `GET /racks/{id}/power-delivery-summary/`
- `GET /nodes/{id}/paths/`

## 10.3 GraphQL

Optional for phase 2.

Recommendation:

- expose GraphQL only after path summaries and filter semantics stabilize

---

## 11. Background Jobs

Use NetBox background jobs for any action that can explode into thousands of objects or expensive graph traversals.

Initial jobs:

- `InstantiateTemplateJob`
- `RecalculateScopeSummariesJob`
- `ValidateScopeJob`
- `ImportPowerDesignJob`
- `RebindRackBoundaryJob`

Job design requirements:

- dry-run first for template expansion
- verbose progress logs
- persistent summary artifacts
- deterministic retry behavior
- rollback or compensating-action support where feasible

---

## 12. Import / Bulk Population Workflows

## 12.1 Supported import modes

### Mode A: reference-template creation

Input:

- JSON or YAML describing a reusable architecture

Use when:

- creating canonical designs for future halls or sites

### Mode B: concrete deployment stamping

Input:

- wizard data or CSV/JSON specifying site/hall/row/rack ranges and naming variables

Use when:

- creating real inventory in bulk

### Mode C: brownfield reconciliation

Input:

- CSV/JSON inventory extracts from existing facility documentation

Use when:

- loading an existing data center with partial fidelity first, then refining it

## 12.2 Import validation stages

Every bulk workflow should go through:

1. schema validation
2. semantic validation
3. naming preview
4. object-count preview
5. conflict detection
6. dry-run diff
7. apply

---

## 13. Validation Rules for v1

Implement these first because they deliver immediate value.

### Topology rules

- no orphan terminals on active nodes
- no active segments into missing terminals
- no invalid directionality pairings
- no impossible source-less rack delivery point

### Compatibility rules

- supply-type mismatch
- voltage incompatibility
- phase/pole incompatibility
- incompatible segment/node pairings

### Redundancy rules

- required distinct path count not met
- A and B paths collapse to same domain upstream
- ATS/STS inputs not sufficiently isolated
- rack marked redundant but only one valid path exists

### Capacity rules

- reserved > usable
- committed > installed
- downstream branch breaker > upstream protective envelope
- tap-off demand exceeds busway capacity policy

### Consistency rules

- template-derived object drift from naming policy
- missing required NetBox boundary bindings when detailed design state is active
- invalid status combinations across connected objects

---

## 14. NetBox Core Integration Strategy

## 14.1 What stays in core NetBox

Use native NetBox models for:

- `Site`
- `Location`
- `Rack`
- `Device`
- `Module`
- `PowerFeed`
- `PowerPort`
- `PowerOutlet`
- `Cable`

## 14.2 What the plugin adds

The plugin adds:

- upstream/facility-side plant objects
- richer electrical topology semantics
- redundancy-aware validation
- template instantiation at hall/row/rack scale
- rack/device boundary binding models

## 14.3 Config context / downstream automation

Phase 2 recommendation:

- publish simplified rack/device-facing power summaries into config context or derived API endpoints for downstream automation consumers

Examples:

- rack A/B delivery labels
- upstream domain names
- usable reserved power per rack
- boundary path identifiers

---

## 15. Search, Filter, and Reporting Plan

## 15.1 Search indexing

Add global search indexes for:

- power systems
- electrical nodes
- rack delivery points
- templates
- validation results

## 15.2 Filter priorities

Every primary model should support filtering by:

- site
- location
- power system
- power domain
- redundancy group
- status
- design instance
- template origin

## 15.3 Reporting pages

Initial reports:

- capacity by hall/domain
- racks missing redundant feed
- orphaned rack delivery points
- segments without protection metadata
- template instantiations with drift
- brownfield objects missing placement metadata

---

## 16. Permissions and Multi-Team Operation

Define permission groups so facility, capacity-planning, and network/DCIM users can coexist.

Suggested role partition:

- **Power design admin**: full model/template authority
- **Capacity planner**: reservation and reporting authority
- **DCIM operator**: rack boundary and binding authority
- **Read-only consumers**: topology/report visibility only

Guardrails:

- restrict template publishing
- restrict mass instantiation
- require explicit permission for binding overrides against core NetBox objects

---

## 17. Migration / Rollout Strategy

## Phase 0: groundwork completed

- plugin skeleton
- base choices and abstract models
- navigation scaffolding
- REST/API framework

Status:

- completed in the repository scaffold and dev environment
- unique devrun compose project/container naming and unique host port bindings are in place
- editable install and focused plugin test lane are working

## Phase 1A: organizational backbone completed

- `PowerSystem`, `PowerDomain`, `RedundancyGroup`
- standard CRUD + API
- first system-overview page
- focused model/view/API tests

Status:

- completed for the first three organizational models
- intentionally kept flat in single-module surfaces pending higher model count

## Phase 1B: topology MVP completed

- `ElectricalNode`, `ElectricalTerminal`, `ElectricalSegment`
- initial validation engine

Status:

- topology backbone models have been added in the existing flat module layout
- an initial validation service now covers terminal supply compatibility and basic segment topology checks
- a first graph traversal service now builds active-topology snapshots, upstream/downstream reachability, isolated-node detection, orphan-terminal detection, and directed-cycle detection
- graph-based topology checks now report missing terminals, orphan terminals, isolated nodes, and directed cycles for active topologies
- redundancy checks now evaluate derived rack-boundary delivery against redundancy-group path-count and domain-isolation requirements
- one rack-delivery summary page now reports derived rack-boundary endpoints, upstream domains, and redundancy posture per power system
- standard CRUD views, routes, navigation entries, detail templates, filtersets, filter forms, tables, and REST endpoints have been added for the topology models
- focused model, view, API, graph, and validation tests are in place and included in the fast test lane
- phase 1B deliverables are now complete

## Phase 2: facility detail and rack boundary

- type-specific detail models
- `ProtectionElement`
- `RackDeliveryPoint`
- NetBox bindings
- rack summary views

## Phase 3: templates and scale workflows

- `PowerArchitectureTemplate`
- placement rules
- naming policies
- dry-run diff
- instantiation jobs

## Phase 4: reporting and drift control

- path snapshots
- scope summaries
- validation console
- drift detection against template-derived objects

## Phase 5: integration polish

- config-context style exports
- telemetry bindings
- optional UI-component enhancements

---

## 18. Testing Strategy

### Unit tests

Focus on:

- path traversal
- redundancy calculations
- capacity math
- validator behavior
- naming policy expansion

### Integration tests

Focus on:

- template dry-run and apply
- bulk import
- binding to native NetBox power objects
- delete protection / cascade behavior
- permission boundaries

### Fixture strategy

Maintain canonical test fixtures for:

- simple single-feed room
- 2N hall with dual UPS domains
- overhead busway with tap-offs and rack drops
- AI rack zone with high-density dual-path delivery
- brownfield import with partial data quality

---

## 19. Risks and Design Traps

### Trap 1: too many bespoke equipment tables

If every equipment family becomes its own totally separate topology model, traversal and validation will become miserable.

Mitigation:

- keep a unified node/terminal/segment backbone

### Trap 2: forcing too much fidelity too early

If the plugin demands full breaker-trip and relay-study detail on day one, adoption will stall.

Mitigation:

- allow progressive enrichment from high-level topology to detailed implementation

### Trap 3: conflating physical cable with electrical path semantics

A facility feeder is not just a generic “cable object.”

Mitigation:

- use plugin segments for plant semantics and bind to NetBox cable/feed objects at the rack/device boundary where appropriate

### Trap 4: artisanal data entry

No one will hand-click a hall-sized design into existence.

Mitigation:

- prioritize templates, wizards, imports, and background jobs from the start

### Trap 5: no traceability from template to deployed state

Without provenance, drift becomes impossible to reason about.

Mitigation:

- every template-derived object must be traceable through `DesignInstance` / `InstantiationRun`

---

## 20. Recommended Initial Django Model Build Order

Implement in this order:

1. `PowerSystem` completed
2. `PowerDomain` completed
3. `RedundancyGroup` completed
4. `ElectricalNode`
5. `ElectricalTerminal`
6. `ElectricalSegment`
7. `ProtectionElement`
8. `RackDeliveryPoint`
9. `NetBoxPowerFeedBinding`
10. `NetBoxPowerPortBinding`
11. `PowerArchitectureTemplate`
12. `TemplateNode`
13. `TemplateTerminal`
14. `TemplateSegment`
15. `TemplatePlacementRule`
16. `NamingPolicy`
17. `InstantiationRun`
18. `InstantiationArtifact`
19. `ValidationRule`
20. `ValidationResult`
21. `ScopeSummary`
22. `PathSnapshot`

This sequence gives usable topology early, then boundary integration, then scale workflows, then operational reporting.

Current progress note:

- the first three organizational models now exist with migrations, list/detail/add/edit/delete views, REST serializers/viewsets, plugin navigation entries, and a system overview page

---

## 21. Recommended Initial Deliverables

### Milestone 1A completed

Completed deliverables:

- Django model skeletons for `PowerSystem`, `PowerDomain`, and `RedundancyGroup`
- `ChoiceSet` definitions for the first organizational slice
- migrations for the initial slice
- list/detail/add/edit/delete views for the first three models
- filtersets and tables for the first three models
- REST serializers/viewsets for the first three models
- one system-overview page
- focused model/view/API tests covering the delivered slice

### Milestone 1B completed

Completed so far in this milestone:

- Django model skeletons for `ElectricalNode`, `ElectricalTerminal`, and `ElectricalSegment`
- supporting `ChoiceSet` definitions and migrations for the topology backbone
- one validation service for basic terminal and segment consistency rules
- one service module for graph traversal across the active topology backbone
- expanded topology validation coverage for missing terminals, orphan terminals, isolated nodes, and directed cycles
- expanded redundancy validation coverage for rack-boundary delivery path count and domain isolation
- standard list/detail/add/edit/delete views for the topology backbone
- filtersets and tables for the topology backbone
- REST serializers/viewsets for the topology backbone
- one rack-delivery summary page for derived rack-boundary coverage and redundancy posture
- focused model/view/API/graph/validation tests covering the delivered topology slice

That follow-on milestone will move the plugin from organizational scoping into actual facility-topology modeling while keeping the first delivered slice stable.

---

## 22. Bottom Line

The plugin should be built as a **facility-grade electrical graph plus a template-instantiation engine**, with NetBox core remaining the source of truth for rack/device power endpoints and physical DCIM placement.

That combination gives you three things at once:

- fidelity high enough to represent real modern power distribution;
- operational workflows that scale beyond one beautiful pilot hall;
- an integration boundary that fits naturally inside NetBox instead of fighting it.
