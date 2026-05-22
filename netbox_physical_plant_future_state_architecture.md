# NetBox Physical Plant Future-State Architecture

## Purpose

This document formalizes a future-state architecture for evolving
`netbox_power_plant` into a broader physical-site modeling plugin. The working
product name is **NetBox Physical Plant**. The current power-plant model remains
important, but power becomes one discipline-specific subsystem inside a common
physical site model.

The motivation is Madison, NC: the blueprint and workbook sources describe much
more than electrical topology. They describe rooms, halls, galleries, rack rows,
rack footprints, elevations, equipment pads, electrical gear, cable pathways,
grounding, cooling equipment, and repeated physical patterns. NetBox core is the
right system of record for inventory identity, but it is not meant to be a CAD
or blueprint model. The plugin should own that physical underlay and bind it
cleanly to NetBox-native objects.

This is a future-state architecture. It is intentionally broader than the
current implementation, which already contains `SpatialFrame`,
`SpatialPlacement`, electrical graph models, `PowerHandoffPoint`,
`InternalPowerBus`, import services, validation services, and operator summaries.

## Executive Summary

The plugin should be recast around four core principles:

1. **Physical space**: model the actual site underlay: campus, building, floor,
   room, data hall, gallery, yard, aisle, rack row, rack slot, wall elevation,
   equipment pad, and other spaces derived from design documents.
2. **Physical object**: model blueprint-visible things that may or may not be
   NetBox inventory: racks, rack slots, transformers, generators, switchboards,
   RPPs, cable trays, conduits, busways, panels, grounding bars, CRAHs, CDUs,
   doors, walls, columns, and pads.
3. **System topology**: keep discipline-specific connection graphs separate
   from physical placement. Electrical, fiber, cooling, grounding, and pathway
   systems all have different topology semantics but can share the same
   physical underlay.
4. **Object binding**: explicitly bind physical elements and placements to
   NetBox-native objects and plugin-native topology objects. NetBox keeps
   inventory identity. The plugin keeps blueprint-derived physical reality.

The resulting model lets operators answer:

- Where is this NetBox rack or device in the actual design underlay?
- What blueprint object, source sheet, and confidence level produced this
  placement?
- What electrical, fiber, cooling, grounding, or pathway system touches this
  physical object?
- What physical objects are not yet represented by NetBox inventory?
- Which plugin-native topology nodes are logical only versus physically placed?
- How do plan coordinates, room coordinates, z-axis positions, and rack/wall
  elevations relate to each other?

## Product And Compatibility Posture

The safest migration path is not an immediate package rename.

- Keep the Python package and Django app label as `netbox_power_plant` until the
  schema has stabilized.
- Change the user-facing product language to "Physical Plant" where the feature
  scope is broader than electrical power.
- Add physical-core models alongside the existing power models.
- Keep existing electrical APIs stable and progressively rebase them onto the
  physical core.
- Consider a package/app rename only after downstream migrations and operator
  workflows are proven.

Recommended staged naming:

| Layer | Near-term name | Future product name |
|---|---|---|
| Python package | `netbox_power_plant` | keep or rename later |
| Django app label | `netbox_power_plant` | keep unless migration cost is justified |
| Navigation group | Power Plant / Physical Plant during transition | Physical Plant |
| Electrical subsystem | Power Plant | Electrical Plant |
| Spatial subsystem | Spatial Models | Physical Underlay |

## Architectural Principles

### 1. Physical Space

Physical spaces are the objective underlay. They are not merely NetBox
`Location` rows with extra attributes. A NetBox `Location` is an inventory scope;
a physical space is a geometrically meaningful part of the design.

Examples:

- site plan frame for Madison / GS001
- building footprint
- data halls and galleries
- electrical rooms
- mechanical rooms
- exterior equipment yards
- rack rows and aisle zones
- individual rack slots
- wall elevations
- rack front/rear elevation frames

Rules:

- A physical space may bind to a NetBox `Site` or `Location`, but does not have
  to be one-to-one with NetBox hierarchy.
- Physical spaces can have boundaries, z ranges, and source provenance.
- A physical space may contain other spaces.
- Space identity must be stable even if the NetBox location taxonomy changes.

### 2. Physical Object

Physical objects are things shown or implied by blueprints, schedules, and
workbooks. Some are NetBox objects, some are plugin topology nodes, and some are
neither.

Examples:

- rack footprint
- rack sidecar
- electrical switchboard lineup
- RPP
- transformer
- generator
- cable tray
- conduit
- grounding bar
- CRAH
- CDU
- door
- wall
- column
- equipment pad

Rules:

- Do not force every physical object to become a NetBox `Device`.
- Do not force every physical object into the electrical graph.
- Classify physical objects with type, discipline, role, geometry, and source
  confidence.
- Allow physical objects to represent either actual assets or design placeholders.

### 3. System Topology

Topology describes how systems connect. Placement describes where things are.
Those two concerns must remain separate.

