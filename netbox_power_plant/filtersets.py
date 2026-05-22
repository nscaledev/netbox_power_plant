import django_filters

from django.contrib.contenttypes.models import ContentType
from dcim.models import Device, Location, PowerPort, Rack, Site
from tenancy.models import Tenant
from netbox.filtersets import OrganizationalModelFilterSet

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


class PowerValidationRunFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )

    class Meta:
        model = PowerValidationRun
        fields = ('id', 'name', 'slug', 'power_system_id', 'run_kind', 'status')


class PowerFindingFilterSet(OrganizationalModelFilterSet):
    run_id = django_filters.ModelMultipleChoiceFilter(
        field_name='run',
        queryset=PowerValidationRun.objects.all(),
        label='Validation run',
    )
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    assigned_object_type_id = django_filters.ModelMultipleChoiceFilter(
        field_name='assigned_object_type',
        queryset=ContentType.objects.all(),
        label='Assigned object type',
    )

    class Meta:
        model = PowerFinding
        fields = (
            'id', 'name', 'slug', 'run_id', 'power_system_id', 'finding_type', 'severity', 'status',
            'assigned_object_type_id', 'assigned_object_id', 'assigned_to',
        )


class PowerArchitectureTemplateFilterSet(OrganizationalModelFilterSet):
    class Meta:
        model = PowerArchitectureTemplate
        fields = ('id', 'name', 'slug', 'version', 'is_active')


class InstantiationRunFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    template_id = django_filters.ModelMultipleChoiceFilter(
        field_name='template',
        queryset=PowerArchitectureTemplate.objects.all(),
        label='Template',
    )

    class Meta:
        model = InstantiationRun
        fields = ('id', 'name', 'slug', 'power_system_id', 'template_id', 'status', 'dry_run')


class InstantiationArtifactFilterSet(OrganizationalModelFilterSet):
    run_id = django_filters.ModelMultipleChoiceFilter(
        field_name='run',
        queryset=InstantiationRun.objects.all(),
        label='Instantiation run',
    )

    class Meta:
        model = InstantiationArtifact
        fields = ('id', 'name', 'slug', 'run_id', 'artifact_type', 'action', 'status', 'template_key')


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


class PowerHandoffPointFilterSet(OrganizationalModelFilterSet):
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
    power_port_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_port',
        queryset=PowerPort.objects.all(),
        label='Power port',
    )

    class Meta:
        model = PowerHandoffPoint
        fields = (
            'id', 'name', 'slug', 'power_system_id', 'expected_redundancy_group_id', 'electrical_node_id',
            'electrical_terminal_id', 'power_port_id', 'delivery_role', 'feed_label', 'design_state',
        )


class CapacityReservationFilterSet(OrganizationalModelFilterSet):
    node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node',
        queryset=ElectricalNode.objects.all(),
        label='Electrical node',
    )
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node__power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node__site',
        queryset=Site.objects.all(),
        label='Site',
    )
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        field_name='tenant',
        queryset=Tenant.objects.all(),
        label='Tenant',
    )
    rack_id = django_filters.ModelMultipleChoiceFilter(
        field_name='rack',
        queryset=Rack.objects.all(),
        label='Rack',
    )

    class Meta:
        model = CapacityReservation
        fields = (
            'id', 'name', 'slug', 'node_id', 'power_system_id', 'site_id', 'tenant_id', 'rack_id',
            'reserved_kw', 'status', 'valid_from', 'valid_until',
        )


class ElectricalNodeDetailFilterSet(django_filters.FilterSet):
    node_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node',
        queryset=ElectricalNode.objects.all(),
        label='Electrical node',
    )
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node__power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='node__site',
        queryset=Site.objects.all(),
        label='Site',
    )

    class Meta:
        fields = ('id', 'node_id', 'power_system_id', 'site_id')


class UPSDetailFilterSet(ElectricalNodeDetailFilterSet):
    class Meta(ElectricalNodeDetailFilterSet.Meta):
        model = UPSDetail
        fields = ElectricalNodeDetailFilterSet.Meta.fields + (
            'ups_topology', 'parallel_group_id', 'maintenance_bypass_present',
        )


class GeneratorDetailFilterSet(ElectricalNodeDetailFilterSet):
    class Meta(ElectricalNodeDetailFilterSet.Meta):
        model = GeneratorDetail
        fields = ElectricalNodeDetailFilterSet.Meta.fields + (
            'fuel_type', 'cooling_type', 'ats_group_id',
        )


class TransformerDetailFilterSet(ElectricalNodeDetailFilterSet):
    class Meta(ElectricalNodeDetailFilterSet.Meta):
        model = TransformerDetail
        fields = ElectricalNodeDetailFilterSet.Meta.fields + (
            'vector_group', 'cooling_type',
        )


