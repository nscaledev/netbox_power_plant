from django.contrib.contenttypes.models import ContentType
from django.urls import NoReverseMatch
from dcim.models import Device, Location, PowerPort, Rack, Site
from tenancy.models import Tenant
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
    CapacityReservationStatusChoices,
    DesignStateChoices,
    InternalPowerBusAttachmentRoleChoices,
    InternalPowerBusRoleChoices,
    NodeKindChoices,
    PhaseModeChoices,
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    PlantExtractionMethodChoices,
    PlantSourceLayerKindChoices,
    PlantSourceTypeChoices,
    PlacementLabelModeChoices,
    PlacementScopeChoices,
    PlacementSymbolKindChoices,
    PowerDomainKindChoices,
    PowerFindingSeverityChoices,
    PowerFindingStatusChoices,
    PowerSystemScopeChoices,
    PowerValidationRunKindChoices,
    PowerValidationRunStatusChoices,
    RedundancyTopologyChoices,
    SegmentKindChoices,
    SpatialAnchorChoices,
    SpatialAxisOrientationChoices,
    SpatialConfidenceChoices,
    SpatialPlacementKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TerminalRoleChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import (
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
    PowerDomain,
    PowerFinding,
    PowerArchitectureTemplate,
    PowerSystem,
    PowerHandoffPoint,
    PowerValidationRun,
    RedundancyGroup,
    SpatialFrame,
    SpatialPlacement,
    TransformerDetail,
    UPSDetail,
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


class NestedTenantSerializer(WritableNestedSerializer):

    class Meta:
        model = Tenant
        fields = ('id', 'url', 'display', 'name', 'slug')
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


class NestedSpatialFrameSerializer(WritableNestedSerializer):

    class Meta:
        model = SpatialFrame
        fields = ('id', 'url', 'display', 'name', 'slug')
        brief_fields = fields


class NestedSpatialPlacementSerializer(WritableNestedSerializer):

    class Meta:
        model = SpatialPlacement
        fields = ('id', 'url', 'display', 'name', 'slug', 'placement_kind', 'confidence')
        brief_fields = fields


class NestedPlantSourceDocumentSerializer(WritableNestedSerializer):

    class Meta:
        model = PlantSourceDocument
        fields = ('id', 'url', 'display', 'name', 'slug', 'source_type', 'discipline', 'document_id', 'revision')
        brief_fields = fields


class NestedPlantSourceSheetSerializer(WritableNestedSerializer):

    class Meta:
        model = PlantSourceSheet
        fields = ('id', 'url', 'display', 'name', 'slug', 'sheet_number', 'title', 'page_index')
        brief_fields = fields


class NestedPlantSourceLayerSerializer(WritableNestedSerializer):

    class Meta:
        model = PlantSourceLayer
        fields = ('id', 'url', 'display', 'name', 'slug', 'layer_name', 'layer_kind', 'discipline')
        brief_fields = fields


class NestedPhysicalSpaceSerializer(WritableNestedSerializer):

    class Meta:
        model = PhysicalSpace
        fields = ('id', 'url', 'display', 'name', 'slug', 'space_kind', 'floor_label')
        brief_fields = fields


class NestedPhysicalElementTypeSerializer(WritableNestedSerializer):

    class Meta:
        model = PhysicalElementType
        fields = ('id', 'url', 'display', 'name', 'slug', 'discipline', 'element_kind')
        brief_fields = fields


class NestedPhysicalElementSerializer(WritableNestedSerializer):

    class Meta:
        model = PhysicalElement
        fields = ('id', 'url', 'display', 'name', 'slug', 'label', 'role')
        brief_fields = fields


class NestedPhysicalObjectBindingSerializer(WritableNestedSerializer):

    class Meta:
        model = PhysicalObjectBinding
        fields = ('id', 'url', 'display', 'name', 'slug', 'binding_role', 'is_primary')
        brief_fields = fields


class NestedPowerArchitectureTemplateSerializer(WritableNestedSerializer):

    class Meta:
        model = PowerArchitectureTemplate
        fields = ('id', 'url', 'display', 'name', 'slug', 'version')
        brief_fields = fields


class NestedInstantiationRunSerializer(WritableNestedSerializer):

    class Meta:
        model = InstantiationRun
        fields = ('id', 'url', 'display', 'name', 'slug', 'status', 'dry_run')
        brief_fields = fields


class NestedPowerValidationRunSerializer(WritableNestedSerializer):

    class Meta:
        model = PowerValidationRun
        fields = ('id', 'url', 'display', 'name', 'slug', 'run_kind', 'status')
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


class PowerValidationRunSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    run_kind = ChoiceField(choices=PowerValidationRunKindChoices, required=False)
    status = ChoiceField(choices=PowerValidationRunStatusChoices, required=False)

    class Meta:
        model = PowerValidationRun
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'run_kind', 'status',
            'started_at', 'completed_at', 'finding_count', 'description', 'comments', 'tags',
            'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'run_kind', 'status', 'finding_count')


class PowerFindingSerializer(OrganizationalModelSerializer):
    run = NestedPowerValidationRunSerializer(nested=True)
    power_system = NestedPowerSystemSerializer(nested=True)
    assigned_object_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        required=False,
        allow_null=True,
    )
    assigned_object = serializers.SerializerMethodField(read_only=True)
    severity = ChoiceField(choices=PowerFindingSeverityChoices, required=False)
    status = ChoiceField(choices=PowerFindingStatusChoices, required=False)

    class Meta:
        model = PowerFinding
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'run', 'power_system', 'fingerprint',
            'finding_type', 'severity', 'status', 'message', 'assigned_object_type', 'assigned_object_id',
            'assigned_object', 'assigned_to', 'suppressed_until', 'resolved_at', 'first_seen', 'last_seen',
            'details', 'description', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'finding_type', 'severity', 'status')

    def get_assigned_object(self, obj):
        assigned_object = obj.assigned_object
        if assigned_object is None:
            return None
        return {
            'id': assigned_object.pk,
            'display': str(assigned_object),
            'url': assigned_object.get_absolute_url() if hasattr(assigned_object, 'get_absolute_url') else None,
        }

    def validate(self, data):
        data = super().validate(data)
        run = data.get('run', getattr(self.instance, 'run', None))
        power_system = data.get('power_system', getattr(self.instance, 'power_system', None))
        assigned_object_type = data.get('assigned_object_type', getattr(self.instance, 'assigned_object_type', None))
        assigned_object_id = data.get('assigned_object_id', getattr(self.instance, 'assigned_object_id', None))

        errors = {}
        if run and power_system and run.power_system_id != power_system.pk:
            errors['power_system'] = 'The finding power system must match the validation run power system.'

        if bool(assigned_object_type) != bool(assigned_object_id):
            errors['assigned_object_id'] = 'Select both an assigned object type and object ID, or leave both blank.'
        elif assigned_object_type and assigned_object_id:
            model_class = assigned_object_type.model_class()
            try:
                assigned_object_type.get_object_for_this_type(pk=assigned_object_id)
            except (AttributeError, model_class.DoesNotExist if model_class is not None else ContentType.DoesNotExist):
                errors['assigned_object_id'] = 'The assigned object could not be found.'

        if errors:
            raise ValidationError(errors)

        return data