Disciplines should share common physical placement and provenance machinery, but
they may have their own topology semantics:

- Electrical: sources, terminals, segments, redundancy domains, handoffs to
  `dcim.PowerPort`, internal buses.
- Fiber and network plant: trays, cassettes, ports, strands, trunks, pathways,
  lane maps, splice/transfer behavior.
- Mechanical/cooling: equipment, pipes, flow paths, valves, coils, CDUs, CRAHs.
- Grounding/bonding: bars, bonding conductors, grounding electrodes, rack bonds.
- Pathways: cable trays, conduits, sleeves, risers, duct banks, ladder rack.

Rules:

- Do not use physical containment hierarchy as the only topology model.
- Do not use topology edges as the only placement model.
- Derive operator views by joining topology paths to physical placements.

### 4. Object Binding

Bindings connect the physical underlay to NetBox and to plugin-native systems.
They are explicit records, not hidden assumptions.

Examples:

- rack footprint physical element represents NetBox `Rack A2`
- room polygon represents NetBox `Location Data Hall 2a`
- RPP blueprint symbol represents plugin `ElectricalNode RPP-2A-1-1-1`
- PS33 shelf placement represents NetBox `Device gs001-a2-u42-ps33`
- cabinet circuit endpoint binds to `PowerHandoffPoint`
- cable tray path constrains fiber pathway routing but is not itself a fiber
  segment

Rules:

- Bindings should carry a role, confidence, and provenance.
- A physical object may bind to zero, one, or many logical/inventory objects.
- A NetBox object may have zero, one, or many physical placements.
- Stale binding detection is a first-class validation concern.

## Future-State Data Model

### Source And Provenance Models

#### `PlantSourceDocument`

Represents a source artifact.

Suggested fields:

- `name`
- `slug`
- `source_type`: PDF, SVG, CAD export, workbook, CSV, Mermaid, manual note
- `discipline`: architectural, electrical, mechanical, telecom, grounding,
  rack_layout, mixed
- `file_path` or managed file reference
- `title`
- `revision`
- `issue_date`
- `issuer`
- `checksum`
- `is_active`
- `comments`

#### `PlantSourceSheet`

Represents a page, sheet, worksheet, or drawing view inside a source document.

Suggested fields:

- `source_document`
- `sheet_number`
- `sheet_title`
- `discipline`
- `page_index`
- `view_box`
- `native_width`
- `native_height`
- `native_units`
- `scale_text`
- `rotation_degrees`
- `comments`

#### `PlantSourceLayer`

Represents a parsed or manually named source layer.

Suggested fields:

- `source_sheet`
- `name`
- `layer_kind`: geometry, annotation, equipment, rack_layout, circuit,
  pathway, room_boundary, unknown
- `is_visible`
- `comments`

#### `PlantProvenance`

Generic provenance link from any modeled object to a source location.

Suggested fields:

- generic assigned object
- `source_document`
- `source_sheet`
- `source_layer`
- `source_label`
- `source_ref`
- `source_row`
- `source_column`
- `source_bbox`: JSON, source-native coordinates
- `extraction_method`: manual, parsed_svg, parsed_pdf, workbook, csv,
  reconciliation
- `confidence`: authoritative, derived, provisional, logical, unknown
- `notes`

### Physical Underlay Models

#### `PhysicalFrame`

Supersedes or extends `SpatialFrame`.

Suggested fields:

- `site`
- `location`, optional
- `parent_frame`, optional
- `name`
- `slug`
- `frame_kind`: site_plan, building_plan, floor_plan, room_plan, equipment_yard,
  rack_elevation, wall_elevation, schematic, logical
- `units`: svg_unit, mm, cm, m, inch, ft, rack_unit
- `axis_orientation`: y_down, y_up, z_up, rack_ru_up, wall_elevation
- `origin_x_in_parent`
- `origin_y_in_parent`
- `origin_z_in_parent`
- `width`
- `depth`
- `height`
- `rotation_degrees`
- `scale_x`
- `scale_y`
- `scale_z`
- `transform_matrix`: optional JSON for advanced transforms
- `z_datum`: finished_floor, slab, site_datum, rack_base, ceiling, unknown
- source/provenance fields

Madison examples:

- `gs001-site-plan-v1`
- `gs001-room-b1209-v1`
- `gs001-room-b1211-v1`
- `gs001-room-b1111-v1`
- `gs001-rack-a2-front-elevation-v1`
- `gs001-electrical-yard-plan-v1`

#### `PhysicalSpace`

Represents meaningful spaces and boundaries.

Suggested fields:

- `physical_frame`
- `parent_space`, optional
- `site`
- `location`, optional
- `name`
- `slug`
- `space_kind`: campus, building, floor, room, gallery, data_hall,
  electrical_room, mechanical_room, yard, aisle, row_zone, rack_slot,
  wall_zone, containment_zone, clearance_zone
