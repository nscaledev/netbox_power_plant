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