class PowerArchitectureTemplateSerializer(OrganizationalModelSerializer):

    class Meta:
        model = PowerArchitectureTemplate
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'version', 'is_active',
            'default_context', 'description', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'version', 'is_active')


class InstantiationRunSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    template = NestedPowerArchitectureTemplateSerializer(nested=True)

    class Meta:
        model = InstantiationRun
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'template',
            'status', 'dry_run', 'context', 'artifact_count', 'description', 'comments',
            'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'status', 'dry_run', 'artifact_count')


class InstantiationArtifactSerializer(OrganizationalModelSerializer):
    run = NestedInstantiationRunSerializer(nested=True)
    object_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        required=False,
        allow_null=True,
    )
    object = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = InstantiationArtifact
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'run', 'artifact_type',
            'action', 'status', 'template_key', 'stable_slug', 'object_type', 'object_id',
            'object', 'proposed_data', 'description', 'comments', 'tags', 'custom_fields',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'artifact_type', 'action', 'status')

    def get_object(self, obj):
        return _serialize_assigned_object(obj.object)


def _serialize_assigned_object(assigned_object):
    if assigned_object is None:
        return None

    url = None
    if hasattr(assigned_object, 'get_absolute_url'):
        try:
            url = assigned_object.get_absolute_url()
        except NoReverseMatch:
            url = None

    return {
        'id': assigned_object.pk,
        'display': str(assigned_object),
        'url': url,
    }


def _resolve_assigned_object(errors, assigned_object_type, assigned_object_id):
    if not assigned_object_type or not assigned_object_id:
        errors['assigned_object_id'] = 'Select an assigned object.'
        return None

    model_class = assigned_object_type.model_class()
    object_does_not_exist = model_class.DoesNotExist if model_class is not None else ContentType.DoesNotExist
    try:
        return assigned_object_type.get_object_for_this_type(pk=assigned_object_id)
    except (AttributeError, object_does_not_exist):
        errors['assigned_object_id'] = 'The assigned object could not be found.'
        return None


