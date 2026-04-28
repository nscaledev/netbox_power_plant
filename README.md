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

The current scaffold is intentionally minimal. It provides:

- an installable NetBox plugin package;
- a dedicated `devrun` stack with repo-specific state and Compose naming;
- a test configuration that loads the plugin through NetBox's testing settings;
- initial contributor docs aligned with the other plugin repos in this workspace.

For the planned domain model and longer implementation direction, see
`netbox_power_plant_plugin_proposal.md`.

## Requirements

- NetBox 4.5.0+
- Python 3.12+

## Installation

```bash
pip install -e ".[test]"
```

For layout-aware development, install the floorplan plugin package into the
same NetBox virtual environment:

```bash
pip install -e ~/src/netbox-floorplan-plugin
```

Add `netbox_power_plant` to the `PLUGINS` list in your NetBox `configuration.py`:

```python
PLUGINS = ['netbox_power_plant']
```

Layout-aware features use the floorplan plugin package
`netbox-floorplan-plugin`, exposed to NetBox as `netbox_floorplan`. In the
current local baseline, `netbox_floorplan` is enabled in the pinned NetBox 4.5.7
configuration. `netbox_power_plant` still degrades cleanly when that plugin is
missing or disabled: the electrical topology surfaces remain available, while
floorplan-aware adapter results simply report no resolved floorplan context.

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
