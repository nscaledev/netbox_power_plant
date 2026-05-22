from utilities.choices import ChoiceSet


class PowerSystemScopeChoices(ChoiceSet):
    key = 'PowerSystem.scope_type'

    SCOPE_CAMPUS = 'campus'
    SCOPE_BUILDING = 'building'
    SCOPE_HALL = 'hall'
    SCOPE_ROOM = 'room'
    SCOPE_CUSTOM = 'custom'

    CHOICES = [
        (SCOPE_CAMPUS, 'Campus'),
        (SCOPE_BUILDING, 'Building'),
        (SCOPE_HALL, 'Hall'),
        (SCOPE_ROOM, 'Room'),
        (SCOPE_CUSTOM, 'Custom'),
    ]


class SupplyTypeChoices(ChoiceSet):
    key = 'PowerPlant.supply_type'

    SUPPLY_AC = 'ac'
    SUPPLY_DC = 'dc'
    SUPPLY_MIXED = 'mixed'

    CHOICES = [
        (SUPPLY_AC, 'AC'),
        (SUPPLY_DC, 'DC'),
        (SUPPLY_MIXED, 'Mixed'),
    ]


class InternalPowerBusRoleChoices(ChoiceSet):
    key = 'InternalPowerBus.bus_role'

    ROLE_BUSBAR = 'busbar'
    ROLE_BACKPLANE = 'backplane'
    ROLE_CUSTOM = 'custom'

    CHOICES = [
        (ROLE_BUSBAR, 'Busbar'),
        (ROLE_BACKPLANE, 'Backplane'),
        (ROLE_CUSTOM, 'Custom'),
    ]


class InternalPowerBusAttachmentRoleChoices(ChoiceSet):
    key = 'InternalPowerBusAttachment.attachment_role'

    ROLE_SOURCE = 'source'
    ROLE_LOAD = 'load'

    CHOICES = [
        (ROLE_SOURCE, 'Source'),
        (ROLE_LOAD, 'Load'),
    ]


class DesignStateChoices(ChoiceSet):
    key = 'PowerPlant.design_state'

    STATE_PLANNED = 'planned'
    STATE_BUILD_READY = 'build-ready'
    STATE_ACTIVE = 'active'
    STATE_DECOMMISSIONING = 'decommissioning'

    CHOICES = [
        (STATE_PLANNED, 'Planned'),
        (STATE_BUILD_READY, 'Build-ready'),
        (STATE_ACTIVE, 'Active'),
        (STATE_DECOMMISSIONING, 'Decommissioning'),
    ]


class PlacementScopeChoices(ChoiceSet):
    key = 'ElectricalNodePlacement.placement_scope_type'

    SCOPE_SITE = 'site'
    SCOPE_LOCATION = 'location'

    CHOICES = [
        (SCOPE_SITE, 'Site'),
        (SCOPE_LOCATION, 'Location'),
    ]


class PlacementSymbolKindChoices(ChoiceSet):
    key = 'ElectricalNodePlacement.symbol_kind'

    KIND_EQUIPMENT = 'equipment'
    KIND_SOURCE = 'source'
    KIND_DISTRIBUTION = 'distribution'
    KIND_RACK_BOUNDARY = 'rack_boundary'
    KIND_CUSTOM = 'custom'

    CHOICES = [
        (KIND_EQUIPMENT, 'Equipment'),
        (KIND_SOURCE, 'Source'),
        (KIND_DISTRIBUTION, 'Distribution'),
        (KIND_RACK_BOUNDARY, 'Rack Boundary'),
        (KIND_CUSTOM, 'Custom'),
    ]


class PlacementLabelModeChoices(ChoiceSet):
    key = 'ElectricalNodePlacement.label_mode'

    MODE_NAME = 'name'
    MODE_NAME_KIND = 'name_kind'
    MODE_HIDDEN = 'hidden'

    CHOICES = [
        (MODE_NAME, 'Name'),
        (MODE_NAME_KIND, 'Name + Kind'),
        (MODE_HIDDEN, 'Hidden'),
    ]