- `boundary_geometry`: JSON polygon/rectangle/path
- `z_min`
- `z_max`
- `source_label`
- `confidence`
- `description`

#### `PhysicalElementType`

Reusable classification for blueprint-visible elements.

Suggested fields:

- `name`
- `slug`
- `discipline`
- `element_kind`: rack_footprint, sidecar, transformer, generator, switchgear,
  panelboard, RPP, UPS, UOP, PDU, cable_tray, conduit, duct, pipe,
  grounding_bar, wall, door, column, equipment_pad, annotation, other
- `default_width`
- `default_depth`
- `default_height`
- `default_symbol`
- `default_color`
- `is_placeable`
- `is_pathway`
- `is_inventory_candidate`
- `comments`

#### `PhysicalElement`

Instance of a physical object from the blueprint or staging model.

Suggested fields:

- `element_type`
- `site`
- `physical_space`, optional
- `name`
- `slug`
- `label`
- `role`
- `design_state`
- `install_state`
- `manufacturer`
- `model`
- `asset_tag`
- `source_label`
- `confidence`
- `metadata`: JSON
- `comments`

### Placement And Geometry Models

#### `PhysicalPlacement`

General-purpose placement of any object in a frame.

Suggested fields:

- generic assigned object
- `physical_frame`
- `physical_space`, optional
- `placement_kind`: physical, logical, provisional, schematic, clearance,
  pathway, rack_elevation, wall_elevation
- `geometry_type`: point, rectangle, polygon, polyline, volume, rack_ru_span,
  wall_mount
- `x`
- `y`
- `z`
- `width`
- `depth`
- `height`
- `rotation_degrees`
- `anchor`: center, top_left, bottom_left, front_center, rear_center,
  rack_base, wall_face, ceiling, floor
- `mount_face`: floor, ceiling, wall_north, wall_south, wall_east, wall_west,
  rack_front, rack_rear, overhead, underfloor, unknown
- `path_geometry`: JSON for polylines and routed pathways
- `polygon_geometry`: JSON for non-rectangular areas
- `z_min`
- `z_max`
- `confidence`
- `source/provenance`

This model should support:

- rack footprint rectangles
- rack center points
- room polygons
- cable tray polylines
- conduit paths
- equipment pad rectangles
- wall-mounted grounding bars
- rack front/rear RU spans
- overhead pathway z elevations

#### `PhysicalObjectBinding`

Explicit binding between physical elements/placements and NetBox or plugin
objects.

Suggested fields:

- `physical_element`, optional
- `physical_placement`, optional
- generic assigned object
- `binding_role`: represents, contains, mounted_on, served_by, source_of_truth,
  derived_from, topology_node_for, inventory_object_for
- `confidence`
- `is_primary`
- `provenance`
- `comments`

### System Topology Models

The current electrical models should remain valid during transition. The future
architecture can either:

1. keep `ElectricalNode`, `ElectricalTerminal`, and `ElectricalSegment` as
   electrical-specific models that bind to physical objects; or
2. introduce generic `PlantSystem`, `PlantNode`, `PlantTerminal`, and
   `PlantSegment` models, then treat electrical models as compatibility views or
   subclasses.

The second path is more powerful but riskier. The recommended implementation is
incremental:

- keep the existing electrical models;
- add physical bindings to them;
- later introduce a generic topology layer only when a second discipline, such
  as pathways or grounding, proves the abstraction.

#### Future Generic Topology Candidate

`PlantSystem`

- `discipline`: electrical, fiber, cooling, grounding, pathway, architectural
- `site`
- `location`, optional
- `name`
- `slug`
- `design_state`

`PlantNode`

- `plant_system`
- `physical_element`, optional
- `node_kind`
- `role`
- `design_state`
- `metadata`

`PlantTerminal`

- `plant_node`
- `terminal_kind`
- `direction`
- `media_type`: AC, DC, fiber, coolant, air, ground, pathway
- `metadata`

`PlantSegment`

- `plant_system`
- `from_terminal`
- `to_terminal`
- `segment_kind`
- `route_placement`, optional
- `design_state`
- `metadata`

### Discipline-Specific Extensions

Electrical remains the first-class discipline already implemented.

Electrical future-state additions:

- bind each `ElectricalNode` to zero or more `PhysicalElement`s;
- bind each `PowerHandoffPoint` to the placement of its target `PowerPort`
  through the target device/rack;
- validate that handoff targets are within the expected physical site/space;
- distinguish logical-only electrical nodes from physically placed equipment.

Pathway candidate discipline:

- `PathwaySystem`
- cable tray, ladder rack, conduit, sleeve, duct bank, underfloor zone,
  overhead zone
- polyline placements with z values
- pathway capacity and reservation metadata

Grounding candidate discipline:

- grounding bars
- bonding conductors
- grounding electrode system
- rack bonds
- tray bonds
- continuity graph

Cooling candidate discipline:

- CRAH/CRAC/CDU/chiller/pump placements
- piping or cooling loop topology
- service zones and airflow zones

