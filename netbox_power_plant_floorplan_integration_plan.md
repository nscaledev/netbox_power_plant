# NetBox Power Plant Floorplan Integration Plan

## 1. Purpose

This document defines a concrete implementation plan for evolving `netbox_power_plant` so it can leverage the site and location layout capabilities provided by `netbox_floorplan` without collapsing the two plugins into a single concern.

The plan assumes the following starting point is already true:

- `netbox-floorplan-plugin` is installed in the local NetBox 4.5.7 and 4.5.0 virtual environments.
- `netbox_floorplan` is enabled in the baseline NetBox 4.5.7 configuration.
- `netbox_power_plant` already owns the electrical topology graph, rack-delivery summary logic, and redundancy validation behavior.

The goal is to add **layout awareness** to the power-plant plugin while preserving clean boundaries:

- `netbox_floorplan` owns floorplan records, background imagery, and site/location canvas content for racks and unracked devices.
- `netbox_power_plant` owns electrical topology, facility equipment semantics, rack-delivery semantics, and layout-aware power overlays.

---

## 2. Current Constraints

### 2.1 What the floorplan plugin already provides

Based on the current `netbox_floorplan` implementation:

- floorplans are attached to a `Site` or `Location`
- floorplans store canvas content in a JSON field
- the canvas currently understands mapped `Rack` and `Device` objects
- the plugin already exposes Site and Location tabs for viewing floorplans
- the plugin does not model arbitrary power equipment placement as first-class records

### 2.2 What the power-plant plugin already provides

The current `netbox_power_plant` implementation already has:

- `PowerSystem`, `PowerDomain`, and `RedundancyGroup`
- `ElectricalNode`, `ElectricalTerminal`, and `ElectricalSegment`
- graph traversal and topology validation services
- derived rack-delivery summary logic
- redundancy checks based on distinct path count and domain isolation

### 2.3 Architectural implication

The floorplan plugin is a **layout substrate**, not a complete placement model for electrical infrastructure. `netbox_power_plant` therefore needs an adapter and its own overlay/placement layer rather than direct reuse of floorplan canvas JSON as the electrical system of record.

---

## 3. Target Architecture

The target architecture should be split into four layers.

### 3.1 Layer A: authoritative layout substrate

Owned by `netbox_floorplan`:

- floorplan records
- background images
- site/location selection
- canvas state for racks and unracked devices

### 3.2 Layer B: floorplan integration adapter

Owned by `netbox_power_plant.services.floorplan`:

- detect whether `netbox_floorplan` is installed and enabled
- resolve the effective floorplan for a given `PowerSystem`
- read mapped rack/device objects from the linked floorplan canvas
- expose stable typed helpers so the rest of `netbox_power_plant` never depends directly on floorplan canvas structure

### 3.3 Layer C: power overlay and placement model

Owned by `netbox_power_plant`:

- placement bindings between electrical objects and a floorplan context
- overlay metadata for facility equipment not represented as NetBox racks/devices
- rendered overlay payloads for UI views

### 3.4 Layer D: user-facing layout views and validations

Owned by `netbox_power_plant`:

- floorplan-aware power-system views
- rack-delivery overlay views
- placement validation
- redundancy visualization
- operational reporting that combines topology and layout

---

## 4. Design Principles

### 4.1 Do not duplicate floorplan ownership

Do not create a second background-image or floorplan record inside `netbox_power_plant`. Always refer outward to `netbox_floorplan` for the underlying floorplan.

### 4.2 Do not store topology in canvas JSON

Electrical topology must continue to live in `ElectricalNode`, `ElectricalTerminal`, and `ElectricalSegment`. Floorplan overlay coordinates are presentation and placement data only.

### 4.3 Keep plugin coupling narrow

All direct imports of floorplan plugin models should be isolated behind a small adapter/service boundary. This keeps the rest of `netbox_power_plant` clean and makes feature gating easier.

### 4.4 Support graceful degradation

If `netbox_floorplan` is not installed or not enabled in some environment:

- topology logic must continue to work
- power-plant migrations must still be valid
- layout views should be hidden or present a clear unavailable state

### 4.5 Prefer derived read-only views before editing workflows

The first integration step should show value without introducing fragile bidirectional editing. Render floorplan-backed power overlays first, then add editing only after the data boundary is stable.

---

## 5. Recommended Implementation Order

## Phase 0: Environment and compatibility baseline

### Objective

Make the floorplan plugin reliably available in local NetBox environments and establish the compatibility contract.

### Current status