class SpatialAxisOrientationChoices(ChoiceSet):
    key = 'SpatialFrame.axis_orientation'

    ORIENTATION_LOWER_LEFT_X_RIGHT_Y_UP = 'lower-left-x-right-y-up'
    ORIENTATION_UPPER_LEFT_X_RIGHT_Y_DOWN = 'upper-left-x-right-y-down'

    CHOICES = [
        (ORIENTATION_LOWER_LEFT_X_RIGHT_Y_UP, 'Lower-left, X right, Y up'),
        (ORIENTATION_UPPER_LEFT_X_RIGHT_Y_DOWN, 'Upper-left, X right, Y down'),
    ]


class SpatialAnchorChoices(ChoiceSet):
    key = 'SpatialPlacement.anchor'

    ANCHOR_CENTER = 'center'
    ANCHOR_LOWER_LEFT = 'lower-left'
    ANCHOR_UPPER_LEFT = 'upper-left'
    ANCHOR_LOWER_RIGHT = 'lower-right'
    ANCHOR_UPPER_RIGHT = 'upper-right'

    CHOICES = [
        (ANCHOR_CENTER, 'Center'),
        (ANCHOR_LOWER_LEFT, 'Lower left'),
        (ANCHOR_UPPER_LEFT, 'Upper left'),
        (ANCHOR_LOWER_RIGHT, 'Lower right'),
        (ANCHOR_UPPER_RIGHT, 'Upper right'),
    ]


class SpatialPlacementKindChoices(ChoiceSet):
    key = 'SpatialPlacement.placement_kind'

    KIND_PHYSICAL = 'physical'
    KIND_SCHEMATIC = 'schematic'
    KIND_LOGICAL = 'logical'
    KIND_INFERRED = 'inferred'

    CHOICES = [
        (KIND_PHYSICAL, 'Physical'),
        (KIND_SCHEMATIC, 'Schematic'),
        (KIND_LOGICAL, 'Logical'),
        (KIND_INFERRED, 'Inferred'),
    ]


class SpatialConfidenceChoices(ChoiceSet):
    key = 'SpatialPlacement.confidence'

    CONFIDENCE_AUTHORITATIVE = 'authoritative'
    CONFIDENCE_DERIVED = 'derived'
    CONFIDENCE_PROVISIONAL = 'provisional'
    CONFIDENCE_UNKNOWN = 'unknown'

    CHOICES = [
        (CONFIDENCE_AUTHORITATIVE, 'Authoritative'),
        (CONFIDENCE_DERIVED, 'Derived'),
        (CONFIDENCE_PROVISIONAL, 'Provisional'),
        (CONFIDENCE_UNKNOWN, 'Unknown'),
    ]


class PlantDisciplineChoices(ChoiceSet):
    key = 'PhysicalPlant.discipline'

    DISCIPLINE_ARCHITECTURAL = 'architectural'
    DISCIPLINE_ELECTRICAL = 'electrical'
    DISCIPLINE_MECHANICAL = 'mechanical'
    DISCIPLINE_TELECOM = 'telecom'
    DISCIPLINE_FIBER = 'fiber'
    DISCIPLINE_GROUNDING = 'grounding'
    DISCIPLINE_PATHWAY = 'pathway'
    DISCIPLINE_STRUCTURAL = 'structural'
    DISCIPLINE_RACK_LAYOUT = 'rack_layout'
    DISCIPLINE_MIXED = 'mixed'
    DISCIPLINE_CUSTOM = 'custom'

    CHOICES = [
        (DISCIPLINE_ARCHITECTURAL, 'Architectural'),
        (DISCIPLINE_ELECTRICAL, 'Electrical'),
        (DISCIPLINE_MECHANICAL, 'Mechanical'),
        (DISCIPLINE_TELECOM, 'Telecom'),
        (DISCIPLINE_FIBER, 'Fiber'),
        (DISCIPLINE_GROUNDING, 'Grounding'),
        (DISCIPLINE_PATHWAY, 'Pathway'),
        (DISCIPLINE_STRUCTURAL, 'Structural'),
        (DISCIPLINE_RACK_LAYOUT, 'Rack layout'),
        (DISCIPLINE_MIXED, 'Mixed'),
        (DISCIPLINE_CUSTOM, 'Custom'),
    ]


