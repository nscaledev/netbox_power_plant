from django import forms

from dcim.models import Device, Location, PowerPort, Rack, Site
try:
    from netbox.forms import OrganizationalModelFilterSetForm, OrganizationalModelForm
except ImportError:
    from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm

    class OrganizationalModelForm(NetBoxModelForm):
        comments = forms.CharField(
            required=False,
            widget=forms.Textarea,
            help_text='Compatibility-only field for NetBox releases before OrganizationalModel comments.',
        )

    OrganizationalModelFilterSetForm = NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelChoiceField, DynamicModelMultipleChoiceField
from utilities.forms.rendering import FieldSet

from .choices import (
    DesignStateChoices,
    NodeKindChoices,
    PhaseModeChoices,
    InternalPowerBusAttachmentRoleChoices,
    InternalPowerBusRoleChoices,
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
from .models import (
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


class PowerSystemForm(OrganizationalModelForm):
    site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=True,
        selector=True,
    )
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'site', 'location', name='Scope'),
        FieldSet(
            'scope_type',
            'upstream_supply_type',
            'nominal_distribution_voltage',
            'frequency_hz',
            'design_state',
            'is_template_derived',
            name='Design',
        ),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PowerSystem
        fields = (
            'name',
            'slug',
            'site',
            'location',
            'scope_type',
            'upstream_supply_type',
            'nominal_distribution_voltage',
            'frequency_hz',
            'design_state',
            'is_template_derived',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'scope_type': forms.Select(choices=PowerSystemScopeChoices),
            'upstream_supply_type': forms.Select(choices=SupplyTypeChoices),
            'design_state': forms.Select(choices=DesignStateChoices),
        }


class PowerDomainForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'code', name='Domain'),
        FieldSet('kind', 'color', 'priority', 'failure_isolation_depth', name='Behavior'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PowerDomain
        fields = (
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
        )
        widgets = {
            'kind': forms.Select(choices=PowerDomainKindChoices),
        }


class RedundancyGroupForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    power_domains = DynamicModelMultipleChoiceField(
        queryset=PowerDomain.objects.all(),
        required=False,
        query_params={'power_system_id': '$power_system'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'power_domains', name='Group'),
        FieldSet(
            'topology_type',
            'min_distinct_paths',
            'requires_domain_isolation',
            name='Redundancy Contract',
        ),
        FieldSet('description', 'notes_on_failover', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = RedundancyGroup
        fields = (
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
        )
        widgets = {
            'topology_type': forms.Select(choices=RedundancyTopologyChoices),
        }

    def clean(self):
        cleaned_data = super().clean()
        power_system = cleaned_data.get('power_system')
        power_domains = cleaned_data.get('power_domains')

        if power_system and power_domains:
            mismatched_domains = [domain for domain in power_domains if domain.power_system_id != power_system.pk]
            if mismatched_domains:
                self.add_error('power_domains', 'Selected domains must belong to the selected power system.')

        return cleaned_data


class ElectricalNodeForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=True,
        selector=True,
    )
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )
    parent_node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        query_params={'power_system_id': '$power_system'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'site', 'location', 'parent_node', name='Placement'),
        FieldSet('node_kind', 'equipment_role', 'manufacturer', 'model', 'serial', 'asset_tag', name='Identity'),
        FieldSet('install_state', 'topology_state', 'phase_mode', 'pole_count', 'frequency_hz', name='State'),
        FieldSet(
            'rated_input_voltage_min',
            'rated_input_voltage_max',
            'rated_output_voltage_min',
            'rated_output_voltage_max',
            'installed_capacity_kw',
            'usable_capacity_kw',
            'derating_factor',
            'reserve_margin_pct',
            'telemetry_source_ref',
            name='Electrical Characteristics',
        ),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = ElectricalNode
        fields = (
            'name',
            'slug',
            'power_system',
            'site',
            'location',
            'parent_node',
            'node_kind',
            'equipment_role',
            'manufacturer',
            'model',
            'serial',
            'asset_tag',
            'install_state',
            'topology_state',
            'phase_mode',
            'pole_count',
            'frequency_hz',
            'rated_input_voltage_min',
            'rated_input_voltage_max',
            'rated_output_voltage_min',
            'rated_output_voltage_max',
            'installed_capacity_kw',
            'usable_capacity_kw',
            'derating_factor',
            'reserve_margin_pct',
            'telemetry_source_ref',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'node_kind': forms.Select(choices=NodeKindChoices),
            'install_state': forms.Select(choices=TopologyStateChoices),
            'topology_state': forms.Select(choices=TopologyStateChoices),
            'phase_mode': forms.Select(choices=PhaseModeChoices),
        }


class ElectricalTerminalForm(OrganizationalModelForm):
    node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'node', 'position_index', name='Attachment'),
        FieldSet(
            'terminal_role',
            'direction',
            'supply_type',
            'voltage_nominal',
            'amperage_rating',
            'phase_designation',
            'pole_designation',
            'connector_type',
            name='Electrical Characteristics',
        ),
        FieldSet('is_protected', 'is_switchable', 'is_monitored', name='Behavior'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = ElectricalTerminal
        fields = (
            'name',
            'slug',
            'node',
            'position_index',
            'terminal_role',
            'direction',
            'supply_type',
            'voltage_nominal',
            'amperage_rating',
            'phase_designation',
            'pole_designation',
            'connector_type',
            'is_protected',
            'is_switchable',
            'is_monitored',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'terminal_role': forms.Select(choices=TerminalRoleChoices),
            'direction': forms.Select(choices=TerminalDirectionChoices),
            'supply_type': forms.Select(choices=SupplyTypeChoices),
        }


class ElectricalSegmentForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    from_terminal = DynamicModelChoiceField(
        queryset=ElectricalTerminal.objects.all(),
        required=True,
        selector=True,
    )
    to_terminal = DynamicModelChoiceField(
        queryset=ElectricalTerminal.objects.all(),
        required=True,
        selector=True,
    )
    power_domain = DynamicModelChoiceField(
        queryset=PowerDomain.objects.all(),
        required=False,
        query_params={'power_system_id': '$power_system'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'power_domain', name='Scope'),
        FieldSet('from_terminal', 'to_terminal', 'segment_kind', 'path_state', name='Topology'),
        FieldSet(
            'length_m',
            'conductor_material',
            'conductor_count',
            'awg_or_mm2',
            'insulation_type',
            'breaker_size_a',
            'voltage_nominal',
            'ampacity_a',
            'derated_ampacity_a',
            name='Electrical Characteristics',
        ),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = ElectricalSegment
        fields = (
            'name',
            'slug',
            'power_system',
            'power_domain',
            'from_terminal',
            'to_terminal',
            'segment_kind',
            'path_state',
            'length_m',
            'conductor_material',
            'conductor_count',
            'awg_or_mm2',
            'insulation_type',
            'breaker_size_a',
            'voltage_nominal',
            'ampacity_a',
            'derated_ampacity_a',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'segment_kind': forms.Select(choices=SegmentKindChoices),
            'path_state': forms.Select(choices=TopologyStateChoices),
        }


class InternalPowerBusForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    rack = DynamicModelChoiceField(
        queryset=Rack.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'design_state', name='Scope'),
        FieldSet('rack', 'bus_role', 'supply_type', 'nominal_voltage', name='Bus'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = InternalPowerBus
        fields = (
            'name',
            'slug',
            'power_system',
            'rack',
            'bus_role',
            'supply_type',
            'nominal_voltage',
            'design_state',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'bus_role': forms.Select(choices=InternalPowerBusRoleChoices),
            'supply_type': forms.Select(choices=SupplyTypeChoices),
            'design_state': forms.Select(choices=DesignStateChoices),
        }


class InternalPowerBusAttachmentForm(OrganizationalModelForm):
    internal_power_bus = DynamicModelChoiceField(
        queryset=InternalPowerBus.objects.all(),
        required=True,
        selector=True,
    )
    power_port = DynamicModelChoiceField(
        queryset=PowerPort.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'internal_power_bus', 'design_state', name='Scope'),
        FieldSet('power_port', 'attachment_role', 'position_index', name='Power Port Attachment'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = InternalPowerBusAttachment
        fields = (
            'name',
            'slug',
            'internal_power_bus',
            'power_port',
            'attachment_role',
            'position_index',
            'design_state',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'attachment_role': forms.Select(choices=InternalPowerBusAttachmentRoleChoices),
            'design_state': forms.Select(choices=DesignStateChoices),
        }


class RackDeliveryPointForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    electrical_node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        query_params={'power_system_id': '$power_system'},
    )
    electrical_terminal = DynamicModelChoiceField(
        queryset=ElectricalTerminal.objects.all(),
        required=False,
        query_params={'node_id': '$electrical_node'},
    )
    rack = DynamicModelChoiceField(
        queryset=Rack.objects.all(),
        required=False,
        selector=True,
    )
    device = DynamicModelChoiceField(
        queryset=Device.objects.all(),
        required=False,
        selector=True,
    )
    power_port = DynamicModelChoiceField(
        queryset=PowerPort.objects.all(),
        required=False,
        selector=True,
    )
    expected_redundancy_group = DynamicModelChoiceField(
        queryset=RedundancyGroup.objects.all(),
        required=False,
        query_params={'power_system_id': '$power_system'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'design_state', name='Scope'),
        FieldSet('electrical_node', 'electrical_terminal', 'expected_redundancy_group', name='Electrical Boundary'),
        FieldSet('rack', 'device', 'power_port', 'delivery_role', 'feed_label', name='Target'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = RackDeliveryPoint
        fields = (
            'name',
            'slug',
            'power_system',
            'electrical_node',
            'electrical_terminal',
            'rack',
            'device',
            'power_port',
            'expected_redundancy_group',
            'delivery_role',
            'feed_label',
            'design_state',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'design_state': forms.Select(choices=DesignStateChoices),
        }


class ElectricalNodePlacementForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    electrical_node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=True,
        query_params={'power_system_id': '$power_system'},
    )
    site = DynamicModelChoiceField(
        queryset=Site.objects.all(),
        required=True,
        selector=True,
    )
    location = DynamicModelChoiceField(
        queryset=Location.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', 'electrical_node', name='Placement'),
        FieldSet('site', 'location', 'placement_scope_type', name='Floorplan Context'),
        FieldSet('x', 'y', 'width', 'height', 'rotation_degrees', name='Coordinates'),
        FieldSet('symbol_kind', 'label_mode', 'color', 'z_index', name='Rendering'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = ElectricalNodePlacement
        fields = (
            'name',
            'slug',
            'power_system',
            'electrical_node',
            'site',
            'location',
            'placement_scope_type',
            'x',
            'y',
            'width',
            'height',
            'rotation_degrees',
            'symbol_kind',
            'label_mode',
            'color',
            'z_index',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'placement_scope_type': forms.Select(choices=PlacementScopeChoices),
            'symbol_kind': forms.Select(choices=PlacementSymbolKindChoices),
            'label_mode': forms.Select(choices=PlacementLabelModeChoices),
        }


class PowerSystemFilterForm(OrganizationalModelFilterSetForm):
    model = PowerSystem
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('site_id', 'location_id', name='Scope'),
        FieldSet('scope_type', 'upstream_supply_type', 'design_state', 'is_template_derived', name='Design'),
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label='Site',
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label='Location',
        query_params={'site_id': '$site_id'},
    )


class PowerDomainFilterForm(OrganizationalModelFilterSetForm):
    model = PowerDomain
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'kind', 'color', name='Attributes'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )


class RedundancyGroupFilterForm(OrganizationalModelFilterSetForm):
    model = RedundancyGroup
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'power_domain_id', name='Scope'),
        FieldSet('topology_type', 'requires_domain_isolation', name='Behavior'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    power_domain_id = DynamicModelMultipleChoiceField(
        queryset=PowerDomain.objects.all(),
        required=False,
        label='Power domain',
        query_params={'power_system_id': '$power_system_id'},
    )


class ElectricalNodeFilterForm(OrganizationalModelFilterSetForm):
    model = ElectricalNode
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'site_id', 'location_id', 'parent_node_id', name='Scope'),
        FieldSet('node_kind', 'install_state', 'topology_state', 'phase_mode', name='Attributes'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label='Site',
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label='Location',
        query_params={'site_id': '$site_id'},
    )
    parent_node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='Parent node',
        query_params={'power_system_id': '$power_system_id'},
    )


class ElectricalTerminalFilterForm(OrganizationalModelFilterSetForm):
    model = ElectricalTerminal
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('node_id', name='Attachment'),
        FieldSet('terminal_role', 'direction', 'supply_type', name='Attributes'),
    )
    node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='Node',
    )