class PlantSourceDocumentSerializer(OrganizationalModelSerializer):
    site = NestedSiteSerializer(nested=True)
    location = NestedLocationSerializer(nested=True, required=False, allow_null=True)
    source_type = ChoiceField(choices=PlantSourceTypeChoices, required=False)
    discipline = ChoiceField(choices=PlantDisciplineChoices, required=False)

    class Meta:
        model = PlantSourceDocument
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'site', 'location', 'source_type', 'discipline',
            'document_id', 'revision', 'issued_at', 'source_uri', 'checksum', 'metadata', 'description',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'source_type', 'discipline')


class PlantSourceSheetSerializer(OrganizationalModelSerializer):
    source_document = NestedPlantSourceDocumentSerializer(nested=True)

    class Meta:
        model = PlantSourceSheet
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'source_document', 'sheet_number', 'title', 'scale',
            'page_index', 'metadata', 'description', 'comments', 'tags', 'custom_fields', 'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'sheet_number', 'title', 'page_index')


class PlantSourceLayerSerializer(OrganizationalModelSerializer):
    source_sheet = NestedPlantSourceSheetSerializer(nested=True)
    layer_kind = ChoiceField(choices=PlantSourceLayerKindChoices, required=False)
    discipline = ChoiceField(choices=PlantDisciplineChoices, required=False)

    class Meta:
        model = PlantSourceLayer
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'source_sheet', 'layer_name', 'layer_kind',
            'discipline', 'is_visible', 'metadata', 'description', 'comments', 'tags', 'custom_fields',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'layer_name', 'layer_kind', 'discipline')


class PlantProvenanceSerializer(OrganizationalModelSerializer):
    assigned_object_type = serializers.PrimaryKeyRelatedField(queryset=ContentType.objects.all())
    assigned_object = serializers.SerializerMethodField(read_only=True)
    source_document = NestedPlantSourceDocumentSerializer(nested=True, required=False, allow_null=True)
    source_sheet = NestedPlantSourceSheetSerializer(nested=True, required=False, allow_null=True)
    source_layer = NestedPlantSourceLayerSerializer(nested=True, required=False, allow_null=True)
    extraction_method = ChoiceField(choices=PlantExtractionMethodChoices, required=False)
    confidence = ChoiceField(choices=SpatialConfidenceChoices, required=False)

    class Meta:
        model = PlantProvenance
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'assigned_object_type', 'assigned_object_id',
            'assigned_object', 'source_document', 'source_sheet', 'source_layer', 'extraction_method',
            'source_ref', 'confidence', 'is_authoritative', 'extracted_at', 'metadata', 'description',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'extraction_method', 'confidence')

    def get_assigned_object(self, obj):
        return _serialize_assigned_object(obj.assigned_object)

    def validate(self, data):
        data = super().validate(data)
        assigned_object_type = data.get('assigned_object_type', getattr(self.instance, 'assigned_object_type', None))
        assigned_object_id = data.get('assigned_object_id', getattr(self.instance, 'assigned_object_id', None))
        source_document = data.get('source_document', getattr(self.instance, 'source_document', None))
        source_sheet = data.get('source_sheet', getattr(self.instance, 'source_sheet', None))
        source_layer = data.get('source_layer', getattr(self.instance, 'source_layer', None))

        errors = {}
        _resolve_assigned_object(errors, assigned_object_type, assigned_object_id)

        if source_sheet and source_document and source_sheet.source_document_id != source_document.pk:
            errors['source_sheet'] = 'The selected sheet must belong to the selected source document.'

        if source_layer:
            if source_sheet and source_layer.source_sheet_id != source_sheet.pk:
                errors['source_layer'] = 'The selected layer must belong to the selected source sheet.'
            if source_document and source_layer.source_sheet.source_document_id != source_document.pk:
                errors['source_layer'] = 'The selected layer must belong to the selected source document.'

        if errors:
            raise ValidationError(errors)

        return data


