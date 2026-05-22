# NetBox Power Plant Plugin

NetBox plugin scaffold for facility-side electrical plant modeling.

## Overview

This repository follows the same local-development pattern as the sibling
`netbox_rpki` and `netbox_multiplanar_fabrics` repositories:

- native Python execution against a pinned local NetBox checkout;
- Docker Compose for PostgreSQL and Redis;
- a repo-specific `devrun` wrapper for bootstrapping, test execution, and
  runtime isolation;
- plugin-specific enable flags and test settings so multiple local NetBox plugin
  repos can coexist cleanly.

The local development scaffold provides:

- an installable NetBox plugin package;
- a dedicated `devrun` stack with repo-specific state and Compose naming;
- a test configuration that loads the plugin through NetBox's testing settings;
- initial contributor docs aligned with the other plugin repos in this workspace.

The NetBox 4.2.3 compatibility branch treats `dcim.PowerPort` as the only
native NetBox power object at the device boundary. Power panels, feeds, outlets,
internal rack buses, and delivery paths are modeled in `netbox_power_plant`
through electrical nodes, terminals, segments, `PowerHandoffPoint` records, and
internal power bus attachments. A power circuit is considered handed off to
NetBox only when a `PowerHandoffPoint` targets a real `dcim.PowerPort`.

Physical placement is modeled inside this plugin with `SpatialFrame` and
`SpatialPlacement`. The plugin no longer depends on `netbox_floorplan` for
location semantics or layout-aware behavior.

Current operator workflows include:

- bulk staged circuit import and optional `PowerPort` binding via
  `services.import_workflows`;
- direct Madison CAD/DWG package upload from the underlay review page, producing
  source-document, source-layer, coordinate-frame, physical-space, placement,
  and provenance records for operator approval;
- plant-to-NetBox handoff completeness checks via `services.completeness`;
- persisted topology, layout, and capacity validation actions from the power
  system detail page;
- reserved-load capacity planning and maintenance impact summaries via
  `services.operational_planning`;
- interactive spatial trace highlighting in the power system layout view.

For the planned electrical domain model and longer implementation direction, see
`netbox_power_plant_plugin_proposal.md`. For the broader future-state
architecture that recasts the plugin as a physical-site modeling system with
power as one discipline, see
`netbox_physical_plant_future_state_architecture.md`.

## Requirements

- NetBox 4.2.x (4.2.0 – 4.2.99)
- Python 3.12+
- CAD import/conversion support is mandatory. The base package installs
  `ezdwg[dxf]` so the site modeling workflow can ingest DWG packages directly.
- NetBox deployments that expose the CAD upload workflow must allow large
  request bodies at their reverse proxy or NGINX Unit layer, and must raise
  Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` above the intended CAD package size.
  Deployments that allow direct multi-file selection should also raise
  `DATA_UPLOAD_MAX_NUMBER_FILES` above the expected CAD file count. The plugin
  accepts up to 500 supported CAD files, a 2 GiB CAD upload package, and 2 GiB
  of extracted CAD contents.

## Installation

```bash
pip install -e ".[test]"
```

Add `netbox_power_plant` to the `PLUGINS` list in your NetBox `configuration.py`:

```python
PLUGINS = ['netbox_power_plant']
```

No companion floorplan plugin is required. Layout and placement development
should use the plugin-native spatial models and services.

## Development

See `LOCAL_DEV_SETUP.md` for the local development workflow.

The `devrun` wrapper uses a repo-specific Docker Compose project name,
`netbox_power_plant_devrun`, and a repo-specific state directory,
`~/.config/netbox-power-plant-dev`, so this repo does not collide with the
existing `netbox_rpki` or `netbox_multiplanar_fabrics` environments.
That Compose project name yields unique container names such as
`netbox_power_plant_devrun-postgres-1` and
`netbox_power_plant_devrun-redis-1`, and the default host bindings are also
repo-specific: PostgreSQL on `127.0.0.1:5434` and Redis on `127.0.0.1:6381`.

## License

Apache License 2.0