class ElectricalSegmentFilterForm(OrganizationalModelFilterSetForm):
    model = ElectricalSegment
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'power_domain_id', name='Scope'),
        FieldSet('from_node_id', 'to_node_id', name='Endpoints'),
        FieldSet('segment_kind', 'path_state', name='Attributes'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    power_domain_id = DynamicModelMultipleChoiceField(
        queryset=PowerDomain.objects.all(),
        required=False,
        label='Power domain',
        query_params={'power_system_id': '$power_system_id'},
    )
    from_node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='From node',
        query_params={'power_system_id': '$power_system_id'},
    )
    to_node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='To node',
        query_params={'power_system_id': '$power_system_id'},
    )


class RackDeliveryPointFilterForm(OrganizationalModelFilterSetForm):
    model = RackDeliveryPoint
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'expected_redundancy_group_id', name='Scope'),
        FieldSet('electrical_node_id', 'electrical_terminal_id', name='Electrical Boundary'),
        FieldSet('rack_id', 'device_id', 'power_port_id', 'design_state', name='Target'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    expected_redundancy_group_id = DynamicModelMultipleChoiceField(
        queryset=RedundancyGroup.objects.all(),
        required=False,
        label='Redundancy group',
        query_params={'power_system_id': '$power_system_id'},
    )
    electrical_node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='Electrical node',
        query_params={'power_system_id': '$power_system_id'},
    )
    electrical_terminal_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalTerminal.objects.all(),
        required=False,
        label='Electrical terminal',
    )
    rack_id = DynamicModelMultipleChoiceField(
        queryset=Rack.objects.all(),
        required=False,
        label='Rack',
    )
    device_id = DynamicModelMultipleChoiceField(
        queryset=Device.objects.all(),
        required=False,
        label='Device',
    )
    power_port_id = DynamicModelMultipleChoiceField(
        queryset=PowerPort.objects.all(),
        required=False,
        label='Power port',
    )