class PhysicalSpaceSerializer(OrganizationalModelSerializer):
    site = NestedSiteSerializer(nested=True)
    location = NestedLocationSerializer(nested=True, required=False, allow_null=True)
    spatial_frame = NestedSpatialFrameSerializer(nested=True, required=False, allow_null=True)
    parent_space = NestedPhysicalSpaceSerializer(nested=True, required=False, allow_null=True)
    space_kind = ChoiceField(choices=PhysicalSpaceKindChoices, required=False)
    confidence = ChoiceField(choices=SpatialConfidenceChoices, required=False)

    class Meta:
        model = PhysicalSpace
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'site', 'location', 'spatial_frame', 'parent_space',
            'space_kind', 'floor_label', 'z_min', 'z_max', 'boundary_geometry', 'source_document',
            'source_ref', 'confidence', 'metadata', 'description', 'comments', 'tags', 'custom_fields',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'space_kind', 'floor_label')


class PhysicalElementTypeSerializer(OrganizationalModelSerializer):
    discipline = ChoiceField(choices=PlantDisciplineChoices, required=False)
    element_kind = ChoiceField(choices=PhysicalElementKindChoices, required=False)

    class Meta:
        model = PhysicalElementType
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'discipline', 'element_kind', 'default_width',
            'default_depth', 'default_height', 'default_color', 'symbol_key', 'is_pathway',
            'is_supporting_structure', 'metadata', 'description', 'comments', 'tags', 'custom_fields',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'discipline', 'element_kind')


class PhysicalElementSerializer(OrganizationalModelSerializer):
    element_type = NestedPhysicalElementTypeSerializer(nested=True)
    site = NestedSiteSerializer(nested=True)
    location = NestedLocationSerializer(nested=True, required=False, allow_null=True)
    physical_space = NestedPhysicalSpaceSerializer(nested=True, required=False, allow_null=True)
    install_state = ChoiceField(choices=TopologyStateChoices, required=False)
    design_state = ChoiceField(choices=DesignStateChoices, required=False)
    confidence = ChoiceField(choices=SpatialConfidenceChoices, required=False)

    class Meta:
        model = PhysicalElement
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'element_type', 'site', 'location', 'physical_space',
            'label', 'role', 'manufacturer', 'model_name', 'asset_tag', 'install_state', 'design_state',
            'source_label', 'confidence', 'metadata', 'description', 'comments', 'tags', 'custom_fields',
            'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'label', 'role')