## Z-Axis And Elevation Strategy

The model must support z-axis placement without pretending every source drawing
has architectural precision.

Recommended conventions:

- Every `PhysicalFrame` declares its axis orientation and z datum.
- Plan frames support `x`, `y`, `z` and optional `z_min` / `z_max`.
- Rack elevation frames use rack units as vertical coordinates where useful.
- Wall elevation frames use local wall coordinates.
- Overhead and underfloor pathways use z ranges relative to the parent frame's
  datum.
- Objects can have multiple placements when appropriate:
  - rack footprint in a room plan
  - rack front elevation frame
  - rack rear elevation frame
  - device RU placement from NetBox

Madison-specific initial recommendation:

- treat the original CAD/DWG blueprint files as the authority for physical
  dimensions, scale, and building extents;
- use a lower-left, X-right, Y-up site grid whose origin is the lower-left
  corner of the calibrated physical structure;
- use the plugin's mandatory `ezdwg[dxf]` dependency for PyPI-installed DWG
  reading and optional DXF export;
- preserve SVG-native y-down coordinates only as an approximate overlay
  transform onto the CAD-derived grid;
- store source drawing units explicitly, normally converting CAD architectural
  inches or feet into operator-facing feet;
- model rack footprints with top-left and center anchor placements;
- use rack elevation data from the workbook for NetBox RU positions;
- only place major electrical equipment when the source blueprint location is
  trustworthy.

## Relationship To NetBox Core

NetBox remains authoritative for:

- `Site`
- `Location` as inventory scope
- `Rack`
- `Device`
- `Module`
- `Interface`
- `PowerPort`
- tags, tenants, status, roles where native objects support them

The plugin becomes authoritative for:

- source document provenance
- objective coordinate frames
- physical spaces and boundaries
- blueprint-derived physical elements
- physical placements and geometry
- bindings from blueprint reality to NetBox inventory
- discipline topology outside NetBox native constructs
- spatial/topological validation

The plugin must not:

- replace NetBox `Rack` or `Device` identity;
- create a parallel inventory model for normal NetBox inventory;
- use physical placement as a hidden substitute for topology;
- use topology as a hidden substitute for physical placement;
- assume CAD-grade precision when the source is an SVG export or parsed PDF.

## Madison Target Fit

This architecture can represent the majority of Madison design elements:

| Blueprint/design element | Future model |
|---|---|
| Site plan drawing | `PlantSourceDocument`, `PlantSourceSheet`, `PhysicalFrame` |
| Data halls and galleries | `PhysicalSpace` polygons bound to NetBox `Location`s |
| Rack row grid | `PhysicalSpace` row zones and rack-slot spaces |
| NetBox racks | NetBox `Rack` plus `PhysicalPlacement` and `PhysicalObjectBinding` |
| Rack elevations | `PhysicalFrame` with rack elevation orientation, plus NetBox RU positions |
| Sidecars | `PhysicalElement` plus optional NetBox rack/device binding if promoted |
| Electrical rooms | `PhysicalSpace` bound to NetBox location where appropriate |
| PRSG, transformers, generators, ATS, MDP, UPS, UOP, PDU, RPP | `ElectricalNode` plus `PhysicalElement` and `PhysicalPlacement` |
| RPP-to-cabinet circuits | `ElectricalSegment` to provisional rack circuit nodes, then `PowerHandoffPoint` |
| Cable trays/conduits | pathway `PhysicalElement`s with polyline `PhysicalPlacement`s |
| Grounding bars/bonds | grounding physical elements and later grounding graph |
| CRAH/CDU/mechanical gear | physical elements now, mechanical topology later |
| Blueprint source labels | `PlantProvenance` |
| Unknown exact placement | logical/provisional placement or no placement |

## Validation Themes

Future validation should include:

- frame transform sanity checks;
- placements inside physical-space boundaries;
- stale bindings to deleted or moved NetBox objects;
- NetBox object site/location versus physical frame site/location;
- duplicate rack footprints;
- overlapping physical placements where not allowed;
- missing placement for objects expected to be placeable;
- electrical handoff target outside expected physical scope;
- pathway route discontinuity;
- z-axis discontinuity in cable tray/conduit/piping paths;
- rack row/aisle clearance violations;
- source provenance missing for blueprint-derived placements;
- confidence downgrade reporting for inferred or unresolved placements.

## API And UI Direction

Recommended operator views:

- Physical Plant Overview
- Source Documents
- Physical Frames
- Physical Spaces
- Physical Elements
- Placements
- Object Bindings
- Site Plan Viewer
- Room Plan Viewer
- Rack Row Viewer
- Rack Elevation Viewer
- Discipline Overlay Viewer

Viewer behavior:

- show base underlay geometry;
- toggle disciplines: electrical, racks, fiber/pathway, cooling, grounding;
- click any object to see source provenance, NetBox binding, and topology links;
- trace from a NetBox rack/device/power port to physical underlay and system
  topology;