- initial repository documentation for the dependency and fallback contract is complete
- `README.md`, `LOCAL_DEV_SETUP.md`, and `CONTRIBUTING.md` now document the package name `netbox-floorplan-plugin`, the NetBox plugin name `netbox_floorplan`, the expected migration and collectstatic steps, and the graceful-degradation requirement

### Tasks

1. Keep `netbox-floorplan-plugin` installed in the 4.5.7 and 4.5.0 virtual environments.
2. Keep `netbox_floorplan` enabled in the baseline 4.5.7 NetBox configuration.
3. Add a short section to `LOCAL_DEV_SETUP.md` describing the floorplan dependency, expected plugin name, and any migration or collectstatic steps needed when the baseline environment is actually brought up.
4. Add a repository note capturing the plugin dependency and fallback expectation.

### Deliverables

- documented dependency on `netbox_floorplan`
- verified plugin import path in both local NetBox virtual environments
- explicit statement that `netbox_power_plant` degrades cleanly when layout integration is unavailable

### Exit criteria

- local developers can explain where floorplan support comes from and how it is enabled
- the baseline 4.5.7 configuration includes `netbox_floorplan`

---

## Phase 1: Floorplan adapter service

### Objective

Create a small, stable integration layer that isolates `netbox_power_plant` from `netbox_floorplan` implementation details.

### Current status

- initial adapter scaffold is complete in `netbox_power_plant/services/floorplan.py`
- focused tests are in place in `netbox_power_plant/tests/test_floorplan_integration.py`
- the current slice covers feature detection, plugin-enablement checks, location-first then site fallback resolution, and normalized mapped rack/device extraction from floorplan canvas data
- layout views, placement models, and persistence workflows remain pending

### New module

- `netbox_power_plant/services/floorplan.py`

### Responsibilities

1. Detect whether the floorplan plugin can be imported.
2. Resolve the effective floorplan for a `PowerSystem`:
   - prefer `Location` floorplan when `PowerSystem.location` is set
   - otherwise fall back to `Site` floorplan
3. Normalize floorplan data into typed results such as:
   - `FloorplanAvailability`
   - `ResolvedFloorplanContext`
   - `MappedRackReference`
   - `MappedDeviceReference`
4. Parse canvas JSON only inside this service.
5. Provide helper methods such as:
   - `get_floorplan_context_for_power_system(power_system)`
   - `list_mapped_racks(power_system)`
   - `list_mapped_devices(power_system)`
   - `has_floorplan_context(power_system)`

### Key design choices

1. Do not add a direct model foreign key from `PowerSystem` to `netbox_floorplan.Floorplan` in the first pass.
2. Resolve the association from existing `site` and `location` fields unless a later requirement proves that multiple alternative floorplans per scope must be supported.
3. Return typed, serializable Python structures so views and tests can use them without floorplan-model knowledge.

### Deliverables

- floorplan adapter service
- focused unit tests for floorplan availability and floorplan resolution behavior

Completed in this slice:

- `FloorplanAvailability`, `ResolvedFloorplanContext`, `MappedRackReference`, and `MappedDeviceReference` typed results
- `get_floorplan_context_for_power_system()`, `list_mapped_racks()`, `list_mapped_devices()`, and `has_floorplan_context()` helper functions
- lazy import and enablement checks so topology-only behavior remains usable when `netbox_floorplan` is unavailable

### Exit criteria

- the adapter can answer floorplan questions for a `PowerSystem` without any UI dependency
- no code outside the service needs to parse floorplan canvas JSON directly

---

## Phase 2: Placement and binding model split

### Objective

Define where power objects meet layout objects, without overloading floorplan canvas or electrical topology tables.

### Model decisions

#### 2.1 Rack/device boundary binding

Introduce `RackDeliveryPoint` in `netbox_power_plant` as the canonical boundary object for facility power delivered to the IT layout.

Initial fields should include:

- `power_system`
- `electrical_node` or `electrical_terminal` boundary reference
- `rack` nullable FK to `dcim.Rack`
- `device` nullable FK to `dcim.Device`
- `expected_redundancy_group` nullable FK
- `delivery_role` / `feed_label` / operator-facing identifier
- status or design-state fields as needed

Rules:

- at least one of `rack` or `device` must be set
- if `device` is set, it must be compatible with the same site/location scope as the parent system
- this object becomes the stable handoff between electrical design and layout-bound IT endpoints

#### 2.2 Non-rack electrical placement

Introduce a dedicated overlay placement model such as `FloorplanPlacement` or `ElectricalNodePlacement` for facility equipment that is not represented as a NetBox rack or unracked device.