class InternalPowerBusFilterForm(OrganizationalModelFilterSetForm):
    model = InternalPowerBus
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'rack_id', name='Scope'),
        FieldSet('bus_role', 'supply_type', 'design_state', name='Bus'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    rack_id = DynamicModelMultipleChoiceField(
        queryset=Rack.objects.all(),
        required=False,
        label='Rack',
    )


class InternalPowerBusAttachmentFilterForm(OrganizationalModelFilterSetForm):
    model = InternalPowerBusAttachment
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('internal_power_bus_id', 'power_port_id', name='Attachment'),
        FieldSet('attachment_role', 'design_state', name='Attributes'),
    )
    internal_power_bus_id = DynamicModelMultipleChoiceField(
        queryset=InternalPowerBus.objects.all(),
        required=False,
        label='Internal power bus',
    )
    power_port_id = DynamicModelMultipleChoiceField(
        queryset=PowerPort.objects.all(),
        required=False,
        label='Power port',
    )


class ElectricalNodePlacementFilterForm(OrganizationalModelFilterSetForm):
    model = ElectricalNodePlacement
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'electrical_node_id', name='Scope'),
        FieldSet('site_id', 'location_id', 'placement_scope_type', name='Floorplan Context'),
        FieldSet('symbol_kind', 'label_mode', name='Rendering'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    electrical_node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='Electrical node',
        query_params={'power_system_id': '$power_system_id'},
    )
    site_id = DynamicModelMultipleChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label='Site',
    )
    location_id = DynamicModelMultipleChoiceField(
        queryset=Location.objects.all(),
        required=False,
        label='Location',
        query_params={'site_id': '$site_id'},
    )