class PhysicalObjectBindingSerializer(OrganizationalModelSerializer):
    physical_element = NestedPhysicalElementSerializer(nested=True, required=False, allow_null=True)
    spatial_placement = NestedSpatialPlacementSerializer(nested=True, required=False, allow_null=True)
    assigned_object_type = serializers.PrimaryKeyRelatedField(queryset=ContentType.objects.all())
    assigned_object = serializers.SerializerMethodField(read_only=True)
    binding_role = ChoiceField(choices=PhysicalObjectBindingRoleChoices, required=False)
    confidence = ChoiceField(choices=SpatialConfidenceChoices, required=False)

    class Meta:
        model = PhysicalObjectBinding
        fields = (
            'id', 'url', 'display', 'name', 'slug', 'physical_element', 'spatial_placement',
            'assigned_object_type', 'assigned_object_id', 'assigned_object', 'binding_role', 'confidence',
            'is_primary', 'metadata', 'description', 'comments', 'tags', 'custom_fields', 'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'binding_role', 'confidence', 'is_primary')

    def get_assigned_object(self, obj):
        return _serialize_assigned_object(obj.assigned_object)

    def validate(self, data):
        data = super().validate(data)
        physical_element = data.get('physical_element', getattr(self.instance, 'physical_element', None))
        spatial_placement = data.get('spatial_placement', getattr(self.instance, 'spatial_placement', None))
        assigned_object_type = data.get('assigned_object_type', getattr(self.instance, 'assigned_object_type', None))
        assigned_object_id = data.get('assigned_object_id', getattr(self.instance, 'assigned_object_id', None))

        errors = {}
        if not physical_element and not spatial_placement:
            errors['physical_element'] = 'Select a physical element, spatial placement, or both.'

        _resolve_assigned_object(errors, assigned_object_type, assigned_object_id)

        if physical_element and spatial_placement:
            if physical_element.site_id != spatial_placement.spatial_frame.site_id:
                errors['spatial_placement'] = (
                    'The spatial placement must belong to the same site as the physical element.'
                )

        if errors:
            raise ValidationError(errors)

        return data


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


class PowerHandoffPointSerializer(OrganizationalModelSerializer):
    power_system = NestedPowerSystemSerializer(nested=True)
    electrical_node = NestedElectricalNodeSerializer(nested=True, required=False, allow_null=True)
    electrical_terminal = NestedElectricalTerminalSerializer(nested=True, required=False, allow_null=True)
    power_port = NestedPowerPortSerializer(nested=True)
    expected_redundancy_group = NestedRedundancyGroupSerializer(nested=True, required=False, allow_null=True)
    design_state = ChoiceField(choices=DesignStateChoices, required=False)

    class Meta:
        model = PowerHandoffPoint
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'power_system', 'electrical_node',
            'electrical_terminal', 'power_port', 'expected_redundancy_group', 'delivery_role',
            'feed_label', 'design_state', 'description', 'comments', 'tags', 'custom_fields', 'created',
            'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'feed_label', 'design_state')

    def validate(self, data):
        data = super().validate(data)
        power_system = data.get('power_system', getattr(self.instance, 'power_system', None))
        electrical_node = data.get('electrical_node', getattr(self.instance, 'electrical_node', None))
        electrical_terminal = data.get('electrical_terminal', getattr(self.instance, 'electrical_terminal', None))
        power_port = data.get('power_port', getattr(self.instance, 'power_port', None))
        expected_redundancy_group = data.get(
            'expected_redundancy_group', getattr(self.instance, 'expected_redundancy_group', None)
        )

        errors = {}
        if not power_port:
            errors['power_port'] = 'Select a power port.'

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


class CapacityReservationSerializer(OrganizationalModelSerializer):
    node = NestedElectricalNodeSerializer(nested=True)
    tenant = NestedTenantSerializer(nested=True)
    rack = NestedRackSerializer(nested=True, required=False, allow_null=True)
    status = ChoiceField(choices=CapacityReservationStatusChoices, required=False)

    class Meta:
        model = CapacityReservation
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'node', 'tenant', 'rack',
            'reserved_kw', 'status', 'valid_from', 'valid_until', 'notes', 'description',
            'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'node', 'reserved_kw', 'status')

    def validate(self, data):
        data = super().validate(data)
        node = data.get('node', getattr(self.instance, 'node', None))
        rack = data.get('rack', getattr(self.instance, 'rack', None))
        valid_from = data.get('valid_from', getattr(self.instance, 'valid_from', None))
        valid_until = data.get('valid_until', getattr(self.instance, 'valid_until', None))

        errors = {}
        if rack and node and rack.site_id != node.site_id:
            errors['rack'] = 'The selected rack must belong to the same site as the electrical node.'
        if valid_from and valid_until and valid_until < valid_from:
            errors['valid_until'] = 'Valid until cannot be earlier than valid from.'
        if errors:
            raise ValidationError(errors)
        return data


class ElectricalNodeDetailSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(read_only=True)
    display = serializers.SerializerMethodField(read_only=True)
    node = NestedElectricalNodeSerializer(nested=True)
    allowed_node_kinds = ()

    class Meta:
        fields = ('id', 'url', 'display', 'node')

    def get_url(self, obj):
        if not hasattr(obj, 'get_absolute_url'):
            return None
        try:
            return obj.get_absolute_url()
        except NoReverseMatch:
            return None

    def get_display(self, obj):
        return str(obj)

    def validate(self, data):
        data = super().validate(data)
        node = data.get('node', getattr(self.instance, 'node', None))
        if node is not None and self.allowed_node_kinds and node.node_kind not in self.allowed_node_kinds:
            raise ValidationError({'node': 'The selected electrical node kind is not valid for this detail record.'})
        return data


class UPSDetailSerializer(ElectricalNodeDetailSerializer):
    allowed_node_kinds = (NodeKindChoices.KIND_UPS,)

    class Meta(ElectricalNodeDetailSerializer.Meta):
        model = UPSDetail
        fields = ElectricalNodeDetailSerializer.Meta.fields + (
            'ups_topology', 'battery_autonomy_minutes', 'module_count', 'module_rating_kw',
            'parallel_group_id', 'maintenance_bypass_present',
        )


class GeneratorDetailSerializer(ElectricalNodeDetailSerializer):
    allowed_node_kinds = (NodeKindChoices.KIND_GENERATOR,)

    class Meta(ElectricalNodeDetailSerializer.Meta):
        model = GeneratorDetail
        fields = ElectricalNodeDetailSerializer.Meta.fields + (
            'fuel_type', 'runtime_at_full_load_hours', 'cooling_type', 'ats_group_id',
            'automatic_transfer_time_ms',
        )


class TransformerDetailSerializer(ElectricalNodeDetailSerializer):
    allowed_node_kinds = (NodeKindChoices.KIND_TRANSFORMER,)

    class Meta(ElectricalNodeDetailSerializer.Meta):
        model = TransformerDetail
        fields = ElectricalNodeDetailSerializer.Meta.fields + (
            'primary_kv', 'secondary_kv', 'kva_rating', 'vector_group', 'impedance_pct', 'cooling_type',
        )

    def validate(self, data):
        data = super().validate(data)
        impedance_pct = data.get('impedance_pct', getattr(self.instance, 'impedance_pct', None))
        if impedance_pct is not None and (impedance_pct < 0 or impedance_pct > 100):
            raise ValidationError({'impedance_pct': 'Percentage values must be between 0 and 100.'})
        return data


class BESSDetailSerializer(ElectricalNodeDetailSerializer):
    allowed_node_kinds = (NodeKindChoices.KIND_BESS,)

    class Meta(ElectricalNodeDetailSerializer.Meta):
        model = BESSDetail
        fields = ElectricalNodeDetailSerializer.Meta.fields + (
            'technology', 'energy_capacity_kwh', 'peak_power_kw', 'charge_rate_kw',
            'usable_soc_min_pct', 'usable_soc_max_pct',
        )

    def validate(self, data):
        data = super().validate(data)
        min_pct = data.get('usable_soc_min_pct', getattr(self.instance, 'usable_soc_min_pct', None))
        max_pct = data.get('usable_soc_max_pct', getattr(self.instance, 'usable_soc_max_pct', None))
        errors = {}
        for field_name, value in (('usable_soc_min_pct', min_pct), ('usable_soc_max_pct', max_pct)):
            if value is not None and (value < 0 or value > 100):
                errors[field_name] = 'Percentage values must be between 0 and 100.'
        if min_pct is not None and max_pct is not None and max_pct < min_pct:
            errors['usable_soc_max_pct'] = 'Maximum usable state of charge cannot be lower than the minimum.'
        if errors:
            raise ValidationError(errors)
        return data


class BuswaySectionDetailSerializer(ElectricalNodeDetailSerializer):
    allowed_node_kinds = (NodeKindChoices.KIND_BUSWAY_RUN,)
    busway_system = NestedElectricalNodeSerializer(nested=True)

    class Meta(ElectricalNodeDetailSerializer.Meta):
        model = BuswaySectionDetail
        fields = ElectricalNodeDetailSerializer.Meta.fields + (
            'busway_system', 'section_index', 'rated_ampacity_a', 'plug_count', 'plug_spacing_m',
        )

    def validate(self, data):
        data = super().validate(data)
        node = data.get('node', getattr(self.instance, 'node', None))
        busway_system = data.get('busway_system', getattr(self.instance, 'busway_system', None))
        errors = {}
        if busway_system is not None:
            if busway_system.node_kind != NodeKindChoices.KIND_BUSWAY_RUN:
                errors['busway_system'] = 'The busway system must be a busway run node.'
            if node is not None and busway_system.power_system_id != node.power_system_id:
                errors['busway_system'] = 'The busway system must belong to the same power system as the section node.'
        if errors:
            raise ValidationError(errors)
        return data


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


class SpatialFrameSerializer(OrganizationalModelSerializer):
    site = NestedSiteSerializer(nested=True)
    location = NestedLocationSerializer(nested=True, required=False, allow_null=True)
    parent_frame = NestedSpatialFrameSerializer(nested=True, required=False, allow_null=True)
    axis_orientation = ChoiceField(choices=SpatialAxisOrientationChoices, required=False)
    confidence = ChoiceField(choices=SpatialConfidenceChoices, required=False)

    class Meta:
        model = SpatialFrame
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'site', 'location', 'parent_frame',
            'origin_x_in_parent', 'origin_y_in_parent', 'width', 'height', 'units', 'axis_orientation',
            'source_document', 'source_ref', 'confidence', 'metadata', 'description', 'comments', 'tags',
            'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'site', 'location')

    def validate(self, data):
        data = super().validate(data)
        site = data.get('site', getattr(self.instance, 'site', None))
        location = data.get('location', getattr(self.instance, 'location', None))
        parent_frame = data.get('parent_frame', getattr(self.instance, 'parent_frame', None))

        errors = {}
        if site and location and location.site_id != site.pk:
            errors['location'] = 'The selected location must belong to the selected site.'

        if site and parent_frame and parent_frame.site_id != site.pk:
            errors['parent_frame'] = 'The parent frame must belong to the same site.'

        if location and parent_frame and parent_frame.location_id and location.pk != parent_frame.location_id:
            errors['location'] = 'Child and parent frame locations must match when both are set.'

        if self.instance and parent_frame and parent_frame.pk == self.instance.pk:
            errors['parent_frame'] = 'A spatial frame cannot be its own parent.'

        if errors:
            raise ValidationError(errors)

        return data


class SpatialPlacementSerializer(OrganizationalModelSerializer):
    spatial_frame = NestedSpatialFrameSerializer(nested=True)
    assigned_object_type = serializers.PrimaryKeyRelatedField(queryset=ContentType.objects.all())
    assigned_object = serializers.SerializerMethodField(read_only=True)
    anchor = ChoiceField(choices=SpatialAnchorChoices, required=False)
    placement_kind = ChoiceField(choices=SpatialPlacementKindChoices, required=False)
    confidence = ChoiceField(choices=SpatialConfidenceChoices, required=False)

    class Meta:
        model = SpatialPlacement
        fields = (
            'id', 'url', 'display_url', 'display', 'name', 'slug', 'spatial_frame', 'assigned_object_type',
            'assigned_object_id', 'assigned_object', 'x', 'y', 'z', 'width', 'depth', 'height', 'rotation_degrees',
            'anchor', 'placement_kind', 'confidence', 'source_document', 'source_ref', 'metadata',
            'description', 'comments', 'tags', 'custom_fields', 'created', 'last_updated',
        )
        brief_fields = ('id', 'url', 'display', 'name', 'slug', 'spatial_frame', 'placement_kind', 'confidence')

    def get_assigned_object(self, obj):
        assigned_object = obj.assigned_object
        if assigned_object is None:
            return None
        return {
            'id': assigned_object.pk,
            'display': str(assigned_object),
            'url': assigned_object.get_absolute_url() if hasattr(assigned_object, 'get_absolute_url') else None,
        }

    def validate(self, data):
        data = super().validate(data)
        spatial_frame = data.get('spatial_frame', getattr(self.instance, 'spatial_frame', None))
        assigned_object_type = data.get('assigned_object_type', getattr(self.instance, 'assigned_object_type', None))
        assigned_object_id = data.get('assigned_object_id', getattr(self.instance, 'assigned_object_id', None))

        errors = {}
        assigned_object = None
        if not assigned_object_type or not assigned_object_id:
            errors['assigned_object_id'] = 'Select an assigned object.'
        else:
            model_class = assigned_object_type.model_class()
            try:
                assigned_object = assigned_object_type.get_object_for_this_type(pk=assigned_object_id)
            except (AttributeError, model_class.DoesNotExist if model_class is not None else ContentType.DoesNotExist):
                errors['assigned_object_id'] = 'The assigned object could not be found.'

        if spatial_frame and assigned_object is not None:
            assigned_site_id = self._assigned_object_site_id(assigned_object)
            if assigned_site_id and assigned_site_id != spatial_frame.site_id:
                errors['assigned_object_id'] = 'The assigned object must belong to the spatial frame site.'

            assigned_location_id = self._assigned_object_location_id(assigned_object)
            if (
                assigned_location_id
                and spatial_frame.location_id
                and assigned_location_id != spatial_frame.location_id
            ):
                errors['assigned_object_id'] = 'The assigned object must belong to the spatial frame location when both are known.'

        if errors:
            raise ValidationError(errors)

        return data

    def _assigned_object_site_id(self, assigned_object):
        if hasattr(assigned_object, 'site_id'):
            return assigned_object.site_id

        power_system = getattr(assigned_object, 'power_system', None)
        if power_system is not None:
            return power_system.site_id

        node = getattr(assigned_object, 'node', None)
        if node is not None:
            return node.site_id

        device = getattr(assigned_object, 'device', None)
        if device is not None:
            return device.site_id

        rack = getattr(assigned_object, 'rack', None)
        if rack is not None:
            return rack.site_id

        power_port = getattr(assigned_object, 'power_port', None)
        if power_port is not None:
            return power_port.device.site_id

        internal_power_bus = getattr(assigned_object, 'internal_power_bus', None)
        if internal_power_bus is not None:
            return internal_power_bus.power_system.site_id

        return None

    def _assigned_object_location_id(self, assigned_object):
        if hasattr(assigned_object, 'location_id'):
            return assigned_object.location_id

        power_system = getattr(assigned_object, 'power_system', None)
        if power_system is not None:
            return power_system.location_id

        node = getattr(assigned_object, 'node', None)
        if node is not None:
            return node.location_id

        device = getattr(assigned_object, 'device', None)
        if device is not None:
            return device.location_id or (device.rack.location_id if device.rack_id else None)

        rack = getattr(assigned_object, 'rack', None)
        if rack is not None:
            return rack.location_id

        power_port = getattr(assigned_object, 'power_port', None)
        if power_port is not None:
            device = power_port.device
            return device.location_id or (device.rack.location_id if device.rack_id else None)

        internal_power_bus = getattr(assigned_object, 'internal_power_bus', None)
        if internal_power_bus is not None:
            return internal_power_bus.power_system.location_id

        return None


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
                errors['location'] = 'Leave location blank when the power system does not resolve to a location spatial frame.'

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
                errors['electrical_node'] = 'A placement already exists for this node in the resolved spatial scope.'

        if errors:
            raise ValidationError(errors)

        return data


class InstantiationRunActionSerializer(serializers.Serializer):
    power_system = serializers.PrimaryKeyRelatedField(queryset=PowerSystem.objects.all())
    template = serializers.PrimaryKeyRelatedField(queryset=PowerArchitectureTemplate.objects.filter(is_active=True))
    context = serializers.JSONField(required=False, default=dict)
    apply = serializers.BooleanField(required=False, default=False)
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=128)