class BESSDetailFilterSet(ElectricalNodeDetailFilterSet):
    class Meta(ElectricalNodeDetailFilterSet.Meta):
        model = BESSDetail
        fields = ElectricalNodeDetailFilterSet.Meta.fields + (
            'technology',
        )


class BuswaySectionDetailFilterSet(ElectricalNodeDetailFilterSet):
    busway_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='busway_system',
        queryset=ElectricalNode.objects.filter(node_kind='busway_run'),
        label='Busway system',
    )

    class Meta(ElectricalNodeDetailFilterSet.Meta):
        model = BuswaySectionDetail
        fields = ElectricalNodeDetailFilterSet.Meta.fields + (
            'busway_system_id', 'section_index',
        )


class InternalPowerBusFilterSet(OrganizationalModelFilterSet):
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )
    rack_id = django_filters.ModelMultipleChoiceFilter(
        field_name='rack',
        queryset=Rack.objects.all(),
        label='Rack',
    )

    class Meta:
        model = InternalPowerBus
        fields = ('id', 'name', 'slug', 'power_system_id', 'rack_id', 'bus_role', 'supply_type', 'design_state')


class InternalPowerBusAttachmentFilterSet(OrganizationalModelFilterSet):
    internal_power_bus_id = django_filters.ModelMultipleChoiceFilter(
        field_name='internal_power_bus',
        queryset=InternalPowerBus.objects.all(),
        label='Internal power bus',
    )
    power_port_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_port',
        queryset=PowerPort.objects.all(),
        label='Power port',
    )
    power_port_device_id = django_filters.ModelMultipleChoiceFilter(
        field_name='power_port__device',
        queryset=Device.objects.all(),
        label='Power port device',
    )
    rack_id = django_filters.ModelMultipleChoiceFilter(
        field_name='internal_power_bus__rack',
        queryset=Rack.objects.all(),
        label='Rack',
    )
    power_system_id = django_filters.ModelMultipleChoiceFilter(
        field_name='internal_power_bus__power_system',
        queryset=PowerSystem.objects.all(),
        label='Power system',
    )

    class Meta:
        model = InternalPowerBusAttachment
        fields = (
            'id', 'name', 'slug', 'internal_power_bus_id', 'power_system_id', 'rack_id', 'power_port_id',
            'power_port_device_id', 'attachment_role', 'design_state',
        )


class PlantSourceDocumentFilterSet(OrganizationalModelFilterSet):
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
        model = PlantSourceDocument
        fields = (
            'id', 'name', 'slug', 'site_id', 'location_id', 'source_type', 'discipline',
            'document_id', 'revision', 'source_uri', 'checksum',
        )


class PlantSourceSheetFilterSet(OrganizationalModelFilterSet):
    source_document_id = django_filters.ModelMultipleChoiceFilter(
        field_name='source_document',
        queryset=PlantSourceDocument.objects.all(),
        label='Source document',
    )

    class Meta:
        model = PlantSourceSheet
        fields = ('id', 'name', 'slug', 'source_document_id', 'sheet_number', 'title', 'scale', 'page_index')


class PlantSourceLayerFilterSet(OrganizationalModelFilterSet):
    source_document_id = django_filters.ModelMultipleChoiceFilter(
        field_name='source_sheet__source_document',
        queryset=PlantSourceDocument.objects.all(),
        label='Source document',
    )
    source_sheet_id = django_filters.ModelMultipleChoiceFilter(
        field_name='source_sheet',
        queryset=PlantSourceSheet.objects.all(),
        label='Source sheet',
    )

    class Meta:
        model = PlantSourceLayer
        fields = (
            'id', 'name', 'slug', 'source_document_id', 'source_sheet_id', 'layer_name',
            'layer_kind', 'discipline', 'is_visible',
        )


class PlantProvenanceFilterSet(OrganizationalModelFilterSet):
    assigned_object_type_id = django_filters.ModelMultipleChoiceFilter(
        field_name='assigned_object_type',
        queryset=ContentType.objects.all(),
        label='Assigned object type',
    )
    source_document_id = django_filters.ModelMultipleChoiceFilter(
        field_name='source_document',
        queryset=PlantSourceDocument.objects.all(),
        label='Source document',
    )
    source_sheet_id = django_filters.ModelMultipleChoiceFilter(
        field_name='source_sheet',
        queryset=PlantSourceSheet.objects.all(),
        label='Source sheet',
    )
    source_layer_id = django_filters.ModelMultipleChoiceFilter(
        field_name='source_layer',
        queryset=PlantSourceLayer.objects.all(),
        label='Source layer',
    )

    class Meta:
        model = PlantProvenance
        fields = (
            'id', 'name', 'slug', 'assigned_object_type_id', 'assigned_object_id',
            'source_document_id', 'source_sheet_id', 'source_layer_id', 'extraction_method',
            'source_ref', 'confidence', 'is_authoritative',
        )


