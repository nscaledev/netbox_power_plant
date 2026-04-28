import django_filters

from dcim.models import Device, Location, Rack, Site
from netbox.filtersets import OrganizationalModelFilterSet

from .models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    PowerDomain,
    PowerSystem,
    RackDeliveryPoint,
    RedundancyGroup,
)


class PowerSystemFilterSet(OrganizationalModelFilterSet):
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='site',
        queryset=Site.objects.all(),
        label='Site',
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name='location',
        queryset=Location.objects.all(),
        label='Location',
    )

    class Meta:
        model = PowerSystem
        fields = ('id', 'name', 'slug', 'site_id', 'location_id', 'scope_type', 'upstream_supply_type', 'design_state', 'is_template_derived')


class PowerDomainFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )

    class Meta:
        model = PowerDomain
        fields = ('id', 'name', 'slug', 'power_system_id', 'code', 'kind', 'color', 'priority')


class RedundancyGroupFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    power_domain_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_domains',
        queryset=PowerDomain.objects.all(),
        label='Power domain',
    )

    class Meta:
        model = RedundancyGroup
        fields = ('id', 'name', 'slug', 'power_system_id', 'power_domain_id', 'topology_type', 'requires_domain_isolation')


class ElectricalNodeFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='site',
        queryset=Site.objects.all(),
        label='Site',
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name='location',
        queryset=Location.objects.all(),
        label='Location',
    )
    parent_node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='parent_node',
        queryset=ElectricalNode.objects.all(),
        label='Parent node',
    )

    class Meta:
        model = ElectricalNode
        fields = (
            'id', 'name', 'slug', 'power_system_id', 'site_id', 'location_id', 'parent_node_id',
            'node_kind', 'install_state', 'topology_state', 'phase_mode',
        )


class ElectricalTerminalFilterSet(OrganizationalModelFilterSet):
    node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node',
        queryset=ElectricalNode.objects.all(),
        label='Node',
    )

    class Meta:
        model = ElectricalTerminal
        fields = ('id', 'name', 'slug', 'node_id', 'terminal_role', 'direction', 'supply_type', 'is_protected', 'is_switchable', 'is_monitored')


class ElectricalSegmentFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    power_domain_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_domain',
        queryset=PowerDomain.objects.all(),
        label='Power domain',
    )
    from_node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='from_terminal__node',
        queryset=ElectricalNode.objects.all(),
        label='From node',
    )
    to_node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='to_terminal__node',
        queryset=ElectricalNode.objects.all(),
        label='To node',
    )

    class Meta:
        model = ElectricalSegment
        fields = ('id', 'name', 'slug', 'power_system_id', 'power_domain_id', 'from_node_id', 'to_node_id', 'segment_kind', 'path_state')


class RackDeliveryPointFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    expected_redundancy_group_id = django_filters.ModelMultipleChoiceFilter(
        field_name='expected_redundancy_group',
        queryset=RedundancyGroup.objects.all(),
        label='Redundancy group',
    )
    electrical_node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='electrical_node',
        queryset=ElectricalNode.objects.all(),
        label='Electrical node',
    )
    electrical_terminal_id = django_filters.ModelMultipleChoiceFilter(
        field_name='electrical_terminal',
        queryset=ElectricalTerminal.objects.all(),
        label='Electrical terminal',
    )
    rack_id = django_filters.ModelMultipleChoiceFilter(
        field_name='rack',
        queryset=Rack.objects.all(),
        label='Rack',
    )
    device_id = django_filters.ModelMultipleChoiceFilter(
        field_name='device',
        queryset=Device.objects.all(),
        label='Device',
    )

    class Meta:
        model = RackDeliveryPoint
        fields = (
            'id', 'name', 'slug', 'power_system_id', 'expected_redundancy_group_id', 'electrical_node_id',
            'electrical_terminal_id', 'rack_id', 'device_id', 'delivery_role', 'feed_label', 'design_state',
        )


class ElectricalNodePlacementFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    electrical_node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='electrical_node',
        queryset=ElectricalNode.objects.all(),
        label='Electrical node',
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='site',
        queryset=Site.objects.all(),
        label='Site',
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name='location',
        queryset=Location.objects.all(),
        label='Location',
    )

    class Meta:
        model = ElectricalNodePlacement
        fields = (
            'id', 'name', 'slug', 'power_system_id', 'electrical_node_id', 'site_id', 'location_id',
            'placement_scope_type', 'symbol_kind', 'label_mode', 'z_index',
        )