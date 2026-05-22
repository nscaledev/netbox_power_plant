# Contributing

Contributions are welcome, and they are greatly appreciated.

## Get Started

For local development setup instructions, see `LOCAL_DEV_SETUP.md`.

This repo follows the same general local-development pattern as `netbox_rpki`
and `netbox_multiplanar_fabrics`, but it has its own `devrun` wrapper,
Compose project name, state directory, and plugin-specific environment flags.

In the standard workspace layout, the baseline NetBox checkout at
`~/src/netbox-v4.2.3/netbox` uses its own `./devrun/dev.sh` wrapper with
PostgreSQL on `5435` and Redis on `6382`.

Layout-aware development uses `netbox_power_plant`'s own `SpatialFrame` and
`SpatialPlacement` models. Do not add a dependency on `netbox_floorplan`; the
plugin owns its own placement semantics.

### Generating Migrations Locally

In the standard local workspace layout from `LOCAL_DEV_SETUP.md`, NetBox's
management entry point lives at:

```bash
~/src/netbox-v4.2.3/netbox/manage.py
```

Use the pinned NetBox virtualenv and the plugin's test configuration when
generating plugin migrations:

```bash
~/.virtualenvs/netbox-4.2.3/bin/python \
    ~/src/netbox-v4.2.3/netbox/manage.py \
    makemigrations netbox_power_plant \
    --settings=netbox_power_plant.tests.netbox_configuration
```

If your local checkout or virtualenv uses a different pinned NetBox version,
adjust the `netbox-v4.2.3` and `netbox-4.2.3` path segments accordingly.

### Test Lane Expectations

Use the `devrun` wrapper for local test runs:

```bash
cd ~/src/netbox_power_plant/devrun
./dev.sh test fast
./dev.sh test contract
./dev.sh test full
```

Lane intent:

- `fast`: low-cost plugin registration and URL smoke checks
- `contract`: plugin configuration and runtime wiring checks
- `full`: the full plugin test package

For spatial-placement slices, add focused tests around service-level coordinate
resolution, placement validation, and scope behavior before widening into
NetBox view coverage.

## Pull Request Guidelines

1. The pull request should include tests when behavior changes.
2. If the pull request adds or changes functionality, update the docs in the
   same slice.
3. The pull request should work for Python 3.12, 3.13, and 3.14.
