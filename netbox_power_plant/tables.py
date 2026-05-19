import django_tables2 as tables
from django.utils.html import format_html, format_html_join
from netbox.tables import NetBoxTable, columns
from netbox.tables.columns import ActionsColumn

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
from .services.workflow_urls import build_delivery_add_url, build_delivery_edit_url


class OrganizationalModelTable(NetBoxTable):
    comments = tables.Column(empty_values=(), orderable=False)
    actions = ActionsColumn(actions=('edit', 'delete'))

    def render_comments(self, record):
        return getattr(record, 'comments', '')


class PowerSystemTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PowerSystem
        fields = (
            'pk', 'id', 'name', 'site', 'location', 'scope_type', 'upstream_supply_type', 'design_state',
            'is_template_derived', 'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'site', 'location', 'scope_type', 'upstream_supply_type', 'design_state', 'description',
        )


class PowerDomainTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    color = columns.ColorColumn()

    class Meta(OrganizationalModelTable.Meta):
        model = PowerDomain
        fields = (
            'pk', 'id', 'name', 'power_system', 'code', 'kind', 'color', 'priority', 'failure_isolation_depth',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'code', 'kind', 'color', 'priority', 'description',
        )


class RedundancyGroupTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    power_domains = columns.ManyToManyColumn(
        linkify_item=True,
        verbose_name='Power domains',
    )

    class Meta(OrganizationalModelTable.Meta):
        model = RedundancyGroup
        fields = (
            'pk', 'id', 'name', 'power_system', 'power_domains', 'topology_type', 'min_distinct_paths',
            'requires_domain_isolation', 'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'power_domains', 'topology_type', 'min_distinct_paths',
            'requires_domain_isolation', 'description',
        )


class PowerSystemSummaryTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    domain_count = tables.Column(empty_values=(), verbose_name='Domains')
    redundancy_group_count = tables.Column(empty_values=(), verbose_name='Redundancy groups')
    actions = ActionsColumn(actions=('edit', 'delete'))

    class Meta(OrganizationalModelTable.Meta):
        model = PowerSystem
        fields = ('name', 'site', 'scope_type', 'design_state', 'domain_count', 'redundancy_group_count', 'actions')
        default_columns = fields

    def render_domain_count(self, record):
        return record.power_domains.count()

    def render_redundancy_group_count(self, record):
        return record.redundancy_groups.count()


def render_domain_badges(power_domains):
    return format_html_join(', ', '{}', ((domain,) for domain in power_domains)) or '—'


class ElectricalNodeTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    parent_node = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = ElectricalNode
        fields = (
            'pk', 'id', 'name', 'power_system', 'site', 'location', 'parent_node', 'node_kind', 'install_state',
            'topology_state', 'phase_mode', 'installed_capacity_kw', 'usable_capacity_kw', 'description',
            'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'site', 'location', 'node_kind', 'topology_state', 'phase_mode',
            'installed_capacity_kw', 'usable_capacity_kw', 'description',
        )


class ElectricalTerminalTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    node = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = ElectricalTerminal
        fields = (
            'pk', 'id', 'name', 'node', 'terminal_role', 'direction', 'supply_type', 'voltage_nominal',
            'amperage_rating', 'position_index', 'is_protected', 'is_switchable', 'is_monitored', 'description',
            'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'node', 'terminal_role', 'direction', 'supply_type', 'voltage_nominal',
            'amperage_rating', 'position_index',
        )


class ElectricalSegmentTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    power_domain = tables.Column(linkify=True)
    from_terminal = tables.Column(linkify=True)
    to_terminal = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = ElectricalSegment
        fields = (
            'pk', 'id', 'name', 'power_system', 'power_domain', 'from_terminal', 'to_terminal', 'segment_kind',
            'path_state', 'length_m', 'voltage_nominal', 'ampacity_a', 'derated_ampacity_a', 'description',
            'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'power_domain', 'from_terminal', 'to_terminal', 'segment_kind',
            'path_state', 'voltage_nominal', 'ampacity_a',
        )


class RackDeliveryPointTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    electrical_node = tables.Column(linkify=True)
    electrical_terminal = tables.Column(linkify=True)
    rack = tables.Column(linkify=True)
    device = tables.Column(linkify=True)
    power_port = tables.Column(linkify=True)
    expected_redundancy_group = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = RackDeliveryPoint
        fields = (
            'pk', 'id', 'name', 'power_system', 'electrical_node', 'electrical_terminal', 'rack', 'device', 'power_port',
            'expected_redundancy_group', 'delivery_role', 'feed_label', 'design_state', 'description', 'comments',
            'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'electrical_node', 'electrical_terminal', 'rack', 'device', 'power_port',
            'expected_redundancy_group', 'feed_label', 'design_state',
        )


class ElectricalNodePlacementTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    electrical_node = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    color = columns.ColorColumn()

    class Meta(OrganizationalModelTable.Meta):
        model = ElectricalNodePlacement
        fields = (
            'pk', 'id', 'name', 'power_system', 'electrical_node', 'site', 'location', 'placement_scope_type', 'x',
            'y', 'width', 'height', 'rotation_degrees', 'symbol_kind', 'label_mode', 'color', 'z_index',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'electrical_node', 'placement_scope_type', 'x', 'y', 'symbol_kind',
            'label_mode', 'z_index',
        )


class RackDeliverySummaryTable(tables.Table):
    node = tables.Column(linkify=True)
    terminal = tables.Column(linkify=True)
    modeled_delivery = tables.Column(empty_values=(), verbose_name='Modeled Delivery')
    modeling_status = tables.Column(empty_values=(), verbose_name='Modeling')
    workflow = tables.Column(empty_values=(), verbose_name='Workflow')
    upstream_domains = tables.Column(empty_values=(), verbose_name='Upstream Domains')
    distinct_path_count = tables.Column(verbose_name='Distinct Paths')
    redundancy_status = tables.Column(empty_values=(), verbose_name='Redundancy')
    assessment_summary = tables.Column(verbose_name='Assessment')

    class Meta:
        fields = (
            'node', 'terminal', 'modeled_delivery', 'modeling_status', 'workflow', 'upstream_domains',
            'distinct_path_count', 'redundancy_status', 'assessment_summary',
        )

    def __init__(self, *args, power_system=None, return_url=None, can_add_delivery=False, can_edit_delivery=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.power_system = power_system
        self.return_url = return_url
        self.can_add_delivery = can_add_delivery
        self.can_edit_delivery = can_edit_delivery

    def render_modeled_delivery(self, record):
        if not record.delivery_points:
            return '—'
        return format_html_join(
            '<br>',
            '{}',
            ((self._describe_delivery_point(delivery_point),) for delivery_point in record.delivery_points),
        )

    def render_modeling_status(self, record):
        return 'Modeled' if record.delivery_points else 'Inferred only'

    def render_workflow(self, record):
        if record.delivery_points:
            if not self.can_edit_delivery:
                return '—'
            return format_html_join(
                '<br>',
                '<a href="{}">Edit {}</a>',
                (
                    (
                        build_delivery_edit_url(delivery_point, return_url=self.return_url or ''),
                        delivery_point.feed_label or delivery_point.name,
                    )
                    for delivery_point in record.delivery_points
                ),
            )

        if self.power_system is None or not self.can_add_delivery:
            return '—'

        return format_html(
            '<a href="{}">Model delivery point</a>',
            build_delivery_add_url(
                self.power_system,
                return_url=self.return_url or '',
                electrical_node_id=record.node.pk if record.node else None,
                electrical_terminal_id=record.terminal.pk if record.terminal else None,
            ),
        )

    def render_upstream_domains(self, record):
        return render_domain_badges(record.upstream_domains)

    def render_redundancy_status(self, record):
        return 'Compliant' if record.is_redundancy_compliant else 'Needs attention'

    def _describe_delivery_point(self, delivery_point):
        target = delivery_point.rack or delivery_point.device or delivery_point.power_port
        parts = [delivery_point.feed_label or delivery_point.name]
        if target is not None:
            parts.append(str(target))
        if delivery_point.expected_redundancy_group is not None:
            parts.append(f'expected {delivery_point.expected_redundancy_group.name}')
        return ' / '.join(parts)


class InternalPowerBusTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    rack = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = InternalPowerBus
        fields = (
            'pk', 'id', 'name', 'power_system', 'rack', 'bus_role', 'supply_type', 'nominal_voltage',
            'design_state', 'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'rack', 'bus_role', 'supply_type', 'nominal_voltage', 'design_state',
        )


class InternalPowerBusAttachmentTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    internal_power_bus = tables.Column(linkify=True)
    power_port = tables.Column(linkify=True)
    power_port_device = tables.Column(empty_values=(), verbose_name='Device', linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = InternalPowerBusAttachment
        fields = (
            'pk', 'id', 'name', 'internal_power_bus', 'power_port', 'power_port_device', 'attachment_role',
            'position_index', 'design_state', 'description', 'comments', 'tags', 'created', 'last_updated',
            'actions',
        )
        default_columns = (
            'pk', 'name', 'internal_power_bus', 'power_port', 'power_port_device', 'attachment_role',
            'position_index', 'design_state',
        )

    def render_power_port_device(self, record):
        return record.power_port.device