- highlight incomplete or low-confidence placements;
- make review/approval visual-first: an operator should approve imported or
  extracted spaces, footprints, and placements from an overlay, not from tables
  alone;
- support controlled geometry correction for derived objects before approval,
  beginning with rectangle bounds for spaces and rack footprints;
- export reconciliation reports.

## Immediate Priority: Visual Spatial Review

The Madison modeling workflow has proven that tables and JSON geometry are not
enough. Visualization is therefore not a later UI polish item; it is a core
modeling requirement and must precede large-scale rack-footprint extraction and
binding.

The first-class visual review surface should:

- render `SpatialFrame` coordinate planes, `PhysicalSpace.boundary_geometry`,
  `PhysicalElement` footprints, `SpatialPlacement` rectangles/points, and
  `PhysicalObjectBinding` status in one site/room viewer;
- show source underlay evidence where available, including CAD-rendered sheet
  imagery or simplified CAD geometry;
- color-code confidence and review state: approved, operator-review-required,
  inferred, unmatched, stale, or invalid;
- make every rendered object clickable, with links to the plugin object,
  NetBox-native binding, source provenance, and validation findings;
- support overlay toggles for spaces, rack footprints, electrical gear,
  power handoffs, circuit/pathway hints, and validation findings;
- allow geometry correction for reviewable rectangles in the first iteration:
  drag/move/resize a space or footprint, preview changed coordinates, save a
  reviewed geometry revision, and record reviewer/provenance metadata;
- keep CAD/native coordinates authoritative in the data model while using SVG or
  canvas as the browser rendering layer;
- expose the same renderer in the Madison Underlay Review page before approval
  actions, so approval means "visually reviewed against the underlay."

Near-term implementation order:

1. Build a read-only spatial renderer service that converts frames, spaces,
   placements, and bindings into normalized SVG/canvas primitives.
2. Embed the renderer in the Madison Underlay Review page for the approved site
   frame and the ten detailed spaces.
3. Add visual review affordances: selection, object detail side panel, status
   legend, confidence coloring, source/provenance links, and validation overlays.
4. Add rectangle-edit workflow for `PhysicalSpace.boundary_geometry`, storing
   operator-corrected geometry with approval metadata.
5. Use this visual review foundation for rack-footprint extraction, matching, and
   binding approval.

## Implementation Plan And Parallel Workstreams

The work below is organized for parallel execution. Workstreams should keep
write scopes disjoint where possible and land behind service APIs and focused
tests.

### Phase 0: Alignment And Migration Guardrails

Owner: architecture lead

Checklist:

- [ ] Confirm product naming: keep `netbox_power_plant` app label for now.
- [ ] Confirm target NetBox version for the next schema migration.
- [ ] Freeze current electrical behavior with regression tests.
- [ ] Identify migrations that must remain backward compatible.
- [ ] Decide whether `SpatialFrame`/`SpatialPlacement` will be renamed,
      extended in place, or superseded by new models.
- [ ] Document compatibility aliases if new physical names supersede spatial
      names.
- [ ] Define a feature flag or release note for "Physical Plant core" rollout.

Acceptance criteria:

- Existing power-plant tests pass.
- No current `PowerHandoffPoint` or `InternalPowerBusAttachment` behavior is
  broken.
- The migration path does not require deleting Madison staged data.

### Phase 1: Source And Provenance Foundation

Owner: source/provenance workstream

Files likely touched:

- `models.py` or new model modules
- `choices.py`
- `migrations/`
- `api/serializers.py`
- `api/views.py`
- `filtersets.py`
- `forms.py`
- `tables.py`
- tests for models/API/views

Checklist:

- [ ] Add `PlantSourceDocument`.
- [ ] Add `PlantSourceSheet`.
- [ ] Add `PlantSourceLayer`.
- [ ] Add generic `PlantProvenance`.
- [ ] Add choices for source type, discipline, layer kind, extraction method,
      and confidence.
- [ ] Add REST API serializers and viewsets.
- [ ] Add list/detail/edit views.
- [ ] Add table/filter/form coverage.
- [ ] Add model validation for source-sheet/document relationships.
- [ ] Add tests for provenance generic assignment.
- [ ] Seed Madison source document records for the known layout SVG, layout
      workbook, fiber workbook, and electrical extracts.

Acceptance criteria:

- Any modeled physical object or placement can carry source provenance.
- Source records can represent both file-level and sheet/worksheet-level
  evidence.

### Phase 2: Physical Frames

Owner: coordinate-frame workstream

Checklist:

- [ ] Decide whether to extend `SpatialFrame` or add `PhysicalFrame`.
- [ ] Add frame kind, units, axis orientation, z datum, scale, rotation, and
      optional transform matrix.
- [ ] Add parent-child frame validation.
- [ ] Add transform service:
      - [ ] child-to-parent coordinates;
      - [ ] parent-to-child coordinates;
      - [ ] source y-down to architectural y-up transform;
      - [ ] z datum conversion hooks.