class PlantSourceTypeChoices(ChoiceSet):
    key = 'PlantSourceDocument.source_type'

    TYPE_PDF = 'pdf'
    TYPE_SVG = 'svg'
    TYPE_CAD_EXPORT = 'cad_export'
    TYPE_WORKBOOK = 'workbook'
    TYPE_CSV = 'csv'
    TYPE_MARKDOWN = 'markdown'
    TYPE_MANUAL = 'manual'
    TYPE_OTHER = 'other'

    CHOICES = [
        (TYPE_PDF, 'PDF'),
        (TYPE_SVG, 'SVG'),
        (TYPE_CAD_EXPORT, 'CAD export'),
        (TYPE_WORKBOOK, 'Workbook'),
        (TYPE_CSV, 'CSV'),
        (TYPE_MARKDOWN, 'Markdown'),
        (TYPE_MANUAL, 'Manual'),
        (TYPE_OTHER, 'Other'),
    ]


class PlantSourceLayerKindChoices(ChoiceSet):
    key = 'PlantSourceLayer.layer_kind'

    KIND_GEOMETRY = 'geometry'
    KIND_ANNOTATION = 'annotation'
    KIND_EQUIPMENT = 'equipment'
    KIND_ROOM_BOUNDARY = 'room_boundary'
    KIND_RACK_LAYOUT = 'rack_layout'
    KIND_CIRCUIT = 'circuit'
    KIND_PATHWAY = 'pathway'
    KIND_GROUNDING = 'grounding'
    KIND_MECHANICAL = 'mechanical'
    KIND_UNKNOWN = 'unknown'

    CHOICES = [
        (KIND_GEOMETRY, 'Geometry'),
        (KIND_ANNOTATION, 'Annotation'),
        (KIND_EQUIPMENT, 'Equipment'),
        (KIND_ROOM_BOUNDARY, 'Room boundary'),
        (KIND_RACK_LAYOUT, 'Rack layout'),
        (KIND_CIRCUIT, 'Circuit'),
        (KIND_PATHWAY, 'Pathway'),
        (KIND_GROUNDING, 'Grounding'),
        (KIND_MECHANICAL, 'Mechanical'),
        (KIND_UNKNOWN, 'Unknown'),
    ]


class PlantExtractionMethodChoices(ChoiceSet):
    key = 'PlantProvenance.extraction_method'

    METHOD_MANUAL = 'manual'
    METHOD_PARSED_SVG = 'parsed_svg'
    METHOD_PARSED_PDF = 'parsed_pdf'
    METHOD_WORKBOOK = 'workbook'
    METHOD_CSV = 'csv'
    METHOD_CAD_EXPORT = 'cad_export'
    METHOD_RECONCILIATION = 'reconciliation'
    METHOD_GENERATED = 'generated'
    METHOD_UNKNOWN = 'unknown'

    CHOICES = [
        (METHOD_MANUAL, 'Manual'),
        (METHOD_PARSED_SVG, 'Parsed SVG'),
        (METHOD_PARSED_PDF, 'Parsed PDF'),
        (METHOD_WORKBOOK, 'Workbook'),
        (METHOD_CSV, 'CSV'),
        (METHOD_CAD_EXPORT, 'CAD export'),
        (METHOD_RECONCILIATION, 'Reconciliation'),
        (METHOD_GENERATED, 'Generated'),
        (METHOD_UNKNOWN, 'Unknown'),
    ]