class InstantiationRunApplySerializer(serializers.Serializer):
    context = serializers.JSONField(required=False, default=None, allow_null=True)
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=128)


class ValidationRunActionSerializer(serializers.Serializer):
    power_system = serializers.PrimaryKeyRelatedField(queryset=PowerSystem.objects.all())
    run_kind = ChoiceField(choices=PowerValidationRunKindChoices)
    name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    request_id = serializers.CharField(required=False, allow_blank=True, max_length=128)

    def validate(self, data):
        data = super().validate(data)
        if data['run_kind'] == PowerValidationRunKindChoices.KIND_SCENARIO:
            raise ValidationError({
                'run_kind': 'Scenario validation requires an explicit scenario endpoint; use impact endpoints for non-mutating scenario analysis.'
            })
        return data


class FindingSuppressActionSerializer(serializers.Serializer):
    suppressed_until = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)


class FindingResolveActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


class FindingAcknowledgeActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True)


class CapacityRollupQuerySerializer(serializers.Serializer):
    node_id = serializers.IntegerField()


class ImpactNodeOfflineSerializer(serializers.Serializer):
    power_system = serializers.PrimaryKeyRelatedField(queryset=PowerSystem.objects.all())
    node = serializers.PrimaryKeyRelatedField(queryset=ElectricalNode.objects.all())

    def validate(self, data):
        data = super().validate(data)
        if data['node'].power_system_id != data['power_system'].pk:
            raise ValidationError({'node': 'The electrical node must belong to the selected power system.'})
        return data


