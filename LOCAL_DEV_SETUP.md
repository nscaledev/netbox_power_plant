# Local Development Setup

This project follows the same local dev pattern as `netbox_rpki` and
`netbox_multiplanar_fabrics`.

## Expected environment

- NetBox source tree at `$HOME/src/netbox-v4.2.3/netbox`
- Virtualenv at `$HOME/.virtualenvs/netbox-4.2.3`
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
```

CAD/DWG support is installed by default because direct CAD ingest is part of the
site modeling workflow. Generate the Madison CAD review artifacts with:

```bash
python scripts/report_madison_cad_calibration.py \
  --cad-dir "/path/to/2026.04.02_Enovum MAD1_Electical CAD" \
  --out-dir "/path/to/electrical/generated"
```

The same CAD package can be uploaded from the NetBox UI at
`/plugins/power-plant/madison-underlay-review/`. Operators can upload a ZIP of
the CAD folder, or select the DWG/PCP files together. The total uploaded package
is limited to 2 GiB, and the extracted CAD contents are also limited to 2 GiB.
The plugin stores the package under NetBox `MEDIA_ROOT`, then creates or
refreshes the Madison source document, source sheets/layers, site coordinate
plane, current-building footprint, and provenance records from the stored DWG
package. Creating a new NetBox site also requires the normal `dcim.add_site`
permission.

## Spatial placement development

Layout-aware power-plant work uses plugin-native spatial models:

- `SpatialFrame` defines a coordinate frame for a site, room, drawing, or other
  placement scope.
- `SpatialPlacement` binds power-plant objects to coordinates in one of those
  frames.
- `services.cad_calibration` uses CAD/DWG-derived bounds to build lower-left,
  X-right, Y-up coordinate grids. The hand-built Madison SVG should be treated
  as an approximate overlay, not as the source of physical scale.

Do not install or enable `netbox_floorplan` for this plugin's placement
workflow. The power-plant plugin owns its own spatial semantics so electrical
equipment, rack handoff points, and future layout views have a consistent
relational model.

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
- `netbox_power_plant` does not require `netbox_floorplan`. Placement-related
  services should use `SpatialFrame` and `SpatialPlacement`.
