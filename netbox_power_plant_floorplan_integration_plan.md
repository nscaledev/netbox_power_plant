# Superseded: Floorplan Integration Plan

This document is intentionally retained as a tombstone for the earlier
`netbox_floorplan` integration direction.

Current direction:

- `netbox_power_plant` does not depend on `netbox_floorplan`.
- Physical location is represented by plugin-native `SpatialFrame` and
  `SpatialPlacement` models.
- Facility electrical topology remains in `ElectricalNode`,
  `ElectricalTerminal`, and `ElectricalSegment`.
- The only NetBox-native power boundary is `dcim.PowerPort`.
- Facility power is handed off to NetBox through `PowerHandoffPoint`, which
  targets a real `dcim.PowerPort`.

The old plan proposed a floorplan adapter service, floorplan-backed layout
views, and `RackDeliveryPoint` as the rack-boundary object. Those ideas have
been superseded. Future placement work should build on the native spatial
models instead of reintroducing a dependency on `netbox_floorplan`.