class ImpactSegmentCutSerializer(serializers.Serializer):
    power_system = serializers.PrimaryKeyRelatedField(queryset=PowerSystem.objects.all())
    segment = serializers.PrimaryKeyRelatedField(queryset=ElectricalSegment.objects.all())

    def validate(self, data):
        data = super().validate(data)
        if data['segment'].power_system_id != data['power_system'].pk:
            raise ValidationError({'segment': 'The electrical segment must belong to the selected power system.'})
        return data


class ImpactDomainLostSerializer(serializers.Serializer):
    power_system = serializers.PrimaryKeyRelatedField(queryset=PowerSystem.objects.all())
    domain = serializers.PrimaryKeyRelatedField(queryset=PowerDomain.objects.all())

    def validate(self, data):
        data = super().validate(data)
        if data['domain'].power_system_id != data['power_system'].pk:
            raise ValidationError({'domain': 'The power domain must belong to the selected power system.'})
        return data


class NeocloudCockpitSerializer(serializers.Serializer):
    power_system = serializers.PrimaryKeyRelatedField(queryset=PowerSystem.objects.all())
    scenario_type = serializers.ChoiceField(choices=(
        ('node_offline', 'Node offline'),
        ('segment_cut', 'Segment cut'),
        ('domain_lost', 'Domain lost'),
    ))
    target_id = serializers.IntegerField()

    def validate(self, data):
        data = super().validate(data)
        power_system = data['power_system']
        scenario_type = data['scenario_type']
        target_id = data['target_id']
        if scenario_type == 'node_offline':
            exists = ElectricalNode.objects.filter(pk=target_id, power_system=power_system).exists()
            field = 'node'
        elif scenario_type == 'segment_cut':
            exists = ElectricalSegment.objects.filter(pk=target_id, power_system=power_system).exists()
            field = 'segment'
        else:
            exists = PowerDomain.objects.filter(pk=target_id, power_system=power_system).exists()
            field = 'domain'
        if not exists:
            raise ValidationError({'target_id': f'The selected {field} must belong to the selected power system.'})
        return data


class InstantiationRunLookupSerializer(serializers.Serializer):
    run = serializers.PrimaryKeyRelatedField(queryset=InstantiationRun.objects.all())