- [ ] Add frame API and UI.
- [ ] Add tests for nested frame transforms.
- [ ] Add Madison frame fixtures/service for:
      - [ ] site plan frame;
      - [ ] room frames;
      - [ ] rack elevation frame pattern.

Acceptance criteria:

- A placement in a room frame can be resolved to site-plan coordinates.
- Coordinate conventions are explicit and test-covered.

### Phase 3: Physical Spaces

Owner: physical-space workstream

Checklist:

- [ ] Add `PhysicalSpace`.
- [ ] Add space kind choices.
- [ ] Add boundary geometry storage.
- [ ] Add containment service:
      - [ ] point inside space;
      - [ ] rectangle inside space;
      - [ ] polygon overlap basics.
- [ ] Add NetBox `Site`/`Location` binding fields or companion binding service.
- [ ] Add API/UI/table/form/filter coverage.
- [ ] Add tests for room and rack-row containment.
- [ ] Add Madison space creation service for data halls and galleries.

Acceptance criteria:

- A Madison rack placement can be associated with a room/data-hall space.
- Space/site/location scope mismatches are detected.

### Phase 4: Physical Elements

Owner: physical-element workstream

Checklist:

- [ ] Add `PhysicalElementType`.
- [ ] Add `PhysicalElement`.
- [ ] Add discipline and element-kind choices.
- [ ] Add default symbol/color/dimension support.
- [ ] Add provenance support.
- [ ] Add lifecycle/design/install state support.
- [ ] Add API/UI coverage.
- [ ] Add test coverage for type defaults and scope validation.
- [ ] Add Madison element types for:
      - [ ] rack footprint;
      - [ ] sidecar;
      - [ ] RPP;
      - [ ] UPS/UOP/PDU;
      - [ ] transformer/generator/ATS/MDP;
      - [ ] cable tray/conduit;
      - [ ] grounding bar;
      - [ ] CRAH/CDU.

Acceptance criteria:

- Blueprint-visible objects can exist without being NetBox devices.
- Physical elements can later bind to NetBox or plugin topology objects.

### Phase 5: Generalized Placements

Owner: placement/geometry workstream

Checklist:

- [ ] Decide whether to extend `SpatialPlacement` or add `PhysicalPlacement`.
- [ ] Support assigned generic object.
- [ ] Add geometry type choices.
- [ ] Add x/y/z, dimensions, rotation, anchor, mount face, z range.
- [ ] Add polygon/path JSON fields.
- [ ] Add placement-kind and confidence choices.
- [ ] Add service helpers for:
      - [ ] rack footprint placement;
      - [ ] center point derivation;
      - [ ] polyline path placement;
      - [ ] z range validation;
      - [ ] frame transform resolution.
- [ ] Add API/UI coverage.
- [ ] Add tests for point, rectangle, polygon, polyline, and rack elevation
      placements.
- [ ] Add Madison rack footprint import service from SVG/workbook-derived data.

Acceptance criteria:

- NetBox racks and plugin electrical nodes can share the same placement model.
- z-axis/elevation values can be stored without overloading 2D fields.

### Phase 6: Object Bindings

Owner: binding/reconciliation workstream

Checklist:

- [ ] Add `PhysicalObjectBinding`.
- [ ] Add binding role choices.
- [ ] Support generic assigned object.
- [ ] Add primary binding semantics.
- [ ] Add stale binding checks.
- [ ] Add service to find physical placement for any NetBox object.
- [ ] Add service to find NetBox/plugin objects represented by a physical
      element.
- [ ] Add API/UI coverage.
- [ ] Add tests for rack, device, location, electrical-node, and handoff
      bindings.
- [ ] Add Madison rack binding service:
      - [ ] rack footprint element to NetBox `Rack`;
      - [ ] room physical space to NetBox `Location`;
      - [ ] electrical node to physical element where known.

Acceptance criteria:

- Physical underlay and NetBox inventory are joined through explicit records.
- Stale/missing bindings are reportable.

### Phase 7: Electrical Model Integration

Owner: electrical integration workstream

Checklist:

- [ ] Add optional physical binding helpers to `ElectricalNode`.
- [ ] Add services to resolve physical placement for `PowerHandoffPoint` targets.
- [ ] Extend completeness validation to include physical placement coverage.
- [ ] Add finding types:
      - [ ] electrical_node_unplaced;
      - [ ] handoff_target_unplaced;
      - [ ] handoff_target_outside_expected_space;
      - [ ] electrical_node_binding_stale.
- [ ] Add UI links from electrical node/handoff views to physical placement.
- [ ] Add tests using Madison-like rack/handoff fixtures.

Acceptance criteria:

- Existing electrical graph behavior remains unchanged.
- Operators can move from an electrical node/handoff to its physical location
  when known.

### Phase 8: Madison Spatial Underlay Import

