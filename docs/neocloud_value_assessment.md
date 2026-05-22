# `netbox_power_plant` — Neocloud Value Assessment

> Branch assessed: `copilot/add-support-for-netbox-4-2-3`
> Prepared: May 2026

---

## What the Plugin Is and What Branch Is Current

The active branch (`copilot/add-support-for-netbox-4-2-3`) extends the original `main` commit with NetBox 4.2 compatibility and a substantially more complete model layer. The plugin's core thesis is correct and ambitious: it replaces NetBox's native `PowerPanel/PowerFeed/PowerOutlet` model (which is too shallow for real facility power engineering) with a proper **typed electrical graph** — nodes, terminals, segments — plus explicit domain/redundancy semantics, template-driven architecture stamping, and a plugin-native spatial placement system that has no dependency on `netbox_floorplan`.

---

## What Is Currently Implemented and Working

The plugin has a surprisingly complete model layer for its age:

| Layer | What exists |
|---|---|
| **Topology graph** | `ElectricalNode` (28 `node_kind` values), `ElectricalTerminal`, `ElectricalSegment` with full AC/DC/supply-type validation |
| **Redundancy semantics** | `PowerDomain` (A/B/UPS-A/Busway-West), `RedundancyGroup` with topology type and minimum distinct-path enforcement |
| **Template stamping** | `PowerArchitectureTemplate`, `TemplateNode`, `TemplateTerminal`, `TemplateSegment`, `TemplatePlacementRule`, `InstantiationRun`, `InstantiationArtifact` |
| **Validation** | `PowerValidationRun`, `PowerFinding` with fingerprinting; `run_topology_checks()` covers missing terminals, orphan terminals, isolated nodes, cycle detection, and redundancy path compliance |
| **Rack/device handoff** | `PowerHandoffPoint` → `dcim.PowerPort`; `InternalPowerBus`/`InternalPowerBusAttachment` for in-rack bus attachments |
| **Spatial placement** | `SpatialFrame`, `SpatialPlacement` (physical/schematic/logical/inferred), fully independent of `netbox_floorplan` |
| **Source provenance** | `PlantSourceDocument`, `PlantSourceSheet`, `PlantSourceLayer`, `PlantProvenance` for drawing/workbook traceability |
| **Graph services** | `PowerGraphSnapshot` (BFS upstream/downstream traversal, isolated node detection, cycle detection), `build_power_handoff_summary()` with redundancy compliance assessment |
| **Layout service** | `build_power_system_layout_view()` with delivery overlays mapped onto spatial placements |

The foundational choices — graph over FK-chains, explicit domain objects, template-based stamping, no floorplan dependency — are the right ones for a neocloud.

---

## What Is Not Yet Implemented (and Costs the Most Value)

Several high-value service layers described in the proposal are modeled but not yet wired:

**1. Template instantiation execution engine.** `InstantiationRun` and `InstantiationArtifact` exist as the provenance layer, but there is no service that actually reads `TemplateNode`/`TemplateTerminal`/`TemplateSegment` rows and creates `ElectricalNode`, `ElectricalTerminal`, `ElectricalSegment` rows. The dry-run flag on `InstantiationRun` is inert. This is the most blocking gap: without a working stamp executor, the entire template library is architectural scaffolding with no execution path.

**2. Capacity rollup service.** `ElectricalNode` carries `installed_capacity_kw`, `usable_capacity_kw`, `derating_factor`, and `reserve_margin_pct`, but there is no service that walks the upstream graph and computes available capacity at any node or at the system level. A neocloud building at 30–100 MW per hall needs to answer "how much more can I add to hall-A before the upstream switchboard is full?" from NetBox, not from a spreadsheet.

**3. Maintenance impact (blast-radius) service.** There is no service that answers "if I take this UPS offline, which racks lose power and do any of those racks lose their last redundant path?" This is the power equivalent of the `netbox_multiplanar_fabrics` blast-radius report and is the most operationally critical missing piece.

**4. `PathSnapshot` materialized path cache.** The proposal describes a denormalized snapshot table for source-to-boundary path tracing. Without it, every redundancy compliance check triggers a full BFS traversal. At 2,000+ rack circuits per hall this will be noticeably slow. The graph services are correct; they just need a caching layer.

**5. Type-specific detail models.** `TransformerDetail`, `UPSDetail`, `GeneratorDetail`, `TransferSwitchDetail` are described in the proposal but not implemented. For EPMS integration and for making audit findings actionable, the `attributes` JSON bag on `ElectricalNode` is insufficient.

