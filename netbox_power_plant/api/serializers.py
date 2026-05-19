from dcim.models import Device, Location, PowerPort, Rack, Site
from rest_framework import serializers
from rest_framework.serializers import ValidationError

from netbox.api.fields import ChoiceField, SerializedPKRelatedField
try:
    from netbox.api.serializers import OrganizationalModelSerializer, WritableNestedSerializer
except ImportError:
    from netbox.api.serializers import NetBoxModelSerializer, WritableNestedSerializer

    class OrganizationalModelSerializer(NetBoxModelSerializer):
        comments = serializers.SerializerMethodField()

        def get_comments(self, obj):
            return getattr(obj, 'comments', '')

from netbox_power_plant.choices import (
    DesignStateChoices,
    InternalPowerBusAttachmentRoleChoices,
    InternalPowerBusRoleChoices,
    NodeKindChoices,
    PhaseModeChoices,
    PlacementLabelModeChoices,
    PlacementScopeChoices,
    PlacementSymbolKindChoices,
    PowerDomainKindChoices,
    PowerSystemScopeChoices,
    RedundancyTopologyChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TerminalRoleChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    InternalPowerBus,
    InternalPowerBusAttachment,
    PowerDomain,
    PowerSystem,
    RackDeliveryPoint,
    RedundancyGroup,
)


class NestedPowerSystemSerializer(WritableNestedSerializer):

    class Meta:
        model = PowerSystem
        fields = ('id', 'url', 'display', 'name', 'slug')
        brief_fields = fields


class NestedPowerDomainSerializer(WritableNestedSerializer):

    class Meta:
        model = PowerDomain
        fields = ('id', 'url', 'display', 'name', 'slug', 'code')
        brief_fields = fields


class NestedElectricalNodeSerializer(WritableNestedSerializer):

    class Meta:
        model = ElectricalNode
        fields = ('id', 'url', 'display', 'name', 'slug', 'node_kind')
        brief_fields = fields


class NestedElectricalTerminalSerializer(WritableNestedSerializer):

    class Meta:
        model = ElectricalTerminal
        fields = ('id', 'url', 'display', 'name', 'slug', 'terminal_role', 'direction')
        brief_fields = fields


class NestedRackSerializer(WritableNestedSerializer):

    class Meta:
        model = Rack
        fields = ('id', 'url', 'display', 'name')
        brief_fields = fields


class NestedDeviceSerializer(WritableNestedSerializer):

    class Meta:
        model = Device
        fields = ('id', 'url', 'display', 'name')
        brief_fields = fields


class NestedPowerPortSerializer(WritableNestedSerializer):

    class Meta:
        model = PowerPort
        fields = ('id', 'url', 'display', 'name')
        brief_fields = fields


class NestedSiteSerializer(WritableNestedSerializer):

    class Meta:
        model = Site
        fields = ('id', 'url', 'display', 'name', 'slug')
        brief_fields = fields


class NestedLocationSerializer(WritableNestedSerializer):

    class Meta:
        model = Location
        fields = ('id', 'url', 'display', 'name', 'slug')
        brief_fields = fields


class NestedRedundancyGroupSerializer(WritableNestedSerializer):

    class Meta:
        model = RedundancyGroup
        fields = ('id', 'url', 'display', 'name', 'slug')
        brief_fields = fields


class NestedInternalPowerBusSerializer(WritableNestedSerializer):

    class Meta:
        model = InternalPowerBus
        fields = ('id', 'url', 'display', 'name', 'slug')
        brief_fields = fields


