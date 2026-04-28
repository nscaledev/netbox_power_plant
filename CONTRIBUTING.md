# Contributing

Contributions are welcome, and they are greatly appreciated.

## Get Started

For local development setup instructions, see `LOCAL_DEV_SETUP.md`.

This repo follows the same general local-development pattern as `netbox_rpki`
and `netbox_multiplanar_fabrics`, but it has its own `devrun` wrapper,
Compose project name, state directory, and plugin-specific environment flags.

Layout-aware development also assumes the floorplan plugin package
`netbox-floorplan-plugin` is installed into the pinned NetBox virtualenv and is
enabled in NetBox as `netbox_floorplan`.

In the standard workspace layout, the baseline NetBox checkout at
`~/src/netbox-v4.5.7/netbox` uses its own `./devrun/dev.sh` wrapper with
PostgreSQL on `5435` and Redis on `6382`; bring that baseline runtime up before
running floorplan-related management commands there.

When changing floorplan-aware code paths, keep the graceful-degradation
contract intact: `netbox_power_plant` should continue to function for
topology-only workflows even when `netbox_floorplan` is unavailable.

### Generating Migrations Locally

In the standard local workspace layout from `LOCAL_DEV_SETUP.md`, NetBox's
management entry point lives at:

```bash
~/src/netbox-v4.5.7/netbox/manage.py
```

Use the pinned NetBox virtualenv and the plugin's test configuration when
generating plugin migrations:

```bash
~/.virtualenvs/netbox-4.5.7/bin/python \
    ~/src/netbox-v4.5.7/netbox/manage.py \
    makemigrations netbox_power_plant \
    --settings=netbox_power_plant.tests.netbox_configuration
```

If your local checkout or virtualenv uses a different pinned NetBox version,
adjust the `netbox-v4.5.7` and `netbox-4.5.7` path segments accordingly.

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

For floorplan-aware slices, add focused tests around service-level feature
detection and scope resolution before widening into NetBox view coverage.

## Pull Request Guidelines

1. The pull request should include tests when behavior changes.
2. If the pull request adds or changes functionality, update the docs in the
   same slice.
3. The pull request should work for Python 3.12, 3.13, and 3.14.