**6. REST API mutations.** The API surface is read-only. There are no endpoints for triggering instantiation runs, starting validation runs, or recording finding state transitions. External automation (GitOps pipelines, DCIM sync tools, capacity planning scripts) cannot drive the plugin without write endpoints.

**7. GraphQL surface.** Described as deferred in the proposal. Needed for complex multi-hop capacity and redundancy queries from external planners.

**8. Capacity reservation / allocation model.** There is no mechanism to reserve capacity ahead of hardware delivery — critical for a growth phase where racks are being allocated to tenants before physical servers arrive.

---

## Strategic Recommendations to Maximize Neocloud Value

### 1. Ship the Template Stamp Executor First

This is the single highest-leverage item. The architecture template layer is well-designed and the `InstantiationRun`/`InstantiationArtifact` provenance model is already in place. The executor needs to:

- Resolve `TemplateNode.name_format` and `slug_format` against a stamp context (site, location, power_system, counter variables).
- Create or update `ElectricalNode`, `ElectricalTerminal`, `ElectricalSegment`, and `PowerHandoffPoint` rows using `TemplateNode.key` as the idempotency key, stored in `InstantiationArtifact.template_key`.
- Respect `TemplateNode.parent_key` to wire parent/child node relationships.
- Apply `TemplatePlacementRule` coordinates to `ElectricalNodePlacement` rows.
- Support a dry-run mode that populates `InstantiationArtifact` rows with `action=create/update/skip` and `status=proposed` without writing topology rows.
- Apply only after an explicit confirmation, in a single transaction.

Once this exists, a neocloud facility team can define a standard `2N-UPS-busway-pod` template once and stamp it into every new hall row-by-row in minutes instead of hand-creating hundreds of nodes.

**Built-in reference templates to ship alongside the executor:**

- `ai-pod-2n-ups-busway`: Utility → 2× Generator → ATS → 2× LV Switchboard → 2× UPS bank → Busway run → N× Rack PDU feed (domains A and B)
- `ai-pod-distributed-redundant-ups`: Utility → 2× Generator → Paralleling gear → 2× Transformer → 2× LV Switchboard → 2× UPS → 2× Busway → N× dual-feed Rack PDU
- `high-density-dc-48v`: LV Switchboard → Rectifier → 48V DC Bus → N× Rack DC terminals (for next-gen GB300 / NVL72 direct-DC power trains)

### 2. Add the Capacity Rollup Service

The graph traversal infrastructure is already correct. The service needs to:

- Walk `PowerGraphSnapshot.upstream_node_ids()` from a given `ElectricalNode`.
- At each upstream node, accumulate `usable_capacity_kw` (applying `derating_factor` and `reserve_margin_pct` when present).
- At each segment, accumulate `derated_ampacity_a × voltage_nominal` as the segment's kW rating.
- Return a structured rollup: per-hop available capacity, the first bottleneck node, and a system-level headroom summary.

Expose this as both a service function and a REST endpoint (`GET /api/plugins/power-plant/capacity/rollup/?node_id=123`). For a neocloud capacity-planning workflow, this single endpoint replaces the most common reason operators reach for a spreadsheet instead of NetBox.

### 3. Add the Maintenance Impact / Blast-Radius Service

For each of the following scenarios:

- `node_offline`: an `ElectricalNode` (UPS, ATS, busway run, PDU) is taken out of service.
- `segment_cut`: an `ElectricalSegment` (feeder, branch circuit) is severed.
- `domain_lost`: an entire `PowerDomain` (e.g., domain B) fails.

The service should:

- Use `PowerGraphSnapshot.downstream_node_ids()` from the affected node.
- Find all `PowerHandoffPoint` rows in the downstream set.
- Group by `PowerPort.device.rack` to produce a rack-level impact map.
- Cross-reference `RedundancyGroup` compliance: identify which racks lose all redundant paths (critical) vs. which lose one path but retain another (degraded).
- Return a structured report with severity tiers: `critical` (no remaining path), `degraded` (reduced redundancy), `unaffected`.

Expose this as a non-mutating REST endpoint. This is the tool that lets a neocloud SRE answer "can I pull this UPS for maintenance without killing any active training jobs?" before touching hardware.

### 4. Add Capacity Reservation / Allocation

For hyper-growth operations, racks are allocated to tenants and power is reserved weeks before hardware ships. Add a `CapacityReservation` model with:

- `node` FK to `ElectricalNode` (the reserving point, typically a rack PDU feed or branch circuit terminal)
- `reserved_kw` (decimal)
- `tenant` FK to `tenancy.Tenant`
- `rack` FK to `dcim.Rack` (optional)
- `status` (`planned`, `confirmed`, `active`, `released`)
- `valid_from`, `valid_until` (for time-bounded reservations)
- `notes`

