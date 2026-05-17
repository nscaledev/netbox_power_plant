# Local Development Setup

This project follows the same local dev pattern as `netbox_rpki` and
`netbox_multiplanar_fabrics`.

## Expected environment

- NetBox source tree at `$HOME/src/netbox-v4.2.3/netbox`
- Virtualenv at `$HOME/.virtualenvs/netbox-4.2.3`
- Floorplan plugin checkout at `$HOME/src/netbox-floorplan-plugin` for
  layout-aware development
- Docker for PostgreSQL and Redis
- `devrun` uses its own Docker Compose project name, `netbox_power_plant_devrun`,
  so its local volumes and generated container names do not collide with other
  NetBox plugin repos
- the default host ports are also repo-specific: PostgreSQL on `5434` and Redis
  on `6381`

## One-time setup

```bash
cd ~/src/netbox_power_plant
source ~/.virtualenvs/netbox-4.2.3/bin/activate
pip install -e ".[test]"
pip install -e ~/src/netbox-floorplan-plugin
```

## Floorplan dependency

Layout-aware power-plant work expects the companion floorplan plugin package
`netbox-floorplan-plugin` to be installed into the same virtualenv and enabled
in NetBox as `netbox_floorplan`.

The baseline NetBox checkout also has its own isolated `devrun` wrapper and
host ports so it does not share PostgreSQL or Redis state with this plugin
repo. Start that baseline runtime from the NetBox checkout before applying the
floorplan plugin's migrations or static assets:

```bash
cd ~/src/netbox-v4.2.3/netbox
./devrun/dev.sh start
./devrun/dev.sh status
```

The default baseline host ports are PostgreSQL on `5435` and Redis on `6382`.

Once those baseline services are up, apply the floorplan plugin's migrations
and static assets from the NetBox checkout:

```bash
cd ~/src/netbox-v4.2.3/netbox
~/.virtualenvs/netbox-4.2.3/bin/python manage.py migrate netbox_floorplan
~/.virtualenvs/netbox-4.2.3/bin/python manage.py collectstatic --noinput
```

Use `./devrun/dev.sh stop` from the baseline checkout when you want to tear
down those baseline services.

## Common commands

```bash
./devrun/dev.sh start
./devrun/dev.sh stop
./devrun/dev.sh status
./devrun/dev.sh test fast
./devrun/dev.sh test contract
./devrun/dev.sh test full
```

## Notes

- `./dev.sh start` writes a repo-specific NetBox development configuration that
  enables `netbox_power_plant` only when `NETBOX_POWER_PLANT_ENABLE=1`.
- `./dev.sh test ...` uses `netbox_power_plant.tests.netbox_configuration`
  rather than the development `configuration.py` path.
- The generated local state lives under `~/.config/netbox-power-plant-dev`.
- You can override the repo-specific host ports through `POSTGRES_HOST_PORT`
  and `REDIS_HOST_PORT` in `devrun/.env` or your shell environment.
- `netbox_power_plant` must degrade cleanly when `netbox_floorplan` is absent
  or disabled. Floorplan-aware services should report no resolved layout context
  instead of breaking topology-only workflows.