class PhysicalSpaceKindChoices(ChoiceSet):
    key = 'PhysicalSpace.space_kind'

    KIND_CAMPUS = 'campus'
    KIND_BUILDING = 'building'
    KIND_FLOOR = 'floor'
    KIND_ROOM = 'room'
    KIND_GALLERY = 'gallery'
    KIND_DATA_HALL = 'data_hall'
    KIND_ELECTRICAL_ROOM = 'electrical_room'
    KIND_MECHANICAL_ROOM = 'mechanical_room'
    KIND_YARD = 'yard'
    KIND_AISLE = 'aisle'
    KIND_ROW_ZONE = 'row_zone'
    KIND_RACK_SLOT = 'rack_slot'
    KIND_WALL_ZONE = 'wall_zone'
    KIND_CONTAINMENT_ZONE = 'containment_zone'
    KIND_CLEARANCE_ZONE = 'clearance_zone'
    KIND_CUSTOM = 'custom'

    CHOICES = [
        (KIND_CAMPUS, 'Campus'),
        (KIND_BUILDING, 'Building'),
        (KIND_FLOOR, 'Floor'),
        (KIND_ROOM, 'Room'),
        (KIND_GALLERY, 'Gallery'),
        (KIND_DATA_HALL, 'Data hall'),
        (KIND_ELECTRICAL_ROOM, 'Electrical room'),
        (KIND_MECHANICAL_ROOM, 'Mechanical room'),
        (KIND_YARD, 'Yard'),
        (KIND_AISLE, 'Aisle'),
        (KIND_ROW_ZONE, 'Row zone'),
        (KIND_RACK_SLOT, 'Rack slot'),
        (KIND_WALL_ZONE, 'Wall zone'),
        (KIND_CONTAINMENT_ZONE, 'Containment zone'),
        (KIND_CLEARANCE_ZONE, 'Clearance zone'),
        (KIND_CUSTOM, 'Custom'),
    ]


class PhysicalElementKindChoices(ChoiceSet):
    key = 'PhysicalElement.element_kind'

    KIND_RACK_FOOTPRINT = 'rack_footprint'
    KIND_RACK_SIDECAR = 'rack_sidecar'
    KIND_TRANSFORMER = 'transformer'
    KIND_GENERATOR = 'generator'
    KIND_SWITCHGEAR = 'switchgear'
    KIND_SWITCHBOARD = 'switchboard'
    KIND_PANELBOARD = 'panelboard'
    KIND_RPP = 'rpp'
    KIND_UPS = 'ups'
    KIND_UOP = 'uop'
    KIND_PDU = 'pdu'
    KIND_CABLE_TRAY = 'cable_tray'
    KIND_CONDUIT = 'conduit'
    KIND_BUSWAY = 'busway'
    KIND_DUCT = 'duct'
    KIND_PIPE = 'pipe'
    KIND_GROUNDING_BAR = 'grounding_bar'
    KIND_WALL = 'wall'
    KIND_DOOR = 'door'
    KIND_COLUMN = 'column'
    KIND_EQUIPMENT_PAD = 'equipment_pad'
    KIND_CRAH = 'crah'
    KIND_CDU = 'cdu'
    KIND_ANNOTATION = 'annotation'
    KIND_CUSTOM = 'custom'

    CHOICES = [
        (KIND_RACK_FOOTPRINT, 'Rack footprint'),
        (KIND_RACK_SIDECAR, 'Rack sidecar'),
        (KIND_TRANSFORMER, 'Transformer'),
        (KIND_GENERATOR, 'Generator'),
        (KIND_SWITCHGEAR, 'Switchgear'),
        (KIND_SWITCHBOARD, 'Switchboard'),
        (KIND_PANELBOARD, 'Panelboard'),
        (KIND_RPP, 'Remote power panel'),
        (KIND_UPS, 'UPS'),
        (KIND_UOP, 'UOP'),
        (KIND_PDU, 'PDU'),
        (KIND_CABLE_TRAY, 'Cable tray'),
        (KIND_CONDUIT, 'Conduit'),
        (KIND_BUSWAY, 'Busway'),
        (KIND_DUCT, 'Duct'),
        (KIND_PIPE, 'Pipe'),
        (KIND_GROUNDING_BAR, 'Grounding bar'),
        (KIND_WALL, 'Wall'),
        (KIND_DOOR, 'Door'),
        (KIND_COLUMN, 'Column'),
        (KIND_EQUIPMENT_PAD, 'Equipment pad'),
        (KIND_CRAH, 'CRAH'),
        (KIND_CDU, 'CDU'),
        (KIND_ANNOTATION, 'Annotation'),
        (KIND_CUSTOM, 'Custom'),
    ]