Initial fields should include:

- `power_system`
- `electrical_node`
- resolved placement scope (`site` or `location`)
- x/y coordinates
- optional width/height
- rotation
- optional display metadata like color, icon kind, label mode, z-index

Rules:

- placement rows must stay in the same site/location scope as the parent `PowerSystem`
- a node may have at most one active placement per resolved floorplan context in the first version

### Why this split matters

- `RackDeliveryPoint` models business semantics at the rack boundary
- `ElectricalNodePlacement` models overlay position for facility equipment
- neither one abuses floorplan canvas JSON as the source of truth

### Deliverables

- migrations for the new boundary and placement models
- model validation tests
- basic CRUD or at least admin/API surfaces if needed for early debugging

### Current implementation slice recommendation

Phase 2 should be split into two narrow subphases so schema risk stays low and each slice has an operator-visible outcome.

#### Phase 2A: rack-boundary persistence

Add the first persisted handoff model, `RackDeliveryPoint`, before any free-form overlay placement work.

Recommended initial fields:

- `power_system`
- `electrical_node` nullable FK to `ElectricalNode`
- `electrical_terminal` nullable FK to `ElectricalTerminal`
- `rack` nullable FK to `dcim.Rack`
- `device` nullable FK to `dcim.Device`
- `expected_redundancy_group` nullable FK to `RedundancyGroup`
- `delivery_role`
- `feed_label`
- `design_state`

Validation rules for the first pass:

- exactly one of `rack` or `device` must be set
- at least one of `electrical_node` or `electrical_terminal` must be set
- any referenced electrical object must belong to the same `power_system`
- referenced rack/device scope must match the parent system site, and the location when one is set on the system
- `device` should be restricted to non-rack-mounted or otherwise intentionally boundary-modeled devices if that distinction matters in practice

Operator-visible outcome:

- the existing derived rack-delivery summary can start joining persisted delivery intent to graph-derived delivery posture
- the `PowerSystem` detail and rack-delivery page can distinguish modeled delivery points from merely inferred rack-boundary nodes

#### Phase 2B: facility overlay placement persistence

After rack-boundary persistence is stable, add `ElectricalNodePlacement` for facility equipment overlays.

Recommended initial fields:

- `power_system`
- `electrical_node`
- `site`
- `location` nullable
- `placement_scope_type`
- `x`
- `y`
- `width` nullable
- `height` nullable
- `rotation_degrees`
- `symbol_kind`
- `label_mode`
- `color` nullable
- `z_index`

Validation rules for the first pass:

- placement scope must match the resolved floorplan scope for the parent system
- the node must belong to the same `power_system`
- only one active placement per node per resolved floorplan context
- coordinates must be optional only when the row is explicitly in draft or unplaced state

Operator-visible outcome:

- `PowerSystemLayoutView` can render facility equipment using plugin-owned placement data without writing back into floorplan canvas JSON

### Exit criteria

- `netbox_power_plant` has explicit storage for rack boundary and facility placement concerns

---

## Phase 3: Read-only floorplan-aware layout view

### Objective

Deliver the first operator-visible integration by showing a `PowerSystem` on top of the resolved floorplan.

### New service surface

Add a read-model builder such as:

- `build_power_system_layout_view(power_system)`

This service should combine:

- floorplan context from the adapter service
- rack/device mappings from the floorplan plugin
- `RackDeliveryPoint` information
- `ElectricalNodePlacement` information
- upstream domain and redundancy posture from existing topology services

### New view surface

Add a view such as:

- `PowerSystemLayoutView`

Possible route:

- `/plugins/power-plant/power-systems/<pk>/layout/`

### First-pass UI requirements

1. Show whether a floorplan exists for the `PowerSystem` scope.
2. Render or embed the resolved floorplan.
3. Overlay known facility equipment placements.
4. Overlay rack delivery endpoints.
5. Show power domain colors and redundancy posture.
6. Provide a legend that distinguishes:
   - facility equipment overlays
   - rack delivery points
   - compliant vs noncompliant redundancy coverage

### Important scope constraint

The first pass should be **read-only**. Do not allow drag-and-drop persistence, inline editing, or bidirectional canvas mutation yet.

### Deliverables

- new layout service
- new layout page and template assets
- navigation entry from `PowerSystem` detail
- view tests for layout availability and unavailable states

### Exit criteria

- a user can open a `PowerSystem` and see its topology boundary projected onto the resolved floorplan context

---