class PhysicalSpaceFilterSet(OrganizationalModelFilterSet):
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
    spatial_frame_id = django_filters.ModelMultipleChoiceFilter(
        field_name='spatial_frame',
        queryset=SpatialFrame.objects.all(),
        label='Spatial frame',
    )
    parent_space_id = django_filters.ModelMultipleChoiceFilter(
        field_name='parent_space',
        queryset=PhysicalSpace.objects.all(),
        label='Parent space',
    )

    class Meta:
        model = PhysicalSpace
        fields = (
            'id', 'name', 'slug', 'site_id', 'location_id', 'spatial_frame_id', 'parent_space_id',
            'space_kind', 'floor_label', 'confidence', 'source_document', 'source_ref',
        )


class PhysicalElementTypeFilterSet(OrganizationalModelFilterSet):
    class Meta:
        model = PhysicalElementType
        fields = (
            'id', 'name', 'slug', 'discipline', 'element_kind', 'default_color', 'symbol_key',
            'is_pathway', 'is_supporting_structure',
        )


class PhysicalElementFilterSet(OrganizationalModelFilterSet):
    element_type_id = django_filters.ModelMultipleChoiceFilter(
        field_name='element_type',
        queryset=PhysicalElementType.objects.all(),
        label='Element type',
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
    physical_space_id = django_filters.ModelMultipleChoiceFilter(
        field_name='physical_space',
        queryset=PhysicalSpace.objects.all(),
        label='Physical space',
    )

    class Meta:
        model = PhysicalElement
        fields = (
            'id', 'name', 'slug', 'element_type_id', 'site_id', 'location_id', 'physical_space_id',
            'label', 'role', 'manufacturer', 'model_name', 'asset_tag', 'install_state', 'design_state',
            'confidence',
        )


class PhysicalObjectBindingFilterSet(OrganizationalModelFilterSet):
    physical_element_id = django_filters.ModelMultipleChoiceFilter(
        field_name='physical_element',
        queryset=PhysicalElement.objects.all(),
        label='Physical element',
    )
    spatial_placement_id = django_filters.ModelMultipleChoiceFilter(
        field_name='spatial_placement',
        queryset=SpatialPlacement.objects.all(),
        label='Spatial placement',
    )
    assigned_object_type_id = django_filters.ModelMultipleChoiceFilter(
        field_name='assigned_object_type',
        queryset=ContentType.objects.all(),
        label='Assigned object type',
    )

    class Meta:
        model = PhysicalObjectBinding
        fields = (
            'id', 'name', 'slug', 'physical_element_id', 'spatial_placement_id',
            'assigned_object_type_id', 'assigned_object_id', 'binding_role', 'confidence', 'is_primary',
        )


class SpatialFrameFilterSet(OrganizationalModelFilterSet):
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
    parent_frame_id = django_filters.ModelMultipleChoiceFilter(
        field_name='parent_frame',
        queryset=SpatialFrame.objects.all(),
        label='Parent frame',
    )

    class Meta:
        model = SpatialFrame
        fields = (
            'id', 'name', 'slug', 'site_id', 'location_id', 'parent_frame_id', 'units',
            'axis_orientation', 'source_document', 'source_ref',
        )


class SpatialPlacementFilterSet(OrganizationalModelFilterSet):
    spatial_frame_id = django_filters.ModelMultipleChoiceFilter(
        field_name='spatial_frame',
        queryset=SpatialFrame.objects.all(),
        label='Spatial frame',
    )
    site_id = django_filters.ModelMultipleChoiceFilter(
        field_name='spatial_frame__site',
        queryset=Site.objects.all(),
        label='Site',
    )
    location_id = django_filters.ModelMultipleChoiceFilter(
        field_name='spatial_frame__location',
        queryset=Location.objects.all(),
        label='Location',
    )
    assigned_object_type_id = django_filters.ModelMultipleChoiceFilter(
        field_name='assigned_object_type',
        queryset=ContentType.objects.all(),
        label='Assigned object type',
    )

    class Meta:
        model = SpatialPlacement
        fields = (
            'id', 'name', 'slug', 'spatial_frame_id', 'site_id', 'location_id',
            'assigned_object_type_id', 'assigned_object_id', 'anchor', 'placement_kind',
            'confidence', 'source_document', 'source_ref',
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