The capacity rollup service should subtract active reservations from available headroom at each node. This makes NetBox the single authoritative source for "how much power capacity is already committed in hall-C" — eliminating the parallel spreadsheet that every DC ops team otherwise maintains.

### 5. Add Type-Specific Detail Models for AI Cluster Equipment

The `attributes` JSON bag is too loose for audit findings to be actionable and for EPMS/BMS integration. Implement one-to-one detail models for the equipment types most common in AI data centers:

- **`UPSDetail`**: `ups_topology` (double-conversion, eco-mode), `battery_autonomy_minutes`, `module_count`, `module_rating_kw`, `parallel_group_id`, `maintenance_bypass_present`. AI clusters run double-conversion UPS almost exclusively; autonomy and parallel group membership are critical for maintenance scheduling.
- **`GeneratorDetail`**: `fuel_type` (diesel, natural gas, HVO), `runtime_at_full_load_hours`, `cooling_type`, `ats_group_id`, `automatic_transfer_time_ms`. Generator fleet coordination matters at large scale.
- **`TransformerDetail`**: `primary_kv`, `secondary_kv`, `kva_rating`, `vector_group`, `impedance_pct`, `cooling_type`. Transformers are long-lead items; having their specs in NetBox saves weeks when replacements are needed.
- **`BESSDetail`**: `technology` (Li-ion, flow), `energy_capacity_kwh`, `peak_power_kw`, `charge_rate_kw`, `usable_soc_min_pct`, `usable_soc_max_pct`. BESS integration is growing rapidly in neoclouds for demand response and generator bridge.
- **`BuswaySectionDetail`**: `busway_system_id` (FK to a parent `ElectricalNode` representing the busway run), `section_index`, `rated_ampacity_a`, `plug_count`, `plug_spacing_m`. Busway is the dominant distribution medium for high-density GPU halls.

### 6. Add REST API Mutation Endpoints

The power system is operationally useless without write endpoints for automation:

| Endpoint | Purpose |
|---|---|
| `POST /api/plugins/power-plant/instantiation-runs/` | Create and optionally execute a template instantiation run |
| `POST /api/plugins/power-plant/instantiation-runs/{id}/apply/` | Apply a dry-run to live topology rows |
| `POST /api/plugins/power-plant/validation-runs/` | Start a topology validation run for a power system |
| `POST /api/plugins/power-plant/power-findings/{id}/acknowledge/` | Acknowledge a finding |
| `POST /api/plugins/power-plant/power-findings/{id}/suppress/` | Suppress a finding until a given datetime |
| `POST /api/plugins/power-plant/power-findings/{id}/resolve/` | Mark a finding resolved |
| `GET /api/plugins/power-plant/capacity/rollup/` | Capacity rollup query |
| `POST /api/plugins/power-plant/impact/node-offline/` | Maintenance blast-radius query (non-mutating) |
| `POST /api/plugins/power-plant/impact/domain-lost/` | Domain-failure blast-radius query (non-mutating) |

### 7. Wire the `netbox_multiplanar_fabrics` Cross-Plugin Handoff

For a neocloud using both plugins, the power boundary and the network boundary share the same racks. `PowerHandoffPoint.power_port` and `netbox_multiplanar_fabrics`'s topology endpoints both anchor to `dcim` objects on the same `dcim.Device`. A shared query surface that can answer "which GPU racks in hall-C are at risk from both a power standpoint and a network fabric standpoint if this UPS goes offline?" is a uniquely high-value capability that neither plugin can provide alone. Even a simple NetBox webhook-driven invalidation of `PathSnapshot` caches when `PowerHandoffPoint` rows change would be a meaningful first step.

---

## Priority Summary

| Priority | Item | Why it unlocks the next tier |
|---|---|---|
| 1 | Template stamp executor | Nothing gets stamped at scale without it |
| 2 | Capacity rollup service + REST endpoint | Replaces the spreadsheet; needed before any growth allocation decisions |
| 3 | Maintenance impact / blast-radius service | Pre-maintenance safety gate; same urgency as network blast-radius |
| 4 | REST API mutation endpoints | External automation is blocked without write API |
| 5 | Capacity reservation model | Needed once growth pace exceeds "install hardware then track it" |
| 6 | Type-specific detail models (UPS, Generator, Transformer, BESS, Busway) | Needed for actionable findings and EPMS integration |
| 7 | Built-in AI-cluster power architecture templates | Enables zero-touch stamping of new pods |
| 8 | `netbox_power_plant` × `netbox_multiplanar_fabrics` cross-plugin handoff | Highest combined value; depends on items 1–3 being stable first |