class PhysicalObjectBindingRoleChoices(ChoiceSet):
    key = 'PhysicalObjectBinding.binding_role'

    ROLE_REPRESENTS = 'represents'
    ROLE_CONTAINS = 'contains'
    ROLE_MOUNTED_ON = 'mounted_on'
    ROLE_SERVED_BY = 'served_by'
    ROLE_SOURCE_OF_TRUTH = 'source_of_truth'
    ROLE_DERIVED_FROM = 'derived_from'
    ROLE_TOPOLOGY_NODE_FOR = 'topology_node_for'
    ROLE_INVENTORY_OBJECT_FOR = 'inventory_object_for'
    ROLE_PLACEMENT_FOR = 'placement_for'
    ROLE_CUSTOM = 'custom'

    CHOICES = [
        (ROLE_REPRESENTS, 'Represents'),
        (ROLE_CONTAINS, 'Contains'),
        (ROLE_MOUNTED_ON, 'Mounted on'),
        (ROLE_SERVED_BY, 'Served by'),
        (ROLE_SOURCE_OF_TRUTH, 'Source of truth'),
        (ROLE_DERIVED_FROM, 'Derived from'),
        (ROLE_TOPOLOGY_NODE_FOR, 'Topology node for'),
        (ROLE_INVENTORY_OBJECT_FOR, 'Inventory object for'),
        (ROLE_PLACEMENT_FOR, 'Placement for'),
        (ROLE_CUSTOM, 'Custom'),
    ]


class PowerDomainKindChoices(ChoiceSet):
    key = 'PowerDomain.kind'

    KIND_PRIMARY = 'primary'
    KIND_REDUNDANT = 'redundant'
    KIND_MAINTENANCE = 'maintenance'
    KIND_CATCHER = 'catcher'
    KIND_DC_BUS = 'dc_bus'
    KIND_CUSTOM = 'custom'

    CHOICES = [
        (KIND_PRIMARY, 'Primary'),
        (KIND_REDUNDANT, 'Redundant'),
        (KIND_MAINTENANCE, 'Maintenance'),
        (KIND_CATCHER, 'Catcher'),
        (KIND_DC_BUS, 'DC Bus'),
        (KIND_CUSTOM, 'Custom'),
    ]


class RedundancyTopologyChoices(ChoiceSet):
    key = 'RedundancyGroup.topology_type'

    TOPOLOGY_NONE = 'none'
    TOPOLOGY_N_PLUS_1 = 'n_plus_1'
    TOPOLOGY_2N = '2n'
    TOPOLOGY_2N_PLUS_1 = '2n_plus_1'
    TOPOLOGY_DISTRIBUTED = 'distributed'
    TOPOLOGY_CATCHER = 'catcher'
    TOPOLOGY_CUSTOM = 'custom'

    CHOICES = [
        (TOPOLOGY_NONE, 'None'),
        (TOPOLOGY_N_PLUS_1, 'N+1'),
        (TOPOLOGY_2N, '2N'),
        (TOPOLOGY_2N_PLUS_1, '2N+1'),
        (TOPOLOGY_DISTRIBUTED, 'Distributed'),
        (TOPOLOGY_CATCHER, 'Catcher'),
        (TOPOLOGY_CUSTOM, 'Custom'),
    ]


