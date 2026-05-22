import json

from django import forms

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from pathlib import Path
from dcim.models import Device, Location, PowerPort, Rack, Site
from tenancy.models import Tenant
try:
    from netbox.forms import (
        NetBoxModelFilterSetForm,
        NetBoxModelForm,
        OrganizationalModelFilterSetForm,
        OrganizationalModelForm,
    )
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
    CapacityReservationStatusChoices,
    DesignStateChoices,
    NodeKindChoices,
    PhaseModeChoices,
    InternalPowerBusAttachmentRoleChoices,
    InternalPowerBusRoleChoices,
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
    InstantiationRun,
)
from .services.cad_uploads import MAX_CAD_UPLOAD_PACKAGE_BYTES


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError(self.error_messages['required'], code='required')
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [forms.FileField.clean(self, file, initial) for file in files]


class MadisonCadUnderlayIngestForm(forms.Form):
    site_slug = forms.SlugField(
        required=True,
        max_length=100,
        initial='gs001',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Site slug to model. The site will be created if it does not already exist.',
    )
    site_name = forms.CharField(
        required=False,
        max_length=100,
        initial='Madison, NC',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Site name to create or update for this CAD package.',
    )
    cad_package = MultipleFileField(
        required=True,
        label='CAD package',
        widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': '.zip,.dwg,.pcp,.ctb,.stb,.dxf'}),
        help_text=(
            'Upload a ZIP archive of the CAD folder, or select the DWG/PCP files together. '
            f'Total upload size must be {MAX_CAD_UPLOAD_PACKAGE_BYTES // (1024 * 1024 * 1024)} GiB or less.'
        ),
    )
    source_units = forms.CharField(
        required=True,
        max_length=32,
        initial='inch',
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='CAD model units used to derive the physical grid.',
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Ingest this CAD package and create or update the site modeling underlay records.',
    )

    def clean_cad_package(self):
        uploaded_files = self.cleaned_data['cad_package']
        allowed_suffixes = {'.zip', '.dwg', '.pcp', '.ctb', '.stb', '.dxf'}
        unsupported = [
            uploaded_file.name
            for uploaded_file in uploaded_files
            if Path(uploaded_file.name).suffix.lower() not in allowed_suffixes
        ]
        if unsupported:
            raise forms.ValidationError(
                f"Unsupported CAD upload file type: {', '.join(unsupported)}"
            )
        if not any(Path(uploaded_file.name).suffix.lower() in {'.zip', '.dwg'} for uploaded_file in uploaded_files):
            raise forms.ValidationError('Upload a ZIP archive or at least one DWG file.')
        return uploaded_files


class MadisonCadUnderlayApprovalForm(forms.Form):
    source_units = forms.CharField(
        required=False,
        max_length=32,
        help_text='Approved CAD model units. Override only after checking the drawing settings.',
    )
    site_width = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        help_text='Approved site coordinate plane width in grid units.',
    )
    site_height = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        help_text='Approved site coordinate plane height in grid units.',
    )
    building_origin_x = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        help_text='Approved current-building lower-left X in site grid units.',
    )
    building_origin_y = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        help_text='Approved current-building lower-left Y in site grid units.',
    )
    building_width = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        help_text='Approved current-building footprint width in grid units.',
    )
    building_height = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        help_text='Approved current-building footprint height in grid units.',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    confirm = forms.BooleanField(
        required=True,
        label='I have reviewed the CAD underlay assumptions and approve them as the site spatial baseline.',
    )

    def clean(self):
        cleaned_data = super().clean()
        origin_x = cleaned_data.get('building_origin_x')
        origin_y = cleaned_data.get('building_origin_y')
        building_width = cleaned_data.get('building_width')
        building_height = cleaned_data.get('building_height')
        site_width = cleaned_data.get('site_width')
        site_height = cleaned_data.get('site_height')

        if all(value is not None for value in (origin_x, building_width, site_width)):
            if origin_x + building_width > site_width:
                self.add_error('building_width', 'Building footprint must fit inside the approved site width.')
        if all(value is not None for value in (origin_y, building_height, site_height)):
            if origin_y + building_height > site_height:
                self.add_error('building_height', 'Building footprint must fit inside the approved site height.')
        return cleaned_data

    def to_overrides(self):
        from netbox_power_plant.services.madison_cad_approval import MadisonCadApprovalOverrides

        return MadisonCadApprovalOverrides(
            source_units=self.cleaned_data.get('source_units') or '',
            site_width=self.cleaned_data.get('site_width'),
            site_height=self.cleaned_data.get('site_height'),
            building_origin_x=self.cleaned_data.get('building_origin_x'),
            building_origin_y=self.cleaned_data.get('building_origin_y'),
            building_width=self.cleaned_data.get('building_width'),
            building_height=self.cleaned_data.get('building_height'),
            notes=self.cleaned_data.get('notes') or '',
        )


class MadisonDetailedSpaceDecompositionForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Create or refresh Madison detailed data hall and gallery spaces for operator review.',
    )


class MadisonDetailedSpaceBoundaryApprovalForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Review notes',
        help_text='Optional operator note captured on each approved detailed space boundary.',
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=(
            'I have visually reviewed the Madison detailed space boundaries on the spatial review map '
            'and approve them for rack placement and binding.'
        ),
    )


class MadisonRackFootprintMaterializationForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Create or refresh Madison rack/cabinet footprint candidates and provisional NetBox rack bindings.',
    )


class MadisonRackFootprintApprovalForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Review notes',
        help_text='Optional operator note captured on approved rack footprint bindings.',
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=(
            'I have visually reviewed the Madison rack/cabinet footprints and approve the matched '
            'NetBox rack bindings as authoritative.'
        ),
    )


class SpatialReviewSpaceGeometryForm(forms.Form):
    space_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput(attrs={'data-spatial-geometry-field': 'spaceId'}),
    )
    x = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'data-spatial-geometry-field': 'x'}),
        label='X',
    )
    y = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'data-spatial-geometry-field': 'y'}),
        label='Y',
    )
    width = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'step': '0.001', 'data-spatial-geometry-field': 'width'},
        ),
        label='Width',
    )
    depth = forms.DecimalField(
        required=True,
        max_digits=12,
        decimal_places=3,
        min_value=0,
        widget=forms.NumberInput(
            attrs={'class': 'form-control', 'step': '0.001', 'data-spatial-geometry-field': 'depth'},
        ),
        label='Depth',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        label='Correction notes',
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'data-spatial-geometry-field': 'confirm'}),
        label='Save this visual geometry correction and return the boundary to review-required state.',
    )

    def clean_width(self):
        width = self.cleaned_data['width']
        if width <= 0:
            raise forms.ValidationError('Width must be greater than zero.')
        return width

    def clean_depth(self):
        depth = self.cleaned_data['depth']
        if depth <= 0:
            raise forms.ValidationError('Depth must be greater than zero.')
        return depth


class SpatialReviewSpaceGeometryApprovalForm(forms.Form):
    space_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput(attrs={'data-spatial-approval-field': 'spaceId'}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={'class': 'form-control', 'rows': 2, 'data-spatial-approval-field': 'notes'},
        ),
        label='Approval notes',
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'data-spatial-approval-field': 'confirm'}),
        label='Approve this corrected geometry as authoritative for placement and binding.',
    )


class NeocloudCockpitForm(forms.Form):
    SCENARIO_NODE_OFFLINE = 'node_offline'
    SCENARIO_SEGMENT_CUT = 'segment_cut'
    SCENARIO_DOMAIN_LOST = 'domain_lost'

    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    scenario_type = forms.ChoiceField(
        choices=(
            (SCENARIO_NODE_OFFLINE, 'Node offline'),
            (SCENARIO_SEGMENT_CUT, 'Segment cut'),
            (SCENARIO_DOMAIN_LOST, 'Domain lost'),
        ),
        required=True,
    )
    node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        selector=True,
        query_params={'power_system_id': '$power_system'},
    )
    segment = DynamicModelChoiceField(
        queryset=ElectricalSegment.objects.all(),
        required=False,
        selector=True,
        query_params={'power_system_id': '$power_system'},
    )
    domain = DynamicModelChoiceField(
        queryset=PowerDomain.objects.all(),
        required=False,
        selector=True,
        query_params={'power_system_id': '$power_system'},
    )

    fieldsets = (
        FieldSet('power_system', 'scenario_type', name='Scope'),
        FieldSet('node', 'segment', 'domain', name='Scenario Target'),
    )

    def clean(self):
        cleaned_data = super().clean()
        power_system = cleaned_data.get('power_system')
        scenario_type = cleaned_data.get('scenario_type')
        target_field = {
            self.SCENARIO_NODE_OFFLINE: 'node',
            self.SCENARIO_SEGMENT_CUT: 'segment',
            self.SCENARIO_DOMAIN_LOST: 'domain',
        }.get(scenario_type)
        target = cleaned_data.get(target_field) if target_field else None

        if target_field and target is None:
            self.add_error(target_field, 'Select the target for this scenario.')
            return cleaned_data

        if power_system and target is not None:
            target_power_system_id = getattr(target, 'power_system_id', None)
            if target_power_system_id != power_system.pk:
                self.add_error(target_field, 'The selected target must belong to the selected power system.')

        cleaned_data['target'] = target
        cleaned_data['target_id'] = target.pk if target is not None else None
        return cleaned_data


class TemplateInstantiationDryRunForm(forms.Form):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    template = forms.ModelChoiceField(
        queryset=PowerArchitectureTemplate.objects.filter(is_active=True),
        required=True,
    )
    context_json = forms.CharField(
        required=False,
        label='Context JSON',
        widget=forms.Textarea(attrs={'rows': 6}),
        help_text='Optional JSON context for repeat counts, power port IDs, redundancy groups, and naming overrides.',
    )

    fieldsets = (
        FieldSet('power_system', 'template', name='Template Scope'),
        FieldSet('context_json', name='Instantiation Context'),
    )

    def clean_context_json(self):
        value = self.cleaned_data.get('context_json') or ''
        if not value.strip():
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError(f'Enter valid JSON context: {exc.msg}') from exc
        if not isinstance(parsed, dict):
            raise forms.ValidationError('Context JSON must be an object.')
        return parsed