## Phase 4: Layout-aware validation and reporting

### Objective

Make floorplan integration operationally useful by validating and reporting on gaps between power topology and physical/layout representation.

### Validation families to add

1. `missing_floorplan_context`
   - a power system requires layout visualization but no site/location floorplan exists
2. `unmapped_rack_delivery_point`
   - a `RackDeliveryPoint` exists but its rack/device is not represented on the resolved floorplan
3. `orphan_floorplan_mapping`
   - a rack/device is mapped in the floorplan but has no matching power delivery object where one is expected
4. `mis_scoped_node_placement`
   - an electrical node placement references the wrong site/location context
5. `redundancy_gap_visible_in_layout`
   - a rack boundary is visible in layout but lacks the required A/B or isolated path coverage

### Reporting additions

1. layout summary card on the `PowerSystem` detail page
2. a small layout-health summary service
3. optional CSV/API export for placement and delivery coverage

### Deliverables

- extended validation service(s)
- tests for layout-aware findings
- visible layout-health summary on the relevant detail pages

### Exit criteria

- layout integration is not just visual; it drives actionable data quality feedback

---

## Phase 5: Controlled editing workflows

### Objective

Add carefully scoped editing only after the read model, placement model, and validation rules are stable.

### Candidate workflows

1. assign `RackDeliveryPoint` to rack or device
2. create and edit `ElectricalNodePlacement`
3. snap overlay positions to floorplan coordinates
4. import bulk placements from CSV or JSON

### Editing constraints

1. Do not mutate `netbox_floorplan` canvas JSON directly from multiple places unless an explicit synchronization contract exists.
2. If power overlays must be rendered inside the existing floorplan canvas, add a single synchronization service that owns all writes.
3. Prefer storing power overlay placement as `netbox_power_plant` data and rendering it in the power-plant UI first.

### Deliverables

- forms and views for placement editing
- placement import workflow if needed
- validation on save for scoping and duplication conflicts

### Exit criteria

- operators can maintain overlay placement without corrupting floorplan data ownership

---

## 6. Detailed Work Breakdown

## Workstream A: Dependency and configuration

### Tasks

1. document floorplan dependency in root docs
2. note baseline plugin enablement rules
3. confirm supported NetBox versions remain aligned with floorplan plugin compatibility

### Risks

- local environments may not have Redis or other supporting services available for baseline `manage.py` checks
- different NetBox installs may want floorplan support optional rather than always enabled

### Mitigation

- keep runtime feature detection in `netbox_power_plant`
- keep architecture resilient to environments where the plugin is installed differently

---

## Workstream B: Service-layer integration

### Current status

- the floorplan adapter service already exists and covers plugin detection, enablement checks, site/location resolution, and mapped rack/device extraction
- the next service-layer work should build layout read models on top of that adapter rather than reopening floorplan-import concerns

### Tasks

1. extend `services/floorplan.py` only where layout-facing typed helpers are still missing
2. add `services/layout.py` to assemble floorplan context, persisted delivery points, placements, and redundancy posture into a single read model
3. add focused service tests for layout read-model assembly and degraded no-floorplan behavior
4. keep floorplan imports lazy and isolated so layout features remain optional

### Risks

- tight import coupling between plugins
- future floorplan canvas schema changes

### Mitigation

- isolate imports behind helper functions
- keep canvas parsing localized and version-tolerant

---

## Workstream C: Data model additions

### Tasks

1. introduce `RackDeliveryPoint`
2. introduce `ElectricalNodePlacement` or equivalent overlay model
3. add migrations and validation logic
4. add REST serializers/viewsets if the team wants immediate API access

### Recommended sequencing

1. land `RackDeliveryPoint` plus focused model tests first
2. wire persisted delivery points into the existing rack-delivery summary service and detail page
3. add `ElectricalNodePlacement` only after the rack-boundary contract is clear
4. build the read-only layout service and view on top of those persisted models

### Risks

- premature schema growth
- unclear overlap between `RackDeliveryPoint` and existing derived rack-delivery summary rows

### Mitigation

- treat existing derived summary service as a read model, and let `RackDeliveryPoint` become the canonical persisted boundary object over time

---

## Workstream D: UI integration

### Tasks

1. add layout summary card to `PowerSystem`
2. add `PowerSystemLayoutView`
3. build overlay rendering payloads
4. add clear unavailable/empty states

### Risks

- overcommitting to canvas editing too early
- brittle template coupling to floorplan plugin internals

### Mitigation

- start read-only
- keep the layout rendering data contract owned by `netbox_power_plant`