class NodeKindChoices(ChoiceSet):
    key = 'ElectricalNode.node_kind'

    KIND_UTILITY_SERVICE = 'utility_service'
    KIND_GENERATOR = 'generator'
    KIND_PARALLELING_GEAR = 'paralleling_gear'
    KIND_MV_SWITCHGEAR = 'mv_switchgear'
    KIND_LV_SWITCHBOARD = 'lv_switchboard'
    KIND_TRANSFORMER = 'transformer'
    KIND_ATS = 'ats'
    KIND_STS = 'sts'
    KIND_MAINTENANCE_BYPASS = 'maintenance_bypass'
    KIND_UPS = 'ups'
    KIND_BATTERY_SYSTEM = 'battery_system'
    KIND_BESS = 'bess'
    KIND_RECTIFIER = 'rectifier'
    KIND_INVERTER = 'inverter'
    KIND_PDU = 'pdu'
    KIND_RPP = 'rpp'
    KIND_PANELBOARD = 'panelboard'
    KIND_BUSWAY_RUN = 'busway_run'
    KIND_TAP_OFF_BOX = 'tap_off_box'
    KIND_RACK_CIRCUIT_TERMINATOR = 'rack_circuit_terminator'
    KIND_RACK_PDU = 'rack_pdu'
    KIND_DC_DISTRIBUTION_PANEL = 'dc_distribution_panel'
    KIND_CUSTOM = 'custom'

    CHOICES = [
        (KIND_UTILITY_SERVICE, 'Utility Service'),
        (KIND_GENERATOR, 'Generator'),
        (KIND_PARALLELING_GEAR, 'Paralleling Gear'),
        (KIND_MV_SWITCHGEAR, 'MV Switchgear'),
        (KIND_LV_SWITCHBOARD, 'LV Switchboard'),
        (KIND_TRANSFORMER, 'Transformer'),
        (KIND_ATS, 'ATS'),
        (KIND_STS, 'STS'),
        (KIND_MAINTENANCE_BYPASS, 'Maintenance Bypass'),
        (KIND_UPS, 'UPS'),
        (KIND_BATTERY_SYSTEM, 'Battery System'),
        (KIND_BESS, 'BESS'),
        (KIND_RECTIFIER, 'Rectifier'),
        (KIND_INVERTER, 'Inverter'),
        (KIND_PDU, 'PDU'),
        (KIND_RPP, 'RPP'),
        (KIND_PANELBOARD, 'Panelboard'),
        (KIND_BUSWAY_RUN, 'Busway Run'),
        (KIND_TAP_OFF_BOX, 'Tap-off Box'),
        (KIND_RACK_CIRCUIT_TERMINATOR, 'Rack Circuit Terminator'),
        (KIND_RACK_PDU, 'Rack PDU'),
        (KIND_DC_DISTRIBUTION_PANEL, 'DC Distribution Panel'),
        (KIND_CUSTOM, 'Custom'),
    ]


class PhaseModeChoices(ChoiceSet):
    key = 'ElectricalNode.phase_mode'

    MODE_SINGLE_PHASE = '1ph'
    MODE_THREE_PHASE = '3ph'
    MODE_DC = 'dc'
    MODE_MIXED = 'mixed'

    CHOICES = [
        (MODE_SINGLE_PHASE, 'Single-phase'),
        (MODE_THREE_PHASE, 'Three-phase'),
        (MODE_DC, 'DC'),
        (MODE_MIXED, 'Mixed'),
    ]


class TopologyStateChoices(ChoiceSet):
    key = 'ElectricalObject.topology_state'

    STATE_CANDIDATE = 'candidate'
    STATE_PLANNED = 'planned'
    STATE_ACTIVE = 'active'
    STATE_RETIRED = 'retired'

    CHOICES = [
        (STATE_CANDIDATE, 'Candidate'),
        (STATE_PLANNED, 'Planned'),
        (STATE_ACTIVE, 'Active'),
        (STATE_RETIRED, 'Retired'),
    ]


class CapacityReservationStatusChoices(ChoiceSet):
    key = 'CapacityReservation.status'

    STATUS_PLANNED = 'planned'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_ACTIVE = 'active'
    STATUS_RELEASED = 'released'

    CHOICES = [
        (STATUS_PLANNED, 'Planned'),
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_RELEASED, 'Released'),
    ]