class TemplateInstantiationApplyForm(forms.Form):
    run = forms.ModelChoiceField(
        queryset=InstantiationRun.objects.filter(dry_run=True).order_by('-created', 'name'),
        required=True,
    )
    confirm = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Apply the reviewed dry run artifacts to the power model.',
    )

    fieldsets = (
        FieldSet('run', 'confirm', name='Reviewed Dry Run'),
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


class PowerValidationRunForm(OrganizationalModelForm):
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'power_system', name='Scope'),
        FieldSet('run_kind', 'status', 'started_at', 'completed_at', 'finding_count', name='Run'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PowerValidationRun
        fields = (
            'name',
            'slug',
            'power_system',
            'run_kind',
            'status',
            'started_at',
            'completed_at',
            'finding_count',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'run_kind': forms.Select(choices=PowerValidationRunKindChoices),
            'status': forms.Select(choices=PowerValidationRunStatusChoices),
        }


class PowerFindingForm(OrganizationalModelForm):
    run = DynamicModelChoiceField(
        queryset=PowerValidationRun.objects.all(),
        required=True,
        selector=True,
    )
    power_system = DynamicModelChoiceField(
        queryset=PowerSystem.objects.all(),
        required=True,
        selector=True,
    )
    assigned_object_type = forms.ModelChoiceField(
        queryset=ContentType.objects.all(),
        required=False,
    )
    assigned_object_id = forms.IntegerField(
        required=False,
        min_value=1,
        label='Assigned object ID',
    )
    assigned_to = DynamicModelChoiceField(
        queryset=get_user_model().objects.all(),
        required=False,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'run', 'power_system', name='Scope'),
        FieldSet('finding_type', 'severity', 'status', 'message', 'fingerprint', name='Finding'),
        FieldSet('assigned_object_type', 'assigned_object_id', 'assigned_to', name='Assignment'),
        FieldSet('suppressed_until', 'resolved_at', 'first_seen', 'last_seen', name='Lifecycle'),
        FieldSet('details', 'description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PowerFinding
        fields = (
            'name',
            'slug',
            'run',
            'power_system',
            'fingerprint',
            'finding_type',
            'severity',
            'status',
            'message',
            'assigned_object_type',
            'assigned_object_id',
            'assigned_to',
            'suppressed_until',
            'resolved_at',
            'first_seen',
            'last_seen',
            'details',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'severity': forms.Select(choices=PowerFindingSeverityChoices),
            'status': forms.Select(choices=PowerFindingStatusChoices),
            'message': forms.Textarea(attrs={'rows': 3}),
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


class PowerHandoffPointForm(OrganizationalModelForm):
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
    power_port = DynamicModelChoiceField(
        queryset=PowerPort.objects.all(),
        required=True,
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
        FieldSet('power_port', 'delivery_role', 'feed_label', name='Target'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PowerHandoffPoint
        fields = (
            'name',
            'slug',
            'power_system',
            'electrical_node',
            'electrical_terminal',
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


class CapacityReservationForm(OrganizationalModelForm):
    node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=True,
        selector=True,
    )
    tenant = DynamicModelChoiceField(
        queryset=Tenant.objects.all(),
        required=True,
        selector=True,
    )
    rack = DynamicModelChoiceField(
        queryset=Rack.objects.all(),
        required=False,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'node', 'tenant', 'rack', name='Reservation Scope'),
        FieldSet('reserved_kw', 'status', 'valid_from', 'valid_until', name='Capacity Window'),
        FieldSet('description', 'notes', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = CapacityReservation
        fields = (
            'name',
            'slug',
            'node',
            'tenant',
            'rack',
            'reserved_kw',
            'status',
            'valid_from',
            'valid_until',
            'description',
            'notes',
            'comments',
            'tags',
        )
        widgets = {
            'status': forms.Select(choices=CapacityReservationStatusChoices),
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].help_text = (
            'Planned is a forecast, confirmed is committed, active subtracts from headroom, '
            'and released no longer reserves capacity.'
        )


class ElectricalNodeDetailForm(NetBoxModelForm):
    node_kind = None

    node = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=True,
        selector=True,
    )

    class Meta:
        fields = ('node',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.node_kind:
            self.fields['node'].queryset = self.fields['node'].queryset.filter(node_kind=self.node_kind)
            self.fields['node'].query_params = {'node_kind': self.node_kind}


class UPSDetailForm(ElectricalNodeDetailForm):
    node_kind = NodeKindChoices.KIND_UPS

    fieldsets = (
        FieldSet('node', name='Electrical Node'),
        FieldSet(
            'ups_topology',
            'battery_autonomy_minutes',
            'module_count',
            'module_rating_kw',
            'parallel_group_id',
            'maintenance_bypass_present',
            name='UPS Characteristics',
        ),
    )

    class Meta(ElectricalNodeDetailForm.Meta):
        model = UPSDetail
        fields = (
            'node',
            'ups_topology',
            'battery_autonomy_minutes',
            'module_count',
            'module_rating_kw',
            'parallel_group_id',
            'maintenance_bypass_present',
        )


class GeneratorDetailForm(ElectricalNodeDetailForm):
    node_kind = NodeKindChoices.KIND_GENERATOR

    fieldsets = (
        FieldSet('node', name='Electrical Node'),
        FieldSet(
            'fuel_type',
            'runtime_at_full_load_hours',
            'cooling_type',
            'ats_group_id',
            'automatic_transfer_time_ms',
            name='Generator Characteristics',
        ),
    )

    class Meta(ElectricalNodeDetailForm.Meta):
        model = GeneratorDetail
        fields = (
            'node',
            'fuel_type',
            'runtime_at_full_load_hours',
            'cooling_type',
            'ats_group_id',
            'automatic_transfer_time_ms',
        )


class TransformerDetailForm(ElectricalNodeDetailForm):
    node_kind = NodeKindChoices.KIND_TRANSFORMER

    fieldsets = (
        FieldSet('node', name='Electrical Node'),
        FieldSet(
            'primary_kv',
            'secondary_kv',
            'kva_rating',
            'vector_group',
            'impedance_pct',
            'cooling_type',
            name='Transformer Characteristics',
        ),
    )

    class Meta(ElectricalNodeDetailForm.Meta):
        model = TransformerDetail
        fields = (
            'node',
            'primary_kv',
            'secondary_kv',
            'kva_rating',
            'vector_group',
            'impedance_pct',
            'cooling_type',
        )


class BESSDetailForm(ElectricalNodeDetailForm):
    node_kind = NodeKindChoices.KIND_BESS

    fieldsets = (
        FieldSet('node', name='Electrical Node'),
        FieldSet(
            'technology',
            'energy_capacity_kwh',
            'peak_power_kw',
            'charge_rate_kw',
            'usable_soc_min_pct',
            'usable_soc_max_pct',
            name='BESS Characteristics',
        ),
    )

    class Meta(ElectricalNodeDetailForm.Meta):
        model = BESSDetail
        fields = (
            'node',
            'technology',
            'energy_capacity_kwh',
            'peak_power_kw',
            'charge_rate_kw',
            'usable_soc_min_pct',
            'usable_soc_max_pct',
        )


class BuswaySectionDetailForm(ElectricalNodeDetailForm):
    node_kind = NodeKindChoices.KIND_BUSWAY_RUN

    busway_system = DynamicModelChoiceField(
        queryset=ElectricalNode.objects.filter(node_kind=NodeKindChoices.KIND_BUSWAY_RUN),
        required=True,
        selector=True,
        query_params={'node_kind': NodeKindChoices.KIND_BUSWAY_RUN},
    )

    fieldsets = (
        FieldSet('node', 'busway_system', name='Electrical Node'),
        FieldSet(
            'section_index',
            'rated_ampacity_a',
            'plug_count',
            'plug_spacing_m',
            name='Busway Section Characteristics',
        ),
    )

    class Meta(ElectricalNodeDetailForm.Meta):
        model = BuswaySectionDetail
        fields = (
            'node',
            'busway_system',
            'section_index',
            'rated_ampacity_a',
            'plug_count',
            'plug_spacing_m',
        )


class PlantSourceDocumentForm(OrganizationalModelForm):
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
        FieldSet('source_type', 'discipline', 'document_id', 'revision', 'issued_at', name='Document'),
        FieldSet('source_uri', 'checksum', 'metadata', name='Source Metadata'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PlantSourceDocument
        fields = (
            'name',
            'slug',
            'site',
            'location',
            'source_type',
            'discipline',
            'document_id',
            'revision',
            'issued_at',
            'source_uri',
            'checksum',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'source_type': forms.Select(choices=PlantSourceTypeChoices),
            'discipline': forms.Select(choices=PlantDisciplineChoices),
        }


class PlantSourceSheetForm(OrganizationalModelForm):
    source_document = DynamicModelChoiceField(
        queryset=PlantSourceDocument.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'source_document', name='Document'),
        FieldSet('sheet_number', 'title', 'scale', 'page_index', name='Sheet'),
        FieldSet('metadata', name='Source Metadata'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PlantSourceSheet
        fields = (
            'name',
            'slug',
            'source_document',
            'sheet_number',
            'title',
            'scale',
            'page_index',
            'metadata',
            'description',
            'comments',
            'tags',
        )


class PlantSourceLayerForm(OrganizationalModelForm):
    source_sheet = DynamicModelChoiceField(
        queryset=PlantSourceSheet.objects.all(),
        required=True,
        selector=True,
    )

    fieldsets = (
        FieldSet('name', 'slug', 'source_sheet', name='Sheet'),
        FieldSet('layer_name', 'layer_kind', 'discipline', 'is_visible', name='Layer'),
        FieldSet('metadata', name='Source Metadata'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PlantSourceLayer
        fields = (
            'name',
            'slug',
            'source_sheet',
            'layer_name',
            'layer_kind',
            'discipline',
            'is_visible',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'layer_kind': forms.Select(choices=PlantSourceLayerKindChoices),
            'discipline': forms.Select(choices=PlantDisciplineChoices),
        }


class PlantProvenanceForm(OrganizationalModelForm):
    assigned_object_type = forms.ModelChoiceField(
        queryset=ContentType.objects.all(),
        required=True,
    )
    assigned_object_id = forms.IntegerField(
        required=True,
        min_value=1,
        label='Assigned object ID',
    )
    source_document = DynamicModelChoiceField(
        queryset=PlantSourceDocument.objects.all(),
        required=False,
        selector=True,
    )
    source_sheet = DynamicModelChoiceField(
        queryset=PlantSourceSheet.objects.all(),
        required=False,
        query_params={'source_document_id': '$source_document'},
    )
    source_layer = DynamicModelChoiceField(
        queryset=PlantSourceLayer.objects.all(),
        required=False,
        query_params={'source_sheet_id': '$source_sheet'},
    )

    fieldsets = (
        FieldSet('name', 'slug', name='Record'),
        FieldSet('assigned_object_type', 'assigned_object_id', name='Assigned Object'),
        FieldSet('source_document', 'source_sheet', 'source_layer', 'source_ref', name='Source'),
        FieldSet('extraction_method', 'confidence', 'is_authoritative', 'extracted_at', name='Extraction'),
        FieldSet('metadata', 'description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PlantProvenance
        fields = (
            'name',
            'slug',
            'assigned_object_type',
            'assigned_object_id',
            'source_document',
            'source_sheet',
            'source_layer',
            'extraction_method',
            'source_ref',
            'confidence',
            'is_authoritative',
            'extracted_at',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'extraction_method': forms.Select(choices=PlantExtractionMethodChoices),
            'confidence': forms.Select(choices=SpatialConfidenceChoices),
        }


class PhysicalSpaceForm(OrganizationalModelForm):
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
    spatial_frame = DynamicModelChoiceField(
        queryset=SpatialFrame.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )
    parent_space = DynamicModelChoiceField(
        queryset=PhysicalSpace.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'site', 'location', name='Scope'),
        FieldSet('space_kind', 'floor_label', 'parent_space', 'spatial_frame', name='Space'),
        FieldSet('z_min', 'z_max', 'boundary_geometry', name='Bounds'),
        FieldSet('source_document', 'source_ref', 'confidence', 'metadata', name='Source'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PhysicalSpace
        fields = (
            'name',
            'slug',
            'site',
            'location',
            'spatial_frame',
            'parent_space',
            'space_kind',
            'floor_label',
            'z_min',
            'z_max',
            'boundary_geometry',
            'source_document',
            'source_ref',
            'confidence',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'space_kind': forms.Select(choices=PhysicalSpaceKindChoices),
            'confidence': forms.Select(choices=SpatialConfidenceChoices),
        }


class PhysicalElementTypeForm(OrganizationalModelForm):
    fieldsets = (
        FieldSet('name', 'slug', 'discipline', 'element_kind', name='Classification'),
        FieldSet('default_width', 'default_depth', 'default_height', 'default_color', name='Defaults'),
        FieldSet('symbol_key', 'is_pathway', 'is_supporting_structure', name='Behavior'),
        FieldSet('metadata', 'description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PhysicalElementType
        fields = (
            'name',
            'slug',
            'discipline',
            'element_kind',
            'default_width',
            'default_depth',
            'default_height',
            'default_color',
            'symbol_key',
            'is_pathway',
            'is_supporting_structure',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'discipline': forms.Select(choices=PlantDisciplineChoices),
            'element_kind': forms.Select(choices=PhysicalElementKindChoices),
        }


class PhysicalElementForm(OrganizationalModelForm):
    element_type = DynamicModelChoiceField(
        queryset=PhysicalElementType.objects.all(),
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
    physical_space = DynamicModelChoiceField(
        queryset=PhysicalSpace.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'element_type', 'site', 'location', 'physical_space', name='Scope'),
        FieldSet('label', 'role', 'manufacturer', 'model_name', 'asset_tag', name='Identity'),
        FieldSet('install_state', 'design_state', 'source_label', 'confidence', name='State'),
        FieldSet('metadata', 'description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PhysicalElement
        fields = (
            'name',
            'slug',
            'element_type',
            'site',
            'location',
            'physical_space',
            'label',
            'role',
            'manufacturer',
            'model_name',
            'asset_tag',
            'install_state',
            'design_state',
            'source_label',
            'confidence',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'install_state': forms.Select(choices=TopologyStateChoices),
            'design_state': forms.Select(choices=DesignStateChoices),
            'confidence': forms.Select(choices=SpatialConfidenceChoices),
        }


class PhysicalObjectBindingForm(OrganizationalModelForm):
    physical_element = DynamicModelChoiceField(
        queryset=PhysicalElement.objects.all(),
        required=False,
        selector=True,
    )
    spatial_placement = DynamicModelChoiceField(
        queryset=SpatialPlacement.objects.all(),
        required=False,
        selector=True,
    )
    assigned_object_type = forms.ModelChoiceField(
        queryset=ContentType.objects.all(),
        required=True,
    )
    assigned_object_id = forms.IntegerField(
        required=True,
        min_value=1,
        label='Assigned object ID',
    )

    fieldsets = (
        FieldSet('name', 'slug', name='Binding'),
        FieldSet('physical_element', 'spatial_placement', name='Physical Representation'),
        FieldSet('assigned_object_type', 'assigned_object_id', name='Assigned Object'),
        FieldSet('binding_role', 'confidence', 'is_primary', name='Role'),
        FieldSet('metadata', 'description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = PhysicalObjectBinding
        fields = (
            'name',
            'slug',
            'physical_element',
            'spatial_placement',
            'assigned_object_type',
            'assigned_object_id',
            'binding_role',
            'confidence',
            'is_primary',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'binding_role': forms.Select(choices=PhysicalObjectBindingRoleChoices),
            'confidence': forms.Select(choices=SpatialConfidenceChoices),
        }


class SpatialFrameForm(OrganizationalModelForm):
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
    parent_frame = DynamicModelChoiceField(
        queryset=SpatialFrame.objects.all(),
        required=False,
        query_params={'site_id': '$site'},
    )

    fieldsets = (
        FieldSet('name', 'slug', 'site', 'location', 'parent_frame', name='Frame'),
        FieldSet(
            'origin_x_in_parent',
            'origin_y_in_parent',
            'width',
            'height',
            'units',
            'axis_orientation',
            name='Coordinates',
        ),
        FieldSet('source_document', 'source_ref', 'confidence', 'metadata', name='Source'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = SpatialFrame
        fields = (
            'name',
            'slug',
            'site',
            'location',
            'parent_frame',
            'origin_x_in_parent',
            'origin_y_in_parent',
            'width',
            'height',
            'units',
            'axis_orientation',
            'source_document',
            'source_ref',
            'confidence',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'axis_orientation': forms.Select(choices=SpatialAxisOrientationChoices),
            'confidence': forms.Select(choices=SpatialConfidenceChoices),
        }


class SpatialPlacementForm(OrganizationalModelForm):
    spatial_frame = DynamicModelChoiceField(
        queryset=SpatialFrame.objects.all(),
        required=True,
        selector=True,
    )
    assigned_object_type = forms.ModelChoiceField(
        queryset=ContentType.objects.all(),
        required=True,
    )
    assigned_object_id = forms.IntegerField(
        required=True,
        min_value=1,
        label='Assigned object ID',
    )

    fieldsets = (
        FieldSet('name', 'slug', 'spatial_frame', name='Placement'),
        FieldSet('assigned_object_type', 'assigned_object_id', name='Assigned Object'),
        FieldSet('x', 'y', 'z', 'width', 'depth', 'height', 'rotation_degrees', 'anchor', name='Coordinates'),
        FieldSet('placement_kind', 'confidence', name='Classification'),
        FieldSet('source_document', 'source_ref', 'metadata', name='Source'),
        FieldSet('description', 'comments', 'tags', name='Notes'),
    )

    class Meta:
        model = SpatialPlacement
        fields = (
            'name',
            'slug',
            'spatial_frame',
            'assigned_object_type',
            'assigned_object_id',
            'x',
            'y',
            'z',
            'width',
            'depth',
            'height',
            'rotation_degrees',
            'anchor',
            'placement_kind',
            'confidence',
            'source_document',
            'source_ref',
            'metadata',
            'description',
            'comments',
            'tags',
        )
        widgets = {
            'anchor': forms.Select(choices=SpatialAnchorChoices),
            'placement_kind': forms.Select(choices=SpatialPlacementKindChoices),
            'confidence': forms.Select(choices=SpatialConfidenceChoices),
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
        FieldSet('site', 'location', 'placement_scope_type', name='Spatial Context'),
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


class PowerValidationRunFilterForm(OrganizationalModelFilterSetForm):
    model = PowerValidationRun
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', name='Scope'),
        FieldSet('run_kind', 'status', name='Run'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )


class PowerFindingFilterForm(OrganizationalModelFilterSetForm):
    model = PowerFinding
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('run_id', 'power_system_id', name='Scope'),
        FieldSet('finding_type', 'severity', 'status', name='Finding'),
        FieldSet('assigned_object_type_id', 'assigned_object_id', name='Assigned Object'),
    )
    run_id = DynamicModelMultipleChoiceField(
        queryset=PowerValidationRun.objects.all(),
        required=False,
        label='Validation run',
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    assigned_object_type_id = forms.ModelMultipleChoiceField(
        queryset=ContentType.objects.all(),
        required=False,
        label='Assigned object type',
    )
    assigned_object_id = forms.IntegerField(
        required=False,
        min_value=1,
        label='Assigned object ID',
    )


class PowerArchitectureTemplateFilterForm(OrganizationalModelFilterSetForm):
    model = PowerArchitectureTemplate
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('version', 'is_active', name='Template'),
    )


class InstantiationRunFilterForm(OrganizationalModelFilterSetForm):
    model = InstantiationRun
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'template_id', name='Scope'),
        FieldSet('status', 'dry_run', name='Run'),
    )
    power_system_id = DynamicModelMultipleChoiceField(
        queryset=PowerSystem.objects.all(),
        required=False,
        label='Power system',
    )
    template_id = DynamicModelMultipleChoiceField(
        queryset=PowerArchitectureTemplate.objects.all(),
        required=False,
        label='Template',
    )


class InstantiationArtifactFilterForm(OrganizationalModelFilterSetForm):
    model = InstantiationArtifact
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('run_id', name='Run'),
        FieldSet('artifact_type', 'action', 'status', 'template_key', name='Artifact'),
    )
    run_id = DynamicModelMultipleChoiceField(
        queryset=InstantiationRun.objects.all(),
        required=False,
        label='Instantiation run',
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


class PowerHandoffPointFilterForm(OrganizationalModelFilterSetForm):
    model = PowerHandoffPoint
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'expected_redundancy_group_id', name='Scope'),
        FieldSet('electrical_node_id', 'electrical_terminal_id', name='Electrical Boundary'),
        FieldSet('power_port_id', 'design_state', name='Target'),
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
    power_port_id = DynamicModelMultipleChoiceField(
        queryset=PowerPort.objects.all(),
        required=False,
        label='Power port',
    )


class CapacityReservationFilterForm(OrganizationalModelFilterSetForm):
    model = CapacityReservation
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'site_id', 'node_id', name='Electrical Scope'),
        FieldSet('tenant_id', 'rack_id', name='Allocation'),
        FieldSet('status', 'valid_from', 'valid_until', name='Reservation Window'),
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
    node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='Electrical node',
        query_params={'power_system_id': '$power_system_id', 'site_id': '$site_id'},
    )
    tenant_id = DynamicModelMultipleChoiceField(
        queryset=Tenant.objects.all(),
        required=False,
        label='Tenant',
    )
    rack_id = DynamicModelMultipleChoiceField(
        queryset=Rack.objects.all(),
        required=False,
        label='Rack',
        query_params={'site_id': '$site_id'},
    )


class ElectricalNodeDetailFilterForm(NetBoxModelFilterSetForm):
    model = None
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'site_id', 'node_id', name='Electrical Scope'),
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
    node_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.all(),
        required=False,
        label='Electrical node',
        query_params={'power_system_id': '$power_system_id', 'site_id': '$site_id'},
    )


class UPSDetailFilterForm(ElectricalNodeDetailFilterForm):
    model = UPSDetail
    fieldsets = ElectricalNodeDetailFilterForm.fieldsets + (
        FieldSet('ups_topology', 'parallel_group_id', 'maintenance_bypass_present', name='UPS'),
    )


class GeneratorDetailFilterForm(ElectricalNodeDetailFilterForm):
    model = GeneratorDetail
    fieldsets = ElectricalNodeDetailFilterForm.fieldsets + (
        FieldSet('fuel_type', 'cooling_type', 'ats_group_id', name='Generator'),
    )


class TransformerDetailFilterForm(ElectricalNodeDetailFilterForm):
    model = TransformerDetail
    fieldsets = ElectricalNodeDetailFilterForm.fieldsets + (
        FieldSet('vector_group', 'cooling_type', name='Transformer'),
    )


class BESSDetailFilterForm(ElectricalNodeDetailFilterForm):
    model = BESSDetail
    fieldsets = ElectricalNodeDetailFilterForm.fieldsets + (
        FieldSet('technology', name='BESS'),
    )


class BuswaySectionDetailFilterForm(ElectricalNodeDetailFilterForm):
    model = BuswaySectionDetail
    fieldsets = ElectricalNodeDetailFilterForm.fieldsets + (
        FieldSet('busway_system_id', 'section_index', name='Busway Section'),
    )
    busway_system_id = DynamicModelMultipleChoiceField(
        queryset=ElectricalNode.objects.filter(node_kind=NodeKindChoices.KIND_BUSWAY_RUN),
        required=False,
        label='Busway system',
        query_params={'node_kind': NodeKindChoices.KIND_BUSWAY_RUN},
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


class PlantSourceDocumentFilterForm(OrganizationalModelFilterSetForm):
    model = PlantSourceDocument
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('site_id', 'location_id', name='Scope'),
        FieldSet('source_type', 'discipline', 'document_id', 'revision', name='Document'),
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


class PlantSourceSheetFilterForm(OrganizationalModelFilterSetForm):
    model = PlantSourceSheet
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('source_document_id', name='Document'),
        FieldSet('sheet_number', 'title', 'scale', name='Sheet'),
    )
    source_document_id = DynamicModelMultipleChoiceField(
        queryset=PlantSourceDocument.objects.all(),
        required=False,
        label='Source document',
    )


class PlantSourceLayerFilterForm(OrganizationalModelFilterSetForm):
    model = PlantSourceLayer
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('source_document_id', 'source_sheet_id', name='Sheet'),
        FieldSet('layer_kind', 'discipline', 'is_visible', name='Layer'),
    )
    source_document_id = DynamicModelMultipleChoiceField(
        queryset=PlantSourceDocument.objects.all(),
        required=False,
        label='Source document',
    )
    source_sheet_id = DynamicModelMultipleChoiceField(
        queryset=PlantSourceSheet.objects.all(),
        required=False,
        label='Source sheet',
        query_params={'source_document_id': '$source_document_id'},
    )


class PlantProvenanceFilterForm(OrganizationalModelFilterSetForm):
    model = PlantProvenance
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('assigned_object_type_id', 'assigned_object_id', name='Assigned Object'),
        FieldSet('source_document_id', 'source_sheet_id', 'source_layer_id', name='Source'),
        FieldSet('extraction_method', 'confidence', 'is_authoritative', name='Extraction'),
    )
    assigned_object_type_id = forms.ModelMultipleChoiceField(
        queryset=ContentType.objects.all(),
        required=False,
        label='Assigned object type',
    )
    assigned_object_id = forms.IntegerField(
        required=False,
        min_value=1,
        label='Assigned object ID',
    )
    source_document_id = DynamicModelMultipleChoiceField(
        queryset=PlantSourceDocument.objects.all(),
        required=False,
        label='Source document',
    )
    source_sheet_id = DynamicModelMultipleChoiceField(
        queryset=PlantSourceSheet.objects.all(),
        required=False,
        label='Source sheet',
        query_params={'source_document_id': '$source_document_id'},
    )
    source_layer_id = DynamicModelMultipleChoiceField(
        queryset=PlantSourceLayer.objects.all(),
        required=False,
        label='Source layer',
        query_params={'source_sheet_id': '$source_sheet_id'},
    )


class PhysicalSpaceFilterForm(OrganizationalModelFilterSetForm):
    model = PhysicalSpace
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('site_id', 'location_id', 'spatial_frame_id', 'parent_space_id', name='Scope'),
        FieldSet('space_kind', 'floor_label', 'confidence', name='Space'),
        FieldSet('source_document', 'source_ref', name='Source'),
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
    spatial_frame_id = DynamicModelMultipleChoiceField(
        queryset=SpatialFrame.objects.all(),
        required=False,
        label='Spatial frame',
        query_params={'site_id': '$site_id'},
    )
    parent_space_id = DynamicModelMultipleChoiceField(
        queryset=PhysicalSpace.objects.all(),
        required=False,
        label='Parent space',
        query_params={'site_id': '$site_id'},
    )


class PhysicalElementTypeFilterForm(OrganizationalModelFilterSetForm):
    model = PhysicalElementType
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('discipline', 'element_kind', name='Classification'),
        FieldSet('symbol_key', 'is_pathway', 'is_supporting_structure', name='Behavior'),
    )


class PhysicalElementFilterForm(OrganizationalModelFilterSetForm):
    model = PhysicalElement
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('element_type_id', 'site_id', 'location_id', 'physical_space_id', name='Scope'),
        FieldSet('role', 'manufacturer', 'model_name', 'asset_tag', name='Identity'),
        FieldSet('install_state', 'design_state', 'confidence', name='State'),
    )
    element_type_id = DynamicModelMultipleChoiceField(
        queryset=PhysicalElementType.objects.all(),
        required=False,
        label='Element type',
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
    physical_space_id = DynamicModelMultipleChoiceField(
        queryset=PhysicalSpace.objects.all(),
        required=False,
        label='Physical space',
        query_params={'site_id': '$site_id'},
    )


class PhysicalObjectBindingFilterForm(OrganizationalModelFilterSetForm):
    model = PhysicalObjectBinding
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('physical_element_id', 'spatial_placement_id', name='Physical Representation'),
        FieldSet('assigned_object_type_id', 'assigned_object_id', name='Assigned Object'),
        FieldSet('binding_role', 'confidence', 'is_primary', name='Role'),
    )
    physical_element_id = DynamicModelMultipleChoiceField(
        queryset=PhysicalElement.objects.all(),
        required=False,
        label='Physical element',
    )
    spatial_placement_id = DynamicModelMultipleChoiceField(
        queryset=SpatialPlacement.objects.all(),
        required=False,
        label='Spatial placement',
    )
    assigned_object_type_id = forms.ModelMultipleChoiceField(
        queryset=ContentType.objects.all(),
        required=False,
        label='Assigned object type',
    )
    assigned_object_id = forms.IntegerField(
        required=False,
        min_value=1,
        label='Assigned object ID',
    )


class SpatialFrameFilterForm(OrganizationalModelFilterSetForm):
    model = SpatialFrame
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('site_id', 'location_id', 'parent_frame_id', name='Scope'),
        FieldSet('units', 'axis_orientation', 'source_document', 'source_ref', name='Coordinates'),
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
    parent_frame_id = DynamicModelMultipleChoiceField(
        queryset=SpatialFrame.objects.all(),
        required=False,
        label='Parent frame',
        query_params={'site_id': '$site_id'},
    )


class SpatialPlacementFilterForm(OrganizationalModelFilterSetForm):
    model = SpatialPlacement
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('spatial_frame_id', 'site_id', 'location_id', name='Frame'),
        FieldSet('assigned_object_type_id', 'assigned_object_id', name='Assigned Object'),
        FieldSet('anchor', 'placement_kind', 'confidence', name='Classification'),
    )
    spatial_frame_id = DynamicModelMultipleChoiceField(
        queryset=SpatialFrame.objects.all(),
        required=False,
        label='Spatial frame',
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
    assigned_object_type_id = forms.ModelMultipleChoiceField(
        queryset=ContentType.objects.all(),
        required=False,
        label='Assigned object type',
    )
    assigned_object_id = forms.IntegerField(
        required=False,
        min_value=1,
        label='Assigned object ID',
    )


class ElectricalNodePlacementFilterForm(OrganizationalModelFilterSetForm):
    model = ElectricalNodePlacement
    fieldsets = (
        FieldSet('q', 'filter_id'),
        FieldSet('power_system_id', 'electrical_node_id', name='Scope'),
        FieldSet('site_id', 'location_id', 'placement_scope_type', name='Spatial Context'),
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