---

## Workstream E: Validation and reporting

### Tasks

1. extend topology validation to include floorplan-aware findings
2. expose findings on relevant detail pages
3. add targeted test coverage for mismatched placement and missing rack mapping cases

### Risks

- noisy validation when layout rollout is incomplete

### Mitigation

- scope new findings to active design states or opt-in validation modes first

---

## 7. Suggested File and Module Changes

### New modules likely needed

- `netbox_power_plant/services/layout.py`
- `netbox_power_plant/services/layout_validation.py`
- `netbox_power_plant/tests/test_layout_service.py`
- `netbox_power_plant/tests/test_layout_views.py`
- `netbox_power_plant/tests/test_layout_validation.py`

### Existing modules likely to change

- `netbox_power_plant/models.py`
- `netbox_power_plant/migrations/`
- `netbox_power_plant/forms.py`
- `netbox_power_plant/filtersets.py`
- `netbox_power_plant/tables.py`
- `netbox_power_plant/views.py`
- `netbox_power_plant/urls.py`
- `netbox_power_plant/navigation.py`
- `netbox_power_plant/api/serializers.py`
- `netbox_power_plant/api/views.py`
- `netbox_power_plant/api/urls.py`
- `netbox_power_plant/services/floorplan.py`
- `netbox_power_plant/services/validation.py`

---

## 8. Testing Strategy

## 8.1 Unit tests

Focus on:

- floorplan availability detection
- site/location floorplan resolution
- canvas mapping extraction for racks/devices
- placement validation rules
- layout-aware redundancy finding generation
- `RackDeliveryPoint` scope and foreign-key validation rules
- `ElectricalNodePlacement` uniqueness and scope validation rules

## 8.2 View tests

Focus on:

- `PowerSystemLayoutView` available state
- no-floorplan fallback state
- mixed floorplan and power overlay rendering state
- visibility of validation summaries and compliance indicators
- rack-delivery detail behavior when persisted delivery points exist but no placement rows exist yet

## 8.3 Integration tests

Focus on:

- floorplan plugin enabled vs disabled behavior
- rack delivery boundary objects appearing in layout summaries
- redundancy findings remaining consistent between topology-only and layout-aware reports
- migration and serializer behavior for new placement/binding models

## 8.4 Regression tests

Do not allow layout integration to break:

- existing phase 1A organizational tests
- existing topology CRUD/UI/API tests
- graph traversal tests
- redundancy validation already delivered in phase 1B

---

## 9. Acceptance Criteria

This plan should be considered successfully implemented when all of the following are true:

1. `netbox_power_plant` can resolve a `netbox_floorplan` context for a `PowerSystem` based on site/location.
2. The plugin has an explicit persisted model for rack-boundary delivery objects.
3. The plugin has an explicit persisted model for facility overlay placement.
4. A `PowerSystem` layout view shows the resolved floorplan with power overlays.
5. Rack delivery and redundancy posture are visible in the layout view.
6. Layout-aware validation findings are available for missing or inconsistent mappings.
7. The plugin still works when floorplan integration is unavailable, with clear degraded behavior.

---

## 10. Open Questions

These decisions should be resolved before Phase 3 begins:

1. Should the power-plant plugin support multiple alternative floorplans per site/location scope, or is one resolved floorplan enough for v1?
2. Should `RackDeliveryPoint` reference `Rack`, `Device`, or both for the initial version?
3. Should facility equipment overlay editing happen inside the power-plant plugin UI only, or should there eventually be a shared editing contract with the floorplan plugin?
4. Should layout-aware validation run automatically inside the existing topology checks, or be exposed as a separate validation lane first?
5. Is it acceptable for the baseline NetBox configuration to always enable `netbox_floorplan`, or should that be revisited and made environment-gated later?

---

## 11. Immediate Next Actions

The next practical implementation slice should be:

1. add `RackDeliveryPoint` to `netbox_power_plant/models.py` with focused validation and migration coverage
2. extend the existing rack-delivery summary service so it can join persisted delivery points to inferred rack-boundary graph rows
3. add CRUD/API/test coverage for `RackDeliveryPoint` so boundary intent becomes inspectable before layout rendering work starts
4. add `ElectricalNodePlacement` only after the rack-boundary contract is stable, then build `services/layout.py` on top of both persisted models and the existing floorplan adapter

That sequence keeps the next slice narrow, turns the already-delivered graph and floorplan work into persisted operator intent, and sets up the later read-only layout page without forcing early canvas-write decisions.