class TerminalRoleChoices(ChoiceSet):
    key = 'ElectricalTerminal.terminal_role'

    ROLE_LINE = 'line'
    ROLE_LOAD = 'load'
    ROLE_BYPASS = 'bypass'
    ROLE_TIE = 'tie'
    ROLE_BATTERY = 'battery'
    ROLE_TAP = 'tap'
    ROLE_BRANCH = 'branch'
    ROLE_OUTPUT = 'output'
    ROLE_INPUT = 'input'
    ROLE_NEUTRAL = 'neutral'
    ROLE_GROUND = 'ground'
    ROLE_CUSTOM = 'custom'

    CHOICES = [
        (ROLE_LINE, 'Line'),
        (ROLE_LOAD, 'Load'),
        (ROLE_BYPASS, 'Bypass'),
        (ROLE_TIE, 'Tie'),
        (ROLE_BATTERY, 'Battery'),
        (ROLE_TAP, 'Tap'),
        (ROLE_BRANCH, 'Branch'),
        (ROLE_OUTPUT, 'Output'),
        (ROLE_INPUT, 'Input'),
        (ROLE_NEUTRAL, 'Neutral'),
        (ROLE_GROUND, 'Ground'),
        (ROLE_CUSTOM, 'Custom'),
    ]


class TerminalDirectionChoices(ChoiceSet):
    key = 'ElectricalTerminal.direction'

    DIRECTION_SOURCE = 'source'
    DIRECTION_SINK = 'sink'
    DIRECTION_BIDIRECTIONAL = 'bidirectional'

    CHOICES = [
        (DIRECTION_SOURCE, 'Source'),
        (DIRECTION_SINK, 'Sink'),
        (DIRECTION_BIDIRECTIONAL, 'Bidirectional'),
    ]


class SegmentKindChoices(ChoiceSet):
    key = 'ElectricalSegment.segment_kind'

    KIND_FEEDER = 'feeder'
    KIND_BRANCH_CIRCUIT = 'branch_circuit'
    KIND_BUSWAY_SPAN = 'busway_span'
    KIND_TAP_CONNECTION = 'tap_connection'
    KIND_INTERNAL_TIE = 'internal_tie'
    KIND_WHIP = 'whip'
    KIND_RACK_FEED = 'rack_feed'
    KIND_DC_LINK = 'dc_link'
    KIND_CUSTOM = 'custom'

    CHOICES = [
        (KIND_FEEDER, 'Feeder'),
        (KIND_BRANCH_CIRCUIT, 'Branch Circuit'),
        (KIND_BUSWAY_SPAN, 'Busway Span'),
        (KIND_TAP_CONNECTION, 'Tap Connection'),
        (KIND_INTERNAL_TIE, 'Internal Tie'),
        (KIND_WHIP, 'Whip'),
        (KIND_RACK_FEED, 'Rack Feed'),
        (KIND_DC_LINK, 'DC Link'),
        (KIND_CUSTOM, 'Custom'),
    ]


class PowerValidationRunKindChoices(ChoiceSet):
    key = 'PowerValidationRun.run_kind'

    KIND_TOPOLOGY = 'topology'
    KIND_LAYOUT = 'layout'
    KIND_PHYSICAL_PLANT = 'physical_plant'
    KIND_CAPACITY = 'capacity'
    KIND_SCENARIO = 'scenario'

    CHOICES = [
        (KIND_TOPOLOGY, 'Topology'),
        (KIND_LAYOUT, 'Layout'),
        (KIND_PHYSICAL_PLANT, 'Physical plant'),
        (KIND_CAPACITY, 'Capacity'),
        (KIND_SCENARIO, 'Scenario'),
    ]


class PowerValidationRunStatusChoices(ChoiceSet):
    key = 'PowerValidationRun.status'

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'

    CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]


class PowerFindingSeverityChoices(ChoiceSet):
    key = 'PowerFinding.severity'

    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_ERROR = 'error'
    SEVERITY_CRITICAL = 'critical'

    CHOICES = [
        (SEVERITY_INFO, 'Info'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_ERROR, 'Error'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]


class PowerFindingStatusChoices(ChoiceSet):
    key = 'PowerFinding.status'

    STATUS_OPEN = 'open'
    STATUS_SUPPRESSED = 'suppressed'
    STATUS_RESOLVED = 'resolved'

    CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_SUPPRESSED, 'Suppressed'),
        (STATUS_RESOLVED, 'Resolved'),
    ]