class PowerSystemSerializer(OrganizationalModelSerializer):
    scope_type = ChoiceField(choices=PowerSystemScopeChoices, required=False)
    upstream_supply_type = ChoiceField(choices=SupplyTypeChoices, required=False)
    design_state = ChoiceField(choices=DesignStateChoices, required=False)

    class Meta:
        model = PowerSystem
        fields = (
            'id',
            'url',
            'display_url',
            'display',
            'name',
            'slug',
            'site',
            'location',
            'scope_type',
            'upstream_supply_type',
            'nominal_distribution_voltage',
            'frequency_hz',
            'is_template_derived',
            'design_state',
            'description',
            'comments',
            'tags',
            'custom_fields',
            'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'scope_type', 'design_state')


class PowerDomainSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    kind = ChoiceField(choices=PowerDomainKindChoices, required=False)

    class Meta:
        model = PowerDomain
        fields = (
            'id',
            'url',
            'display_url',
            'display',
            'name',
            'slug',
            'power_system',
            'code',
            'kind',
            'color',
            'priority',
            'failure_isolation_depth',
            'description',
            'comments',
            'tags',
            'custom_fields',
            'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'code', 'kind')


class RedundancyGroupSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    power_domains = SerializedPKRelatedField(
        serializer=NestedPowerDomainSerializer,
        queryset=PowerDomain.objects.all(),
        many=True,
        required=False,
    )
    topology_type = ChoiceField(choices=RedundancyTopologyChoices, required=False)

    class Meta:
        model = RedundancyGroup
        fields = (
            'id',
            'url',
            'display_url',
            'display',
            'name',
            'slug',
            'power_system',
            'power_domains',
            'topology_type',
            'min_distinct_paths',
            'requires_domain_isolation',
            'description',
            'notes_on_failover',
            'comments',
            'tags',
            'custom_fields',
            'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'topology_type', 'min_distinct_paths')

    def validate(self, data):
        data = super().validate(data)
        power_system = data.get('power_system', getattr(self.instance, 'power_system', None))
        power_domains = data.get('power_domains')

        if power_system and power_domains:
            mismatched_domains = [domain for domain in power_domains if domain.power_system_id != power_system.pk]
            if mismatched_domains:
                raise ValidationError({'power_domains': 'Selected domains must belong to the selected power system.'})

        return data


class ElectricalNodeSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    parent_node = NestedElectricalNodeSerializer(nested=True, required=False, allow_null=True)
    node_kind = ChoiceField(choices=NodeKindChoices, required=False)
    install_state = ChoiceField(choices=TopologyStateChoices, required=False)
    topology_state = ChoiceField(choices=TopologyStateChoices, required=False)
    phase_mode = ChoiceField(choices=PhaseModeChoices, required=False)

    class Meta:
        model = ElectricalNode
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'site', 'location', 'parent_node',
            'node_kind', 'equipment_role', 'manufacturer', 'model', 'serial', 'asset_tag', 'install_state',
            'topology_state', 'rated_input_voltage_min', 'rated_input_voltage_max', 'rated_output_voltage_min',
            'rated_output_voltage_max', 'frequency_hz', 'phase_mode', 'pole_count', 'installed_capacity_kw',
            'usable_capacity_kw', 'derating_factor', 'reserve_margin_pct', 'telemetry_source_ref', 'description',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'node_kind', 'topology_state')


class ElectricalTerminalSerializer(OrganizationalModelSerializer):
    node = NestedElectricalNodeSerializer(nested=True)
    terminal_role = ChoiceField(choices=TerminalRoleChoices, required=False)
    direction = ChoiceField(choices=TerminalDirectionChoices, required=False)
    supply_type = ChoiceField(choices=SupplyTypeChoices, required=False)

    class Meta:
        model = ElectricalTerminal
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'node', 'terminal_role', 'direction',
            'supply_type', 'voltage_nominal', 'amperage_rating', 'phase_designation', 'pole_designation',
            'connector_type', 'is_protected', 'is_switchable', 'is_monitored', 'position_index', 'description',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'terminal_role', 'direction', 'supply_type')


class ElectricalSegmentSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    power_domain = NestedPowerDomainSerializer(nested=True, required=False, allow_null=True)
    from_terminal = NestedElectricalTerminalSerializer(nested=True)
    to_terminal = NestedElectricalTerminalSerializer(nested=True)
    segment_kind = ChoiceField(choices=SegmentKindChoices, required=False)
    path_state = ChoiceField(choices=TopologyStateChoices, required=False)

    class Meta:
        model = ElectricalSegment
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'power_domain',
            'from_terminal', 'to_terminal', 'segment_kind', 'path_state', 'length_m', 'conductor_material',
            'conductor_count', 'awg_or_mm2', 'insulation_type', 'breaker_size_a', 'voltage_nominal',
            'ampacity_a', 'derated_ampacity_a', 'description', 'comments', 'tags', 'custom_fields', 'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'segment_kind', 'path_state')


class RackDeliveryPointSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    electrical_node = NestedElectricalNodeSerializer(nested=True, required=False, allow_null=True)
    electrical_terminal = NestedElectricalTerminalSerializer(nested=True, required=False, allow_null=True)
    rack = NestedRackSerializer(nested=True, required=False, allow_null=True)
    device = NestedDeviceSerializer(nested=True, required=False, allow_null=True)
    power_port = NestedPowerPortSerializer(nested=True, required=False, allow_null=True)
    expected_redundancy_group = NestedRedundancyGroupSerializer(nested=True, required=False, allow_null=True)
    design_state = ChoiceField(choices=DesignStateChoices, required=False)

    class Meta:
        model = RackDeliveryPoint
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'electrical_node',
            'electrical_terminal', 'rack', 'device', 'power_port', 'expected_redundancy_group', 'delivery_role',
            'feed_label', 'design_state', 'description', 'comments', 'tags', 'custom_fields', 'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'feed_label', 'design_state')

    def validate(self, data):
        data = super().validate(data)
        power_system = data.get('power_system', getattr(self.instance, 'power_system', None))
        electrical_node = data.get('electrical_node', getattr(self.instance, 'electrical_node', None))
        electrical_terminal = data.get('electrical_terminal', getattr(self.instance, 'electrical_terminal', None))
        rack = data.get('rack', getattr(self.instance, 'rack', None))
        device = data.get('device', getattr(self.instance, 'device', None))
        power_port = data.get('power_port', getattr(self.instance, 'power_port', None))
        expected_redundancy_group = data.get(
            'expected_redundancy_group', getattr(self.instance, 'expected_redundancy_group', None)
        )

        errors = {}
        target_fields = {'rack': rack, 'device': device, 'power_port': power_port}
        if sum(bool(target) for target in target_fields.values()) != 1:
            for field_name in target_fields:
                errors[field_name] = 'Select exactly one of rack, device, or power port.'

        if not electrical_node and not electrical_terminal:
            errors['electrical_node'] = 'Select an electrical node or an electrical terminal.'
            errors['electrical_terminal'] = 'Select an electrical node or an electrical terminal.'

        if power_system and electrical_node and electrical_node.power_system_id != power_system.pk:
            errors['electrical_node'] = 'The electrical node must belong to the selected power system.'

        if power_system and electrical_terminal:
            if electrical_terminal.node.power_system_id != power_system.pk:
                errors['electrical_terminal'] = 'The electrical terminal must belong to the selected power system.'
            if electrical_node and electrical_terminal.node_id != electrical_node.pk:
                errors['electrical_node'] = 'The electrical node must match the selected electrical terminal.'

        if power_system and expected_redundancy_group and expected_redundancy_group.power_system_id != power_system.pk:
            errors['expected_redundancy_group'] = 'The redundancy group must belong to the selected power system.'

        if power_system and rack:
            self._validate_boundary_scope(errors, power_system, rack, 'rack')

        if power_system and device:
            self._validate_boundary_scope(errors, power_system, device, 'device')

        if power_system and power_port:
            self._validate_boundary_scope(errors, power_system, power_port.device, 'power_port')

        if errors:
            raise ValidationError(errors)

        return data

    def _validate_boundary_scope(self, errors, power_system, boundary_object, field_name):
        if boundary_object.site_id != power_system.site_id:
            errors[field_name] = 'The selected object must belong to the same site as the power system.'
            return

        if not power_system.location_id:
            return

        boundary_location_id = getattr(boundary_object, 'location_id', None)
        if boundary_location_id is None and getattr(boundary_object, 'rack_id', None):
            boundary_location_id = boundary_object.rack.location_id

        if boundary_location_id != power_system.location_id:
            errors[field_name] = 'The selected object must match the power system location when one is set.'


class InternalPowerBusSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    rack = NestedRackSerializer(nested=True)
    bus_role = ChoiceField(choices=InternalPowerBusRoleChoices, required=False)
    supply_type = ChoiceField(choices=SupplyTypeChoices, required=False)
    design_state = ChoiceField(choices=DesignStateChoices, required=False)

    class Meta:
        model = InternalPowerBus
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'rack', 'bus_role',
            'supply_type', 'nominal_voltage', 'design_state', 'description', 'comments', 'tags',
            'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'bus_role', 'supply_type', 'design_state')

    def validate(self, data):
        data = super().validate(data)
        power_system = data.get('power_system', getattr(self.instance, 'power_system', None))
        rack = data.get('rack', getattr(self.instance, 'rack', None))

        errors = {}
        if power_system and rack:
            if rack.site_id != power_system.site_id:
                errors['rack'] = 'The selected rack must belong to the same site as the power system.'
            elif power_system.location_id and rack.location_id != power_system.location_id:
                errors['rack'] = 'The selected rack must belong to the same location as the power system.'

        if errors:
            raise ValidationError(errors)

        return data


class InternalPowerBusAttachmentSerializer(OrganizationalModelSerializer):
    internal_power_bus = NestedInternalPowerBusSerializer(nested=True)
    power_port = NestedPowerPortSerializer(nested=True)
    power_port_device = NestedDeviceSerializer(source='power_port.device', read_only=True)
    attachment_role = ChoiceField(choices=InternalPowerBusAttachmentRoleChoices, required=False)
    design_state = ChoiceField(choices=DesignStateChoices, required=False)

    class Meta:
        model = InternalPowerBusAttachment
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'internal_power_bus', 'power_port',
            'power_port_device', 'attachment_role', 'position_index', 'design_state', 'description', 'comments',
            'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'attachment_role', 'position_index', 'design_state')

    def validate(self, data):
        data = super().validate(data)
        internal_power_bus = data.get('internal_power_bus', getattr(self.instance, 'internal_power_bus', None))
        power_port = data.get('power_port', getattr(self.instance, 'power_port', None))

        errors = {}
        if internal_power_bus and power_port:
            device = power_port.device
            if device.site_id != internal_power_bus.power_system.site_id:
                errors['power_port'] = 'The attached power port device must belong to the same site as the power system.'
            elif device.rack_id != internal_power_bus.rack_id:
                errors['power_port'] = 'The attached power port device must belong to the bus rack.'

        if errors:
            raise ValidationError(errors)

        return data


class ElectricalNodePlacementSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    electrical_node = NestedElectricalNodeSerializer(nested=True)
    site = NestedSiteSerializer(nested=True)
    location = NestedLocationSerializer(nested=True, required=False, allow_null=True)
    placement_scope_type = ChoiceField(choices=PlacementScopeChoices, required=False)
    symbol_kind = ChoiceField(choices=PlacementSymbolKindChoices, required=False)
    label_mode = ChoiceField(choices=PlacementLabelModeChoices, required=False)

    class Meta:
        model = ElectricalNodePlacement
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'electrical_node', 'site',
            'location', 'placement_scope_type', 'x', 'y', 'width', 'height', 'rotation_degrees', 'symbol_kind',
            'label_mode', 'color', 'z_index', 'description', 'comments', 'tags', 'custom_fields', 'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'placement_scope_type', 'symbol_kind')

    def validate(self, data):
        data = super().validate(data)
        power_system = data.get('power_system', getattr(self.instance, 'power_system', None))
        electrical_node = data.get('electrical_node', getattr(self.instance, 'electrical_node', None))
        site = data.get('site', getattr(self.instance, 'site', None))
        location = data.get('location', getattr(self.instance, 'location', None))
        placement_scope_type = data.get(
            'placement_scope_type',
            getattr(self.instance, 'placement_scope_type', PlacementScopeChoices.SCOPE_LOCATION),
        )

        errors = {}
        if power_system and electrical_node and electrical_node.power_system_id != power_system.pk:
            errors['electrical_node'] = 'The electrical node must belong to the selected power system.'

        if power_system and site and site.pk != power_system.site_id:
            errors['site'] = 'The selected site must match the parent power system site.'

        if site and location and location.site_id != site.pk:
            errors['location'] = 'The selected location must belong to the selected site.'

        if power_system and power_system.location_id:
            if placement_scope_type != PlacementScopeChoices.SCOPE_LOCATION:
                errors['placement_scope_type'] = 'Location-scoped power systems require location placements.'
            if not location or location.pk != power_system.location_id:
                errors['location'] = 'The placement location must match the power system location.'
        elif power_system:
            if placement_scope_type != PlacementScopeChoices.SCOPE_SITE:
                errors['placement_scope_type'] = 'Site-scoped power systems require site placements.'
            if location:
                errors['location'] = 'Leave location blank when the power system does not resolve to a location floorplan.'

        if placement_scope_type == PlacementScopeChoices.SCOPE_SITE and location:
            errors['location'] = 'Site-scoped placements cannot set a location.'

        if placement_scope_type == PlacementScopeChoices.SCOPE_LOCATION and not location:
            errors['location'] = 'Select a location for location-scoped placements.'

        if not errors and power_system and electrical_node and site:
            queryset = ElectricalNodePlacement.objects.filter(
                power_system_id=power_system.pk,
                electrical_node_id=electrical_node.pk,
                site_id=site.pk,
                location_id=getattr(location, 'pk', None),
            )
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                errors['electrical_node'] = 'A placement already exists for this node in the resolved floorplan scope.'

        if errors:
            raise ValidationError(errors)

        return data