Owner: Madison import workstream

Checklist:

- [ ] Parse or ingest `madison-physical-layout.svg` frame metadata.
- [ ] Create source document/sheet/layer records.
- [ ] Create `gs001-site-plan-v1`.
- [ ] Create room frames and physical spaces for:
      - [ ] B1209;
      - [ ] B1211;
      - [ ] B1111;
      - [ ] Data Hall 1a pending room number;
      - [ ] galleries B1208/B1210/B1212/B1108/B1110/B1112.
- [ ] Reconcile broad NetBox locations `Data Hall 1` / `Data Hall 2` with
      room-level physical spaces.
- [ ] Generate rack-slot spaces or rack footprint elements.
- [ ] Create `PhysicalPlacement` rows for all workbook-authoritative racks.
- [ ] Bind each rack placement to NetBox `Rack`.
- [ ] Preserve row-id tags as semantic overlay, not the only underlay.
- [ ] Create dry-run/apply workflow with counts and blocked reasons.
- [ ] Add validation report for unplaced racks and duplicate footprints.

Acceptance criteria:

- Every Madison NetBox rack has an objective placement or an explicit blocked
  reason.
- The placement source and confidence are visible.

### Phase 9: Blueprint Electrical Equipment Placement

Owner: electrical placement import workstream

Checklist:

- [ ] Identify which Madison electrical source drawings expose trustworthy
      physical equipment positions.
- [ ] Create physical element types for major electrical equipment.
- [ ] Create physical elements for placed equipment.
- [ ] Bind physical elements to existing `ElectricalNode`s.
- [ ] Leave schematic-only electrical nodes logical/provisional.
- [ ] Add dry-run/apply workflow.
- [ ] Add validation report:
      - [ ] major equipment missing placement;
      - [ ] equipment with no electrical-node binding;
      - [ ] electrical node with stale physical binding.

Acceptance criteria:

- Major electrical equipment has physical placement where source evidence is
  strong.
- Logical-only nodes are clearly labeled and do not masquerade as placed
  equipment.

### Phase 10: Z-Axis And Elevation

Owner: z-axis/elevation workstream

Checklist:

- [ ] Add rack elevation frame pattern.
- [ ] Add wall elevation frame pattern.
- [ ] Add support for rack front/rear mount face.
- [ ] Add overhead and underfloor pathway z conventions.
- [ ] Reconcile NetBox RU position with plugin elevation placements.
- [ ] Add tests for rack elevation coordinates and z ranges.
- [ ] Add Madison rack elevation import or binding from workbook RU placements.
- [ ] Add validation for impossible z ranges and inconsistent mount faces.

Acceptance criteria:

- A rack can have both a plan footprint and elevation-aware contents.
- Pathways/equipment can be modeled above, below, or on the floor.

### Phase 11: Pathway And Grounding Pilot

Owner: non-power discipline pilot workstream

Checklist:

- [ ] Define pathway element types: cable tray, ladder rack, conduit, sleeve,
      duct bank.
- [ ] Model pathway placements as polylines with z.
- [ ] Define grounding element types: TGB, bonding conductor, tray bond,
      grounding electrode.
- [ ] Decide whether to introduce generic `PlantSystem` topology now or keep
      pathway/grounding as physical elements only.
- [ ] Add Madison pilot data for one hall/row where source evidence is strong.
- [ ] Add validation for path discontinuity and missing z values.

Acceptance criteria:

- The physical plant model proves it can represent a second discipline without
  distorting the electrical model.

### Phase 12: Operator UI

Owner: UI/workflow workstream

Status:

- The visual spatial review subset of this phase has been promoted to the
  immediate priority above and should be implemented before rack-footprint
  extraction/binding at Madison scale.
- The remaining items in this phase still describe the broader operator UI
  build-out after the renderer is established.

Checklist:

- [ ] Add Physical Plant navigation group.
- [ ] Add overview dashboard.
- [ ] Add source document browser.
- [ ] Add frame/space/element/placement/binding list and detail views.
- [ ] Add site plan viewer.
- [ ] Add room plan viewer.
- [ ] Add rack row viewer.
- [ ] Add rack elevation viewer.
- [ ] Add overlay toggles by discipline.
- [ ] Add click-through from visual object to:
      - [ ] source provenance;
      - [ ] NetBox object;
      - [ ] plugin topology node;
      - [ ] validation findings.
- [ ] Add visual display for confidence and unresolved status.

Acceptance criteria:

- Operators can inspect Madison rack and electrical placements visually.
- Low-confidence or unresolved objects are visible, not hidden in tables.

### Phase 13: Validation And Reporting

Owner: validation/reporting workstream

Checklist:

- [ ] Add physical placement validation service.
- [ ] Add physical binding validation service.
- [ ] Add source/provenance coverage validation.
- [ ] Add geometry containment checks.
- [ ] Add overlap checks for racks/equipment.
- [ ] Add frame transform checks.
- [ ] Add z-axis continuity checks.
- [ ] Add persisted findings integration.
- [ ] Add operator reports:
      - [ ] unplaced NetBox racks;
      - [ ] unplaced electrical nodes;
      - [ ] stale physical bindings;
      - [ ] placements outside site/location scope;
      - [ ] duplicate or overlapping rack footprints;
      - [ ] source documents with no modeled objects.

Acceptance criteria:

- Physical underlay completeness is testable and persisted as findings.
- Reports are actionable by operators.

### Phase 14: API, Import, And Automation Hardening

Owner: API/import workstream

Checklist:

- [ ] Add REST endpoints for all new physical-core models.
- [ ] Add bulk import services for frames, spaces, elements, placements, and
      bindings.
- [ ] Add dry-run/apply semantics.
- [ ] Add import artifacts and reconciliation summaries.
- [ ] Add blocked-row reasons.
- [ ] Add idempotent slug/stable-key strategy.
- [ ] Add rollback-safe transactions.
- [ ] Add example Madison import scripts.
- [ ] Add API tests and import workflow tests.

Acceptance criteria:

- Madison physical underlay can be rebuilt idempotently.
- Operators can preview changes before applying them.

### Phase 15: Documentation And Migration Guides

Owner: docs workstream

Checklist:

- [ ] Update README with Physical Plant direction.
- [ ] Update existing power-plant proposal to reference this document.
- [ ] Add model glossary.
- [ ] Add Madison Spatial Underlay v1 runbook section.
- [ ] Add examples:
      - [ ] rack placement;
      - [ ] electrical node placement;
      - [ ] source provenance;
      - [ ] NetBox rack binding;
      - [ ] z-axis/rack elevation;
      - [ ] pathway polyline.
- [ ] Add migration notes from `SpatialFrame`/`SpatialPlacement`.
- [ ] Add operator guide for validation and reconciliation.

Acceptance criteria:

- A new contributor can understand the future-state architecture and implement a
  workstream without reverse-engineering the code.

## Suggested Parallelization

The following streams can proceed in parallel after Phase 0:

| Stream | Primary dependency | Can run with |
|---|---|---|
| Source/provenance | Phase 0 | Frames, elements |
| Frames/transforms | Phase 0 | Provenance, spaces |
| Physical spaces | Frames | Elements |
| Physical elements | Provenance | Spaces, placements |
| Placements | Frames, elements | Bindings after initial model settles |
| Bindings | Elements, placements | Electrical integration |
| Electrical integration | Bindings | Madison import |
| Madison rack underlay import | Frames, spaces, placements, bindings | UI/reporting |
| Electrical equipment placement import | Elements, placements, bindings | Validation |
| Z-axis/elevation | Frames, placements | UI |
| Pathway/grounding pilot | Elements, placements | Validation |
| UI | API/model shape | Validation/reporting |
| Validation/reporting | all core services | Docs |

## Initial Milestone Definition

The first meaningful milestone should be **Physical Plant Core MVP**:

- source document/sheet/provenance models;
- physical frames with explicit coordinate conventions;
- physical spaces for Madison rooms/halls;
- physical elements;
- generalized placements with x/y/z and geometry type;
- physical object bindings;
- Madison rack footprint import and binding to NetBox racks;
- validation findings for unplaced/stale/out-of-scope objects;
- UI/API enough for inspection.

The second milestone should be **Electrical Placement MVP**:

- bind major electrical nodes to physical elements;
- place known major electrical equipment;
- keep schematic-only nodes explicit;
- surface electrical placement completeness in validation.

The third milestone should be **Multi-Discipline Pilot**:

- model one pathway or grounding slice from Madison;
- prove that the physical core is not power-specific;
- validate z-axis and route behavior.

## Open Decisions

- Whether to rename `SpatialFrame` and `SpatialPlacement` or introduce new
  physical-core models alongside them.
- Whether generic `PlantSystem` topology should be introduced before a second
  discipline is implemented.
- Whether Madison site plan coordinates should remain SVG-native y-down or be
  transformed into a y-up room coordinate convention for all operator-facing
  views.
- Which source documents are authoritative for electrical equipment placement,
  not just electrical topology.
- Whether sidecars should remain physical elements only or become NetBox racks.
- Whether wall elevations and rack elevations should share one model with frame
  kind choices or get specialized helper models.
- How much geometry should be stored directly in JSON versus normalized into
  segment/vertex tables later.

## Near-Term Recommendation

Do not start by renaming the plugin. Start by adding the physical-core model
slice behind the current package name, with Madison rack placement as the first
operator-visible use case.

That yields immediate value:

- objective rack underlay;
- source-backed room/frame coordinates;
- clear distinction between row-id tags and physical placement;
- a foundation for electrical placement;
- a foundation for z-axis/elevation and pathways.

Once this is stable, the broader product rename becomes mostly a documentation
and navigation decision rather than a risky schema event.
