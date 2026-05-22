import django_tables2 as tables
from django.utils.html import format_html, format_html_join
from netbox.tables import NetBoxTable, columns
from netbox.tables.columns import ActionsColumn

from .models import (
    BESSDetail,
    BuswaySectionDetail,
    CapacityReservation,
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    GeneratorDetail,
    InstantiationArtifact,
    InstantiationRun,
    InternalPowerBus,
    InternalPowerBusAttachment,
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    PowerArchitectureTemplate,
    PowerDomain,
    PowerFinding,
    PowerSystem,
    PowerHandoffPoint,
    PowerValidationRun,
    RedundancyGroup,
    SpatialFrame,
    SpatialPlacement,
    TransformerDetail,
    UPSDetail,
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


class PowerValidationRunTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PowerValidationRun
        fields = (
            'pk', 'id', 'name', 'power_system', 'run_kind', 'status', 'finding_count', 'started_at',
            'completed_at', 'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'run_kind', 'status', 'finding_count', 'started_at', 'completed_at',
        )


class PowerFindingTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    run = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    assigned_object = tables.Column(linkify=True, orderable=False)

    class Meta(OrganizationalModelTable.Meta):
        model = PowerFinding
        fields = (
            'pk', 'id', 'name', 'run', 'power_system', 'finding_type', 'severity', 'status', 'assigned_object',
            'assigned_to', 'suppressed_until', 'resolved_at', 'message', 'fingerprint', 'description', 'comments',
            'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'run', 'power_system', 'finding_type', 'severity', 'status', 'assigned_object', 'message',
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


class PowerArchitectureTemplateTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    actions = ActionsColumn(actions=())

    class Meta(OrganizationalModelTable.Meta):
        model = PowerArchitectureTemplate
        fields = (
            'pk', 'id', 'name', 'version', 'is_active', 'description', 'comments', 'tags',
            'created', 'last_updated', 'actions',
        )
        default_columns = ('pk', 'name', 'version', 'is_active', 'description')


class InstantiationRunTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    template = tables.Column(linkify=True)
    actions = ActionsColumn(actions=())

    class Meta(OrganizationalModelTable.Meta):
        model = InstantiationRun
        fields = (
            'pk', 'id', 'name', 'power_system', 'template', 'status', 'dry_run',
            'artifact_count', 'description', 'comments', 'tags', 'created',
            'last_updated', 'actions',
        )
        default_columns = ('pk', 'name', 'power_system', 'template', 'status', 'dry_run', 'artifact_count')


class InstantiationArtifactTable(OrganizationalModelTable):
    run = tables.Column(linkify=True)
    object = tables.Column(empty_values=(), orderable=False, verbose_name='Object')
    actions = ActionsColumn(actions=())

    class Meta(OrganizationalModelTable.Meta):
        model = InstantiationArtifact
        fields = (
            'pk', 'id', 'run', 'artifact_type', 'action', 'status', 'template_key',
            'stable_slug', 'object', 'description', 'comments', 'tags', 'created',
            'last_updated', 'actions',
        )
        default_columns = ('pk', 'run', 'artifact_type', 'action', 'status', 'template_key', 'stable_slug', 'object')

    def render_object(self, record):
        return record.object or ''


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


class PowerHandoffPointTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    power_system = tables.Column(linkify=True)
    electrical_node = tables.Column(linkify=True)
    electrical_terminal = tables.Column(linkify=True)
    power_port = tables.Column(linkify=True)
    expected_redundancy_group = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PowerHandoffPoint
        fields = (
            'pk', 'id', 'name', 'power_system', 'electrical_node', 'electrical_terminal', 'power_port',
            'expected_redundancy_group', 'delivery_role', 'feed_label', 'design_state', 'description', 'comments',
            'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'power_system', 'electrical_node', 'electrical_terminal', 'power_port',
            'expected_redundancy_group', 'feed_label', 'design_state',
        )


class CapacityReservationTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    node = tables.Column(linkify=True)
    tenant = tables.Column(linkify=True)
    rack = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = CapacityReservation
        fields = (
            'pk', 'id', 'name', 'node', 'tenant', 'rack', 'reserved_kw', 'status', 'valid_from',
            'valid_until', 'description', 'notes', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'node', 'tenant', 'rack', 'reserved_kw', 'status', 'valid_from', 'valid_until',
        )

    def render_status(self, value, record):
        colors = {
            'planned': 'secondary',
            'confirmed': 'primary',
            'active': 'success',
            'released': 'light',
        }
        return format_html(
            '<span class="badge text-bg-{}">{}</span>',
            colors.get(value, 'secondary'),
            record.get_status_display(),
        )


class ElectricalNodeDetailTable(NetBoxTable):
    node = tables.Column(linkify=True)
    power_system = tables.Column(accessor='node__power_system', verbose_name='Power system', linkify=True)
    actions = ActionsColumn(actions=('edit', 'delete'))

    class Meta(NetBoxTable.Meta):
        fields = ('pk', 'id', 'node', 'power_system', 'actions')
        default_columns = ('pk', 'node', 'power_system')


class UPSDetailTable(ElectricalNodeDetailTable):
    class Meta(ElectricalNodeDetailTable.Meta):
        model = UPSDetail
        fields = ElectricalNodeDetailTable.Meta.fields + (
            'ups_topology', 'battery_autonomy_minutes', 'module_count', 'module_rating_kw',
            'parallel_group_id', 'maintenance_bypass_present',
        )
        default_columns = (
            'pk', 'node', 'power_system', 'ups_topology', 'battery_autonomy_minutes',
            'module_count', 'module_rating_kw', 'maintenance_bypass_present',
        )


class GeneratorDetailTable(ElectricalNodeDetailTable):
    class Meta(ElectricalNodeDetailTable.Meta):
        model = GeneratorDetail
        fields = ElectricalNodeDetailTable.Meta.fields + (
            'fuel_type', 'runtime_at_full_load_hours', 'cooling_type', 'ats_group_id',
            'automatic_transfer_time_ms',
        )
        default_columns = (
            'pk', 'node', 'power_system', 'fuel_type', 'runtime_at_full_load_hours',
            'cooling_type', 'ats_group_id',
        )


class TransformerDetailTable(ElectricalNodeDetailTable):
    class Meta(ElectricalNodeDetailTable.Meta):
        model = TransformerDetail
        fields = ElectricalNodeDetailTable.Meta.fields + (
            'primary_kv', 'secondary_kv', 'kva_rating', 'vector_group', 'impedance_pct', 'cooling_type',
        )
        default_columns = (
            'pk', 'node', 'power_system', 'primary_kv', 'secondary_kv', 'kva_rating',
            'vector_group', 'impedance_pct',
        )


class BESSDetailTable(ElectricalNodeDetailTable):
    class Meta(ElectricalNodeDetailTable.Meta):
        model = BESSDetail
        fields = ElectricalNodeDetailTable.Meta.fields + (
            'technology', 'energy_capacity_kwh', 'peak_power_kw', 'charge_rate_kw',
            'usable_soc_min_pct', 'usable_soc_max_pct',
        )
        default_columns = (
            'pk', 'node', 'power_system', 'technology', 'energy_capacity_kwh',
            'peak_power_kw', 'usable_soc_min_pct', 'usable_soc_max_pct',
        )


class BuswaySectionDetailTable(ElectricalNodeDetailTable):
    busway_system = tables.Column(linkify=True)

    class Meta(ElectricalNodeDetailTable.Meta):
        model = BuswaySectionDetail
        fields = ElectricalNodeDetailTable.Meta.fields + (
            'busway_system', 'section_index', 'rated_ampacity_a', 'plug_count', 'plug_spacing_m',
        )
        default_columns = (
            'pk', 'node', 'power_system', 'busway_system', 'section_index',
            'rated_ampacity_a', 'plug_count', 'plug_spacing_m',
        )


class PlantSourceDocumentTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PlantSourceDocument
        fields = (
            'pk', 'id', 'name', 'site', 'location', 'source_type', 'discipline', 'document_id',
            'revision', 'issued_at', 'source_uri', 'checksum', 'description', 'comments', 'tags',
            'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'site', 'location', 'source_type', 'discipline', 'document_id', 'revision',
        )


class PlantSourceSheetTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    source_document = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PlantSourceSheet
        fields = (
            'pk', 'id', 'name', 'source_document', 'sheet_number', 'title', 'scale', 'page_index',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'source_document', 'sheet_number', 'title', 'scale', 'page_index',
        )


class PlantSourceLayerTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    source_sheet = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PlantSourceLayer
        fields = (
            'pk', 'id', 'name', 'source_sheet', 'layer_name', 'layer_kind', 'discipline', 'is_visible',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'source_sheet', 'layer_name', 'layer_kind', 'discipline', 'is_visible',
        )


class PlantProvenanceTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    assigned_object = tables.Column(linkify=True, orderable=False)
    source_document = tables.Column(linkify=True)
    source_sheet = tables.Column(linkify=True)
    source_layer = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PlantProvenance
        fields = (
            'pk', 'id', 'name', 'assigned_object', 'source_document', 'source_sheet', 'source_layer',
            'source_ref', 'extraction_method', 'confidence', 'is_authoritative', 'extracted_at',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'assigned_object', 'source_document', 'source_sheet', 'source_ref',
            'extraction_method', 'confidence', 'is_authoritative',
        )


class PhysicalSpaceTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    spatial_frame = tables.Column(linkify=True)
    parent_space = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PhysicalSpace
        fields = (
            'pk', 'id', 'name', 'site', 'location', 'spatial_frame', 'parent_space', 'space_kind',
            'floor_label', 'z_min', 'z_max', 'confidence', 'source_document', 'source_ref',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'site', 'location', 'space_kind', 'floor_label', 'spatial_frame',
            'confidence',
        )


class PhysicalElementTypeTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    default_color = columns.ColorColumn()

    class Meta(OrganizationalModelTable.Meta):
        model = PhysicalElementType
        fields = (
            'pk', 'id', 'name', 'discipline', 'element_kind', 'default_width', 'default_depth',
            'default_height', 'default_color', 'symbol_key', 'is_pathway', 'is_supporting_structure',
            'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'discipline', 'element_kind', 'default_color', 'symbol_key',
            'is_pathway', 'is_supporting_structure',
        )


class PhysicalElementTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    element_type = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    physical_space = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = PhysicalElement
        fields = (
            'pk', 'id', 'name', 'element_type', 'site', 'location', 'physical_space', 'label', 'role',
            'manufacturer', 'model_name', 'asset_tag', 'install_state', 'design_state', 'source_label',
            'confidence', 'description', 'comments', 'tags', 'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'element_type', 'site', 'location', 'physical_space', 'role',
            'install_state', 'design_state', 'confidence',
        )


class PhysicalObjectBindingTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    physical_element = tables.Column(linkify=True)
    spatial_placement = tables.Column(linkify=True)
    assigned_object = tables.Column(linkify=True, orderable=False)

    class Meta(OrganizationalModelTable.Meta):
        model = PhysicalObjectBinding
        fields = (
            'pk', 'id', 'name', 'physical_element', 'spatial_placement', 'assigned_object',
            'binding_role', 'confidence', 'is_primary', 'description', 'comments', 'tags',
            'created', 'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'physical_element', 'spatial_placement', 'assigned_object',
            'binding_role', 'confidence', 'is_primary',
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


class SpatialFrameTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    site = tables.Column(linkify=True)
    location = tables.Column(linkify=True)
    parent_frame = tables.Column(linkify=True)

    class Meta(OrganizationalModelTable.Meta):
        model = SpatialFrame
        fields = (
            'pk', 'id', 'name', 'site', 'location', 'parent_frame', 'origin_x_in_parent',
            'origin_y_in_parent', 'width', 'height', 'units', 'axis_orientation', 'source_document',
            'source_ref', 'confidence', 'metadata', 'description', 'comments', 'tags', 'created',
            'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'site', 'location', 'parent_frame', 'width', 'height',
            'units', 'axis_orientation', 'confidence',
        )


class SpatialPlacementTable(OrganizationalModelTable):
    name = tables.Column(linkify=True)
    spatial_frame = tables.Column(linkify=True)
    assigned_object = tables.Column(linkify=True, orderable=False)

    class Meta(OrganizationalModelTable.Meta):
        model = SpatialPlacement
        fields = (
            'pk', 'id', 'name', 'spatial_frame', 'assigned_object', 'x', 'y', 'z', 'width',
            'depth', 'height', 'rotation_degrees', 'anchor', 'placement_kind', 'confidence',
            'source_document', 'source_ref', 'description', 'comments', 'tags', 'created',
            'last_updated', 'actions',
        )
        default_columns = (
            'pk', 'name', 'spatial_frame', 'assigned_object', 'x', 'y', 'z',
            'placement_kind', 'confidence',
        )


class PowerHandoffSummaryTable(tables.Table):
    node = tables.Column(linkify=True)
    terminal = tables.Column(linkify=True)
    modeled_delivery = tables.Column(empty_values=(), verbose_name='Modeled Power Handoff')
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
            '<a href="{}">Model power handoff point</a>',
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
        target = delivery_point.power_port
        parts = [delivery_point.feed_label or delivery_point.name]
        if target is not None:
            parts.append(str(target))
        if delivery_point.expected_redundancy_group is not None:
            parts.append(f'expected {delivery_point.expected_redundancy_group.name}')
        return ' / '.join(parts)


RackDeliverySummaryTable = PowerHandoffSummaryTable


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
