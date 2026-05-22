from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from dcim.models import Location, PowerPort, Rack, Site
from netbox.models import OrganizationalModel
from tenancy.models import Tenant
from utilities.fields import ColorField

from .choices import (
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
from .services.validation import validate_topology_segment, validate_topology_terminal


class PowerPlantURLMixin:
	def get_absolute_url(self):
		return reverse(
			f'plugins:netbox_power_plant:{self._meta.model_name}',
			args=[self.pk],
		)


class PowerSystem(PowerPlantURLMixin, OrganizationalModel):
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_systems',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_systems',
		blank=True,
		null=True,
	)
	scope_type = models.CharField(
		max_length=32,
		choices=PowerSystemScopeChoices,
		default=PowerSystemScopeChoices.SCOPE_HALL,
	)
	upstream_supply_type = models.CharField(
		max_length=16,
		choices=SupplyTypeChoices,
		default=SupplyTypeChoices.SUPPLY_AC,
	)
	nominal_distribution_voltage = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
		help_text=_('Nominal voltage used for the system distribution, expressed in volts.'),
	)
	frequency_hz = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		blank=True,
		null=True,
		help_text=_('Nominal system frequency in hertz.'),
	)
	is_template_derived = models.BooleanField(
		default=False,
	)
	design_state = models.CharField(
		max_length=32,
		choices=DesignStateChoices,
		default=DesignStateChoices.STATE_PLANNED,
	)

	class Meta:
		ordering = ('site__name', 'name')
		verbose_name = 'power system'
		verbose_name_plural = 'power systems'

	def clean(self):
		super().clean()

		if self.location_id and self.location.site_id != self.site_id:
			raise ValidationError({
				'location': _('The selected location must belong to the selected site.'),
			})


class PowerArchitectureTemplate(PowerPlantURLMixin, OrganizationalModel):
	version = models.CharField(
		max_length=32,
		default='1',
	)
	is_active = models.BooleanField(
		default=True,
	)
	default_context = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('name', 'version')
		verbose_name = 'power architecture template'
		verbose_name_plural = 'power architecture templates'


class TemplateNode(PowerPlantURLMixin, OrganizationalModel):
	template = models.ForeignKey(
		to=PowerArchitectureTemplate,
		on_delete=models.CASCADE,
		related_name='nodes',
	)
	key = models.SlugField(
		max_length=64,
		help_text=_('Stable template-local key used for idempotent instantiation.'),
	)
	name_format = models.CharField(
		max_length=120,
		blank=True,
		help_text=_('Optional Python format string. Context includes power_system, template, site, and location values.'),
	)
	slug_format = models.CharField(
		max_length=120,
		blank=True,
	)
	parent_key = models.SlugField(
		max_length=64,
		blank=True,
		help_text=_('Optional TemplateNode key to assign as the stamped parent node.'),
	)
	node_kind = models.CharField(
		max_length=64,
		choices=NodeKindChoices,
		default=NodeKindChoices.KIND_CUSTOM,
	)
	equipment_role = models.CharField(
		max_length=100,
		blank=True,
	)
	phase_mode = models.CharField(
		max_length=16,
		choices=PhaseModeChoices,
		default=PhaseModeChoices.MODE_THREE_PHASE,
	)
	topology_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	install_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	attributes = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('template__name', 'key')
		constraints = (
			models.UniqueConstraint(
				fields=('template', 'key'),
				name='netbox_power_plant_templatenode_template_key',
			),
		)
		verbose_name = 'template node'
		verbose_name_plural = 'template nodes'

	def clean(self):
		super().clean()
		if self.parent_key and self.parent_key == self.key:
			raise ValidationError({
				'parent_key': _('A template node cannot be its own parent.'),
			})


class TemplateTerminal(PowerPlantURLMixin, OrganizationalModel):
	template_node = models.ForeignKey(
		to=TemplateNode,
		on_delete=models.CASCADE,
		related_name='terminals',
	)
	key = models.SlugField(
		max_length=64,
		help_text=_('Stable node-local key used for idempotent instantiation.'),
	)
	name_format = models.CharField(
		max_length=120,
		blank=True,
	)
	slug_format = models.CharField(
		max_length=120,
		blank=True,
	)
	terminal_role = models.CharField(
		max_length=32,
		choices=TerminalRoleChoices,
		default=TerminalRoleChoices.ROLE_CUSTOM,
	)
	direction = models.CharField(
		max_length=16,
		choices=TerminalDirectionChoices,
		default=TerminalDirectionChoices.DIRECTION_BIDIRECTIONAL,
	)
	supply_type = models.CharField(
		max_length=16,
		choices=SupplyTypeChoices,
		default=SupplyTypeChoices.SUPPLY_AC,
	)
	position_index = models.PositiveSmallIntegerField(
		blank=True,
		null=True,
	)
	attributes = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('template_node__template__name', 'template_node__key', 'position_index', 'key')
		constraints = (
			models.UniqueConstraint(
				fields=('template_node', 'key'),
				name='netbox_power_plant_tterminal_node_key',
			),
		)
		verbose_name = 'template terminal'
		verbose_name_plural = 'template terminals'


class TemplateSegment(PowerPlantURLMixin, OrganizationalModel):
	template = models.ForeignKey(
		to=PowerArchitectureTemplate,
		on_delete=models.CASCADE,
		related_name='segments',
	)
	key = models.SlugField(
		max_length=64,
		help_text=_('Stable template-local key used for idempotent instantiation.'),
	)
	name_format = models.CharField(
		max_length=120,
		blank=True,
	)
	slug_format = models.CharField(
		max_length=120,
		blank=True,
	)
	from_node_key = models.SlugField(max_length=64)
	from_terminal_key = models.SlugField(max_length=64)
	to_node_key = models.SlugField(max_length=64)
	to_terminal_key = models.SlugField(max_length=64)
	segment_kind = models.CharField(
		max_length=32,
		choices=SegmentKindChoices,
		default=SegmentKindChoices.KIND_FEEDER,
	)
	path_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	attributes = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('template__name', 'key')
		constraints = (
			models.UniqueConstraint(
				fields=('template', 'key'),
				name='netbox_power_plant_tsegment_template_key',
			),
		)
		verbose_name = 'template segment'
		verbose_name_plural = 'template segments'


class TemplatePlacementRule(PowerPlantURLMixin, OrganizationalModel):
	template_node = models.OneToOneField(
		to=TemplateNode,
		on_delete=models.CASCADE,
		related_name='placement_rule',
	)
	placement_scope_type = models.CharField(
		max_length=16,
		choices=PlacementScopeChoices,
		default=PlacementScopeChoices.SCOPE_LOCATION,
	)
	x = models.DecimalField(max_digits=10, decimal_places=2)
	y = models.DecimalField(max_digits=10, decimal_places=2)
	width = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
	height = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
	rotation_degrees = models.DecimalField(max_digits=7, decimal_places=2, default=0)
	symbol_kind = models.CharField(
		max_length=32,
		choices=PlacementSymbolKindChoices,
		default=PlacementSymbolKindChoices.KIND_EQUIPMENT,
	)
	label_mode = models.CharField(
		max_length=32,
		choices=PlacementLabelModeChoices,
		default=PlacementLabelModeChoices.MODE_NAME,
	)
	color = ColorField(blank=True)
	z_index = models.PositiveIntegerField(default=100)

	class Meta:
		ordering = ('template_node__template__name', 'template_node__key')
		verbose_name = 'template placement rule'
		verbose_name_plural = 'template placement rules'


class InstantiationRun(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='template_instantiation_runs',
	)
	template = models.ForeignKey(
		to=PowerArchitectureTemplate,
		on_delete=models.PROTECT,
		related_name='instantiation_runs',
	)
	status = models.CharField(
		max_length=32,
		default='pending',
	)
	dry_run = models.BooleanField(
		default=True,
	)
	context = models.JSONField(
		default=dict,
		blank=True,
	)
	artifact_count = models.PositiveIntegerField(
		default=0,
	)

	class Meta:
		ordering = ('-created', 'name')
		verbose_name = 'instantiation run'
		verbose_name_plural = 'instantiation runs'


class InstantiationArtifact(PowerPlantURLMixin, OrganizationalModel):
	run = models.ForeignKey(
		to=InstantiationRun,
		on_delete=models.CASCADE,
		related_name='artifacts',
	)
	artifact_type = models.CharField(
		max_length=32,
	)
	action = models.CharField(
		max_length=16,
	)
	status = models.CharField(
		max_length=32,
		default='proposed',
	)
	template_key = models.CharField(
		max_length=160,
	)
	stable_slug = models.SlugField(
		max_length=100,
	)
	object_type = models.ForeignKey(
		to=ContentType,
		on_delete=models.PROTECT,
		related_name='power_plant_instantiation_artifacts',
		blank=True,
		null=True,
	)
	object_id = models.PositiveBigIntegerField(
		blank=True,
		null=True,
	)
	object = GenericForeignKey(
		ct_field='object_type',
		fk_field='object_id',
	)
	proposed_data = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('run', 'artifact_type', 'template_key')
		indexes = (
			models.Index(
				fields=('object_type', 'object_id'),
				name='nbpp_inst_art_obj',
			),
		)
		verbose_name = 'instantiation artifact'
		verbose_name_plural = 'instantiation artifacts'


class PowerValidationRun(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='validation_runs',
	)
	run_kind = models.CharField(
		max_length=32,
		choices=PowerValidationRunKindChoices,
		default=PowerValidationRunKindChoices.KIND_TOPOLOGY,
	)
	status = models.CharField(
		max_length=32,
		choices=PowerValidationRunStatusChoices,
		default=PowerValidationRunStatusChoices.STATUS_PENDING,
	)
	started_at = models.DateTimeField(
		blank=True,
		null=True,
	)
	completed_at = models.DateTimeField(
		blank=True,
		null=True,
	)
	finding_count = models.PositiveIntegerField(
		default=0,
	)

	class Meta:
		ordering = ('-started_at', '-created')
		verbose_name = 'power validation run'
		verbose_name_plural = 'power validation runs'

	def __str__(self):
		return self.name


class PowerFinding(PowerPlantURLMixin, OrganizationalModel):
	run = models.ForeignKey(
		to=PowerValidationRun,
		on_delete=models.CASCADE,
		related_name='findings',
	)
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='power_findings',
	)
	fingerprint = models.CharField(
		max_length=64,
		help_text=_('Stable hash for matching the same finding across repeated persistence passes.'),
	)
	finding_type = models.CharField(
		max_length=100,
	)
	severity = models.CharField(
		max_length=32,
		choices=PowerFindingSeverityChoices,
		default=PowerFindingSeverityChoices.SEVERITY_WARNING,
	)
	status = models.CharField(
		max_length=32,
		choices=PowerFindingStatusChoices,
		default=PowerFindingStatusChoices.STATUS_OPEN,
	)
	message = models.TextField()
	assigned_object_type = models.ForeignKey(
		to=ContentType,
		on_delete=models.PROTECT,
		related_name='power_plant_findings',
		blank=True,
		null=True,
	)
	assigned_object_id = models.PositiveBigIntegerField(
		blank=True,
		null=True,
	)
	assigned_object = GenericForeignKey(
		ct_field='assigned_object_type',
		fk_field='assigned_object_id',
	)
	assigned_to = models.ForeignKey(
		to=settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name='power_plant_findings',
		blank=True,
		null=True,
	)
	suppressed_until = models.DateTimeField(
		blank=True,
		null=True,
	)
	resolved_at = models.DateTimeField(
		blank=True,
		null=True,
	)
	first_seen = models.DateTimeField(
		blank=True,
		null=True,
	)
	last_seen = models.DateTimeField(
		blank=True,
		null=True,
	)
	details = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('status', '-severity', 'finding_type', 'name')
		constraints = (
			models.UniqueConstraint(
				fields=('run', 'fingerprint'),
				name='netbox_power_plant_finding_run_fingerprint',
			),
		)
		indexes = (
			models.Index(
				fields=('assigned_object_type', 'assigned_object_id'),
				name='nbpp_finding_obj',
			),
			models.Index(
				fields=('power_system', 'status', 'severity'),
				name='nbpp_finding_state',
			),
		)
		verbose_name = 'power finding'
		verbose_name_plural = 'power findings'

	def __str__(self):
		return self.name

	def clean(self):
		super().clean()
		errors = {}

		if self.run_id and self.power_system_id and self.run.power_system_id != self.power_system_id:
			errors['power_system'] = _('The finding power system must match the validation run power system.')

		if bool(self.assigned_object_type_id) != bool(self.assigned_object_id):
			errors['assigned_object_id'] = _('Select both an assigned object type and object ID, or leave both blank.')
		elif self.assigned_object_type_id and self.assigned_object is None:
			errors['assigned_object_id'] = _('The assigned object could not be found.')

		if errors:
			raise ValidationError(errors)

	def save(self, *args, **kwargs):
		if self.run_id and not self.power_system_id:
			self.power_system_id = self.run.power_system_id
		super().save(*args, **kwargs)


class PowerDomain(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='power_domains',
	)
	code = models.CharField(
		max_length=32,
		help_text=_('Short operator-facing identifier such as A, B, UPS-B, or Busway-West.'),
	)
	kind = models.CharField(
		max_length=32,
		choices=PowerDomainKindChoices,
		default=PowerDomainKindChoices.KIND_PRIMARY,
	)
	color = ColorField(
		blank=True,
		help_text=_('Optional color used to highlight the domain in UI views.'),
	)
	priority = models.PositiveSmallIntegerField(
		default=100,
		help_text=_('Lower values indicate higher priority when ordering domains.'),
	)
	failure_isolation_depth = models.PositiveSmallIntegerField(
		default=0,
		help_text=_('How far upstream this domain remains isolated for redundancy checks.'),
	)

	class Meta:
		ordering = ('power_system__name', 'priority', 'code', 'name')
		constraints = (
			models.UniqueConstraint(
				fields=('power_system', 'code'),
				name='netbox_power_plant_powerdomain_power_system_code',
			),
		)
		verbose_name = 'power domain'
		verbose_name_plural = 'power domains'


class RedundancyGroup(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='redundancy_groups',
	)
	power_domains = models.ManyToManyField(
		to=PowerDomain,
		related_name='redundancy_groups',
		blank=True,
		help_text=_('Domains participating in this redundancy contract.'),
	)
	topology_type = models.CharField(
		max_length=32,
		choices=RedundancyTopologyChoices,
		default=RedundancyTopologyChoices.TOPOLOGY_NONE,
	)
	min_distinct_paths = models.PositiveSmallIntegerField(
		default=1,
	)
	requires_domain_isolation = models.BooleanField(
		default=False,
	)
	notes_on_failover = models.TextField(
		blank=True,
	)

	class Meta:
		ordering = ('power_system__name', 'name')
		verbose_name = 'redundancy group'
		verbose_name_plural = 'redundancy groups'


class ElectricalNode(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='electrical_nodes',
	)
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_electrical_nodes',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_electrical_nodes',
		blank=True,
		null=True,
	)
	parent_node = models.ForeignKey(
		to='self',
		on_delete=models.PROTECT,
		related_name='child_nodes',
		blank=True,
		null=True,
	)
	node_kind = models.CharField(
		max_length=64,
		choices=NodeKindChoices,
		default=NodeKindChoices.KIND_CUSTOM,
	)
	equipment_role = models.CharField(
		max_length=100,
		blank=True,
	)
	manufacturer = models.CharField(
		max_length=100,
		blank=True,
	)
	model = models.CharField(
		max_length=100,
		blank=True,
	)
	serial = models.CharField(
		max_length=100,
		blank=True,
	)
	asset_tag = models.CharField(
		max_length=100,
		blank=True,
	)
	install_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	topology_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	rated_input_voltage_min = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	rated_input_voltage_max = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	rated_output_voltage_min = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	rated_output_voltage_max = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	frequency_hz = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		blank=True,
		null=True,
	)
	phase_mode = models.CharField(
		max_length=16,
		choices=PhaseModeChoices,
		default=PhaseModeChoices.MODE_THREE_PHASE,
	)
	pole_count = models.PositiveSmallIntegerField(
		blank=True,
		null=True,
	)
	installed_capacity_kw = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		blank=True,
		null=True,
	)
	usable_capacity_kw = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		blank=True,
		null=True,
	)
	derating_factor = models.DecimalField(
		max_digits=6,
		decimal_places=4,
		blank=True,
		null=True,
	)
	reserve_margin_pct = models.DecimalField(
		max_digits=5,
		decimal_places=2,
		blank=True,
		null=True,
	)
	telemetry_source_ref = models.CharField(
		max_length=200,
		blank=True,
	)

	class Meta:
		ordering = ('power_system__name', 'site__name', 'name')
		verbose_name = 'electrical node'
		verbose_name_plural = 'electrical nodes'

	def clean(self):
		super().clean()

		if self.site_id != self.power_system.site_id:
			raise ValidationError({
				'site': _('The selected site must match the parent power system site.'),
			})

		if self.location_id and self.location.site_id != self.site_id:
			raise ValidationError({
				'location': _('The selected location must belong to the selected site.'),
			})

		if self.parent_node_id and self.parent_node.power_system_id != self.power_system_id:
			raise ValidationError({
				'parent_node': _('Parent nodes must belong to the same power system.'),
			})

		if (
			self.installed_capacity_kw is not None
			and self.usable_capacity_kw is not None
			and self.usable_capacity_kw > self.installed_capacity_kw
		):
			raise ValidationError({
				'usable_capacity_kw': _('Usable capacity cannot exceed installed capacity.'),
			})


class CapacityReservation(PowerPlantURLMixin, OrganizationalModel):
	node = models.ForeignKey(
		to=ElectricalNode,
		on_delete=models.CASCADE,
		related_name='capacity_reservations',
	)
	reserved_kw = models.DecimalField(
		max_digits=10,
		decimal_places=2,
	)
	tenant = models.ForeignKey(
		to=Tenant,
		on_delete=models.PROTECT,
		related_name='power_plant_capacity_reservations',
	)
	rack = models.ForeignKey(
		to=Rack,
		on_delete=models.PROTECT,
		related_name='power_plant_capacity_reservations',
		blank=True,
		null=True,
	)
	status = models.CharField(
		max_length=32,
		choices=CapacityReservationStatusChoices,
		default=CapacityReservationStatusChoices.STATUS_PLANNED,
	)
	valid_from = models.DateField(
		blank=True,
		null=True,
	)
	valid_until = models.DateField(
		blank=True,
		null=True,
	)
	notes = models.TextField(
		blank=True,
	)

	class Meta:
		ordering = ('node__power_system__name', 'node__name', 'status', 'valid_from', 'name')
		indexes = (
			models.Index(
				fields=('node', 'status', 'valid_from', 'valid_until'),
				name='nbpp_capres_node_status',
			),
			models.Index(
				fields=('tenant', 'status'),
				name='nbpp_capres_tenant_status',
			),
			models.Index(
				fields=('rack', 'status'),
				name='nbpp_capres_rack_status',
			),
		)
		constraints = (
			models.CheckConstraint(
				condition=models.Q(reserved_kw__gt=0),
				name='netbox_power_plant_capacityreservation_reserved_kw_positive',
			),
		)
		verbose_name = 'capacity reservation'
		verbose_name_plural = 'capacity reservations'

	def clean(self):
		super().clean()
		errors = {}

		if self.reserved_kw is not None and self.reserved_kw <= 0:
			errors['reserved_kw'] = _('Reserved capacity must be greater than zero.')

		if self.rack_id and self.node_id and self.rack.site_id != self.node.site_id:
			errors['rack'] = _('The selected rack must belong to the same site as the electrical node.')

		if self.rack_id and self.node_id and self.node.power_system_id:
			if self.rack.site_id != self.node.power_system.site_id:
				errors['rack'] = _('The selected rack must belong to the same site as the power system.')

		if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
			errors['valid_until'] = _('Valid until cannot be earlier than valid from.')

		if errors:
			raise ValidationError(errors)


class ElectricalNodeDetailModel(PowerPlantURLMixin, models.Model):
	node = models.OneToOneField(
		to=ElectricalNode,
		on_delete=models.CASCADE,
		related_name='%(class)s',
	)

	class Meta:
		abstract = True

	def _validate_node_kind(self, errors, allowed_kinds, label):
		if self.node_id and self.node.node_kind not in allowed_kinds:
			errors['node'] = _('This detail record can only be attached to %(label)s nodes.') % {
				'label': label,
			}

	def _validate_pct(self, errors, field_name):
		value = getattr(self, field_name)
		if value is not None and (value < 0 or value > 100):
			errors[field_name] = _('Percentage values must be between 0 and 100.')

	def __str__(self):
		return str(self.node)


class UPSDetail(ElectricalNodeDetailModel):
	ups_topology = models.CharField(max_length=100, blank=True)
	battery_autonomy_minutes = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
	module_count = models.PositiveSmallIntegerField(blank=True, null=True)
	module_rating_kw = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
	parallel_group_id = models.CharField(max_length=100, blank=True)
	maintenance_bypass_present = models.BooleanField(default=False)

	class Meta:
		ordering = ('node__power_system__name', 'node__name')
		verbose_name = 'UPS detail'
		verbose_name_plural = 'UPS details'

	def clean(self):
		super().clean()
		errors = {}
		self._validate_node_kind(errors, {NodeKindChoices.KIND_UPS}, _('UPS'))
		if errors:
			raise ValidationError(errors)


class GeneratorDetail(ElectricalNodeDetailModel):
	fuel_type = models.CharField(max_length=100, blank=True)
	runtime_at_full_load_hours = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
	cooling_type = models.CharField(max_length=100, blank=True)
	ats_group_id = models.CharField(max_length=100, blank=True)
	automatic_transfer_time_ms = models.PositiveIntegerField(blank=True, null=True)

	class Meta:
		ordering = ('node__power_system__name', 'node__name')
		verbose_name = 'generator detail'
		verbose_name_plural = 'generator details'

	def clean(self):
		super().clean()
		errors = {}
		self._validate_node_kind(errors, {NodeKindChoices.KIND_GENERATOR}, _('generator'))
		if errors:
			raise ValidationError(errors)


class TransformerDetail(ElectricalNodeDetailModel):
	primary_kv = models.DecimalField(max_digits=8, decimal_places=3, blank=True, null=True)
	secondary_kv = models.DecimalField(max_digits=8, decimal_places=3, blank=True, null=True)
	kva_rating = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
	vector_group = models.CharField(max_length=100, blank=True)
	impedance_pct = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
	cooling_type = models.CharField(max_length=100, blank=True)

	class Meta:
		ordering = ('node__power_system__name', 'node__name')
		verbose_name = 'transformer detail'
		verbose_name_plural = 'transformer details'

	def clean(self):
		super().clean()
		errors = {}
		self._validate_node_kind(errors, {NodeKindChoices.KIND_TRANSFORMER}, _('transformer'))
		self._validate_pct(errors, 'impedance_pct')
		if errors:
			raise ValidationError(errors)


class BESSDetail(ElectricalNodeDetailModel):
	technology = models.CharField(max_length=100, blank=True)
	energy_capacity_kwh = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
	peak_power_kw = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
	charge_rate_kw = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
	usable_soc_min_pct = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
	usable_soc_max_pct = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

	class Meta:
		ordering = ('node__power_system__name', 'node__name')
		verbose_name = 'BESS detail'
		verbose_name_plural = 'BESS details'

	def clean(self):
		super().clean()
		errors = {}
		self._validate_node_kind(errors, {NodeKindChoices.KIND_BESS}, _('BESS'))
		self._validate_pct(errors, 'usable_soc_min_pct')
		self._validate_pct(errors, 'usable_soc_max_pct')
		if (
			self.usable_soc_min_pct is not None
			and self.usable_soc_max_pct is not None
			and self.usable_soc_max_pct < self.usable_soc_min_pct
		):
			errors['usable_soc_max_pct'] = _('Maximum usable state of charge cannot be lower than the minimum.')
		if errors:
			raise ValidationError(errors)


class BuswaySectionDetail(ElectricalNodeDetailModel):
	busway_system = models.ForeignKey(
		to=ElectricalNode,
		on_delete=models.PROTECT,
		related_name='busway_sections',
	)
	section_index = models.PositiveSmallIntegerField(blank=True, null=True)
	rated_ampacity_a = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
	plug_count = models.PositiveSmallIntegerField(blank=True, null=True)
	plug_spacing_m = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)

	class Meta:
		ordering = ('busway_system__name', 'section_index', 'node__name')
		verbose_name = 'busway section detail'
		verbose_name_plural = 'busway section details'

	def clean(self):
		super().clean()
		errors = {}
		self._validate_node_kind(errors, {NodeKindChoices.KIND_BUSWAY_RUN}, _('busway run'))
		if self.busway_system_id:
			if self.busway_system.node_kind != NodeKindChoices.KIND_BUSWAY_RUN:
				errors['busway_system'] = _('The busway system must be a busway run node.')
			if self.node_id and self.busway_system.power_system_id != self.node.power_system_id:
				errors['busway_system'] = _('The busway system must belong to the same power system as the section node.')
		if errors:
			raise ValidationError(errors)


class ElectricalTerminal(PowerPlantURLMixin, OrganizationalModel):
	node = models.ForeignKey(
		to=ElectricalNode,
		on_delete=models.CASCADE,
		related_name='terminals',
	)
	terminal_role = models.CharField(
		max_length=32,
		choices=TerminalRoleChoices,
		default=TerminalRoleChoices.ROLE_CUSTOM,
	)
	direction = models.CharField(
		max_length=16,
		choices=TerminalDirectionChoices,
		default=TerminalDirectionChoices.DIRECTION_BIDIRECTIONAL,
	)
	supply_type = models.CharField(
		max_length=16,
		choices=SupplyTypeChoices,
		default=SupplyTypeChoices.SUPPLY_AC,
	)
	voltage_nominal = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	amperage_rating = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	phase_designation = models.CharField(
		max_length=32,
		blank=True,
	)
	pole_designation = models.CharField(
		max_length=32,
		blank=True,
	)
	connector_type = models.CharField(
		max_length=64,
		blank=True,
	)
	is_protected = models.BooleanField(
		default=False,
	)
	is_switchable = models.BooleanField(
		default=False,
	)
	is_monitored = models.BooleanField(
		default=False,
	)
	position_index = models.PositiveSmallIntegerField(
		blank=True,
		null=True,
	)

	class Meta:
		ordering = ('node__name', 'position_index', 'name')
		constraints = (
			models.UniqueConstraint(
				fields=('node', 'name'),
				name='netbox_power_plant_terminal_node_name',
			),
		)
		verbose_name = 'electrical terminal'
		verbose_name_plural = 'electrical terminals'

	def clean(self):
		super().clean()
		validate_topology_terminal(self)


class ElectricalSegment(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='electrical_segments',
	)
	from_terminal = models.ForeignKey(
		to=ElectricalTerminal,
		on_delete=models.PROTECT,
		related_name='outbound_segments',
	)
	to_terminal = models.ForeignKey(
		to=ElectricalTerminal,
		on_delete=models.PROTECT,
		related_name='inbound_segments',
	)
	segment_kind = models.CharField(
		max_length=32,
		choices=SegmentKindChoices,
		default=SegmentKindChoices.KIND_FEEDER,
	)
	path_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	length_m = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		blank=True,
		null=True,
	)
	conductor_material = models.CharField(
		max_length=32,
		blank=True,
	)
	conductor_count = models.PositiveSmallIntegerField(
		blank=True,
		null=True,
	)
	awg_or_mm2 = models.CharField(
		max_length=32,
		blank=True,
	)
	insulation_type = models.CharField(
		max_length=32,
		blank=True,
	)
	breaker_size_a = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	voltage_nominal = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	ampacity_a = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	derated_ampacity_a = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
	)
	power_domain = models.ForeignKey(
		to=PowerDomain,
		on_delete=models.PROTECT,
		related_name='electrical_segments',
		blank=True,
		null=True,
	)

	class Meta:
		ordering = ('power_system__name', 'from_terminal__node__name', 'name')
		constraints = (
			models.UniqueConstraint(
				fields=('from_terminal', 'to_terminal'),
				condition=models.Q(path_state=TopologyStateChoices.STATE_ACTIVE),
				name='netbox_power_plant_active_segment_terminal_pair',
			),
		)
		verbose_name = 'electrical segment'
		verbose_name_plural = 'electrical segments'

	def clean(self):
		super().clean()
		validate_topology_segment(self)


class PowerHandoffPoint(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='power_handoff_points',
	)
	electrical_node = models.ForeignKey(
		to=ElectricalNode,
		on_delete=models.PROTECT,
		related_name='power_handoff_points',
		blank=True,
		null=True,
	)
	electrical_terminal = models.ForeignKey(
		to=ElectricalTerminal,
		on_delete=models.PROTECT,
		related_name='power_handoff_points',
		blank=True,
		null=True,
	)
	power_port = models.ForeignKey(
		to=PowerPort,
		on_delete=models.PROTECT,
		related_name='power_plant_power_handoff_points',
	)
	expected_redundancy_group = models.ForeignKey(
		to=RedundancyGroup,
		on_delete=models.PROTECT,
		related_name='power_handoff_points',
		blank=True,
		null=True,
	)
	delivery_role = models.CharField(
		max_length=100,
		blank=True,
		help_text=_('Operator-facing role for the handoff, such as primary, redundant, or maintenance.'),
	)
	feed_label = models.CharField(
		max_length=100,
		blank=True,
		help_text=_('Short label such as A-feed, B-feed, or RPP-12-L21.'),
	)
	design_state = models.CharField(
		max_length=32,
		choices=DesignStateChoices,
		default=DesignStateChoices.STATE_PLANNED,
	)

	class Meta:
		ordering = ('power_system__name', 'name')
		verbose_name = 'power handoff point'
		verbose_name_plural = 'power handoff points'

	def clean(self):
		super().clean()
		errors = {}

		if not self.power_port_id:
			errors['power_port'] = _('Select a power port.')

		if not self.electrical_node_id and not self.electrical_terminal_id:
			errors['electrical_node'] = _('Select an electrical node or an electrical terminal.')
			errors['electrical_terminal'] = _('Select an electrical node or an electrical terminal.')

		if self.electrical_terminal_id:
			terminal_node = self.electrical_terminal.node
			if terminal_node.power_system_id != self.power_system_id:
				errors['electrical_terminal'] = _('The electrical terminal must belong to the selected power system.')
			if self.electrical_node_id and terminal_node.pk != self.electrical_node_id:
				errors['electrical_node'] = _('The electrical node must match the selected electrical terminal.')

		if self.electrical_node_id and self.electrical_node.power_system_id != self.power_system_id:
			errors['electrical_node'] = _('The electrical node must belong to the selected power system.')

		if self.expected_redundancy_group_id and self.expected_redundancy_group.power_system_id != self.power_system_id:
			errors['expected_redundancy_group'] = _('The redundancy group must belong to the selected power system.')

		if self.power_port_id:
			self._validate_site_location_scope(errors, self.power_port.device, 'power_port')

		if errors:
			raise ValidationError(errors)

	def _validate_site_location_scope(self, errors, boundary_object, field_name):
		if boundary_object.site_id != self.power_system.site_id:
			errors[field_name] = _('The selected object must belong to the same site as the power system.')
			return

		power_system_location_id = self.power_system.location_id
		if not power_system_location_id:
			return

		boundary_location_id = getattr(boundary_object, 'location_id', None)
		if boundary_location_id is None and getattr(boundary_object, 'rack_id', None):
			boundary_location_id = boundary_object.rack.location_id

		if boundary_location_id != power_system_location_id:
			errors[field_name] = _('The selected object must match the power system location when one is set.')


class ElectricalNodePlacement(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='electrical_node_placements',
	)
	electrical_node = models.ForeignKey(
		to=ElectricalNode,
		on_delete=models.PROTECT,
		related_name='placements',
	)
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_node_placements',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_node_placements',
		blank=True,
		null=True,
	)
	placement_scope_type = models.CharField(
		max_length=16,
		choices=PlacementScopeChoices,
		default=PlacementScopeChoices.SCOPE_LOCATION,
	)
	x = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		help_text=_('Horizontal coordinate in plugin-owned spatial overlay space.'),
	)
	y = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		help_text=_('Vertical coordinate in plugin-owned spatial overlay space.'),
	)
	width = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		blank=True,
		null=True,
	)
	height = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		blank=True,
		null=True,
	)
	rotation_degrees = models.DecimalField(
		max_digits=7,
		decimal_places=2,
		default=0,
	)
	symbol_kind = models.CharField(
		max_length=32,
		choices=PlacementSymbolKindChoices,
		default=PlacementSymbolKindChoices.KIND_EQUIPMENT,
	)
	label_mode = models.CharField(
		max_length=32,
		choices=PlacementLabelModeChoices,
		default=PlacementLabelModeChoices.MODE_NAME,
	)
	color = ColorField(
		blank=True,
		help_text=_('Optional color override for the rendered overlay symbol.'),
	)
	z_index = models.PositiveIntegerField(
		default=100,
		help_text=_('Higher values render above lower-priority overlays.'),
	)

	class Meta:
		ordering = ('power_system__name', 'electrical_node__name', 'name')
		constraints = (
			models.UniqueConstraint(
				fields=('power_system', 'electrical_node', 'site', 'location'),
				condition=models.Q(location__isnull=False),
				name='netbox_power_plant_nodeplacement_unique_location_scope',
			),
			models.UniqueConstraint(
				fields=('power_system', 'electrical_node', 'site'),
				condition=models.Q(location__isnull=True),
				name='netbox_power_plant_nodeplacement_unique_site_scope',
			),
		)
		verbose_name = 'electrical node placement'
		verbose_name_plural = 'electrical node placements'

	def clean(self):
		super().clean()
		errors = {}

		if self.electrical_node_id and self.electrical_node.power_system_id != self.power_system_id:
			errors['electrical_node'] = _('The electrical node must belong to the selected power system.')

		if self.site_id != self.power_system.site_id:
			errors['site'] = _('The selected site must match the parent power system site.')

		if self.location_id and self.location.site_id != self.site_id:
			errors['location'] = _('The selected location must belong to the selected site.')

		power_system_location_id = self.power_system.location_id
		if power_system_location_id:
			if self.placement_scope_type != PlacementScopeChoices.SCOPE_LOCATION:
				errors['placement_scope_type'] = _('Location-scoped power systems require location placements.')
			if self.location_id != power_system_location_id:
				errors['location'] = _('The placement location must match the power system location.')

		if self.placement_scope_type == PlacementScopeChoices.SCOPE_SITE and self.location_id:
			errors['location'] = _('Site-scoped placements cannot set a location.')

		if self.placement_scope_type == PlacementScopeChoices.SCOPE_LOCATION and not self.location_id:
			errors['location'] = _('Select a location for location-scoped placements.')

		if self._has_duplicate_scope():
			errors['electrical_node'] = _('A placement already exists for this node in the resolved spatial scope.')

		if errors:
			raise ValidationError(errors)

	def _has_duplicate_scope(self):
		if not self.power_system_id or not self.electrical_node_id or not self.site_id:
			return False

		queryset = type(self).objects.filter(
			power_system_id=self.power_system_id,
			electrical_node_id=self.electrical_node_id,
			site_id=self.site_id,
			location_id=self.location_id,
		)
		if self.pk:
			queryset = queryset.exclude(pk=self.pk)
		return queryset.exists()


class PlantSourceDocument(PowerPlantURLMixin, OrganizationalModel):
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_source_documents',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_source_documents',
		blank=True,
		null=True,
	)
	source_type = models.CharField(
		max_length=32,
		choices=PlantSourceTypeChoices,
		default=PlantSourceTypeChoices.TYPE_PDF,
	)
	discipline = models.CharField(
		max_length=32,
		choices=PlantDisciplineChoices,
		default=PlantDisciplineChoices.DISCIPLINE_MIXED,
	)
	document_id = models.CharField(
		max_length=100,
		blank=True,
		help_text=_('Drawing number, file identifier, or other source-system reference.'),
	)
	revision = models.CharField(
		max_length=32,
		blank=True,
	)
	issued_at = models.DateField(
		blank=True,
		null=True,
	)
	source_uri = models.CharField(
		max_length=500,
		blank=True,
	)
	checksum = models.CharField(
		max_length=128,
		blank=True,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('site__name', 'discipline', 'name')
		verbose_name = 'plant source document'
		verbose_name_plural = 'plant source documents'

	def clean(self):
		super().clean()
		if self.location_id and self.location.site_id != self.site_id:
			raise ValidationError({'location': _('The selected location must belong to the selected site.')})


class PlantSourceSheet(PowerPlantURLMixin, OrganizationalModel):
	source_document = models.ForeignKey(
		to=PlantSourceDocument,
		on_delete=models.CASCADE,
		related_name='sheets',
	)
	sheet_number = models.CharField(
		max_length=64,
		blank=True,
	)
	title = models.CharField(
		max_length=200,
		blank=True,
	)
	scale = models.CharField(
		max_length=64,
		blank=True,
	)
	page_index = models.PositiveIntegerField(
		blank=True,
		null=True,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('source_document__name', 'page_index', 'sheet_number', 'name')
		verbose_name = 'plant source sheet'
		verbose_name_plural = 'plant source sheets'


class PlantSourceLayer(PowerPlantURLMixin, OrganizationalModel):
	source_sheet = models.ForeignKey(
		to=PlantSourceSheet,
		on_delete=models.CASCADE,
		related_name='layers',
	)
	layer_name = models.CharField(
		max_length=120,
		blank=True,
	)
	layer_kind = models.CharField(
		max_length=32,
		choices=PlantSourceLayerKindChoices,
		default=PlantSourceLayerKindChoices.KIND_UNKNOWN,
	)
	discipline = models.CharField(
		max_length=32,
		choices=PlantDisciplineChoices,
		default=PlantDisciplineChoices.DISCIPLINE_MIXED,
	)
	is_visible = models.BooleanField(
		default=True,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('source_sheet__source_document__name', 'source_sheet__page_index', 'layer_kind', 'name')
		verbose_name = 'plant source layer'
		verbose_name_plural = 'plant source layers'


class PlantProvenance(PowerPlantURLMixin, OrganizationalModel):
	assigned_object_type = models.ForeignKey(
		to=ContentType,
		on_delete=models.PROTECT,
		related_name='power_plant_provenance_records',
	)
	assigned_object_id = models.PositiveBigIntegerField()
	assigned_object = GenericForeignKey(
		ct_field='assigned_object_type',
		fk_field='assigned_object_id',
	)
	source_document = models.ForeignKey(
		to=PlantSourceDocument,
		on_delete=models.PROTECT,
		related_name='provenance_records',
		blank=True,
		null=True,
	)
	source_sheet = models.ForeignKey(
		to=PlantSourceSheet,
		on_delete=models.PROTECT,
		related_name='provenance_records',
		blank=True,
		null=True,
	)
	source_layer = models.ForeignKey(
		to=PlantSourceLayer,
		on_delete=models.PROTECT,
		related_name='provenance_records',
		blank=True,
		null=True,
	)
	extraction_method = models.CharField(
		max_length=32,
		choices=PlantExtractionMethodChoices,
		default=PlantExtractionMethodChoices.METHOD_UNKNOWN,
	)
	source_ref = models.CharField(
		max_length=200,
		blank=True,
	)
	confidence = models.CharField(
		max_length=32,
		choices=SpatialConfidenceChoices,
		default=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
	)
	is_authoritative = models.BooleanField(
		default=False,
	)
	extracted_at = models.DateTimeField(
		blank=True,
		null=True,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('assigned_object_type', 'assigned_object_id', 'source_document__name', 'source_ref')
		indexes = (
			models.Index(
				fields=('assigned_object_type', 'assigned_object_id'),
				name='nbpp_prov_obj',
			),
		)
		verbose_name = 'plant provenance record'
		verbose_name_plural = 'plant provenance records'

	def clean(self):
		super().clean()
		errors = {}

		if not self.assigned_object_type_id or not self.assigned_object_id:
			errors['assigned_object_id'] = _('Select an assigned object.')
		elif self.assigned_object is None:
			errors['assigned_object_id'] = _('The assigned object could not be found.')

		if self.source_sheet_id and self.source_document_id:
			if self.source_sheet.source_document_id != self.source_document_id:
				errors['source_sheet'] = _('The selected sheet must belong to the selected source document.')

		if self.source_layer_id:
			if self.source_sheet_id and self.source_layer.source_sheet_id != self.source_sheet_id:
				errors['source_layer'] = _('The selected layer must belong to the selected source sheet.')
			if self.source_document_id and self.source_layer.source_sheet.source_document_id != self.source_document_id:
				errors['source_layer'] = _('The selected layer must belong to the selected source document.')

		if errors:
			raise ValidationError(errors)


class SpatialFrame(PowerPlantURLMixin, OrganizationalModel):
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_spatial_frames',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_spatial_frames',
		blank=True,
		null=True,
	)
	parent_frame = models.ForeignKey(
		to='self',
		on_delete=models.PROTECT,
		related_name='child_frames',
		blank=True,
		null=True,
	)
	origin_x_in_parent = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	origin_y_in_parent = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	width = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	height = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	units = models.CharField(
		max_length=64,
		default='mad1_svg_unit',
	)
	axis_orientation = models.CharField(
		max_length=64,
		choices=SpatialAxisOrientationChoices,
		default=SpatialAxisOrientationChoices.ORIENTATION_LOWER_LEFT_X_RIGHT_Y_UP,
	)
	source_document = models.CharField(
		max_length=200,
		blank=True,
	)
	source_ref = models.CharField(
		max_length=200,
		blank=True,
	)
	confidence = models.CharField(
		max_length=32,
		choices=SpatialConfidenceChoices,
		default=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('site__name', 'location__name', 'name')
		verbose_name = 'spatial frame'
		verbose_name_plural = 'spatial frames'

	def clean(self):
		super().clean()
		errors = {}

		if self.location_id and self.location.site_id != self.site_id:
			errors['location'] = _('The selected location must belong to the selected site.')

		if self.parent_frame_id:
			if self.parent_frame_id == self.pk:
				errors['parent_frame'] = _('A spatial frame cannot be its own parent.')
			elif self.parent_frame.site_id != self.site_id:
				errors['parent_frame'] = _('The parent frame must belong to the same site.')
			elif (
				self.location_id
				and self.parent_frame.location_id
				and self.location_id != self.parent_frame.location_id
			):
				errors['location'] = _('Child and parent frame locations must match when both are set.')

		if errors:
			raise ValidationError(errors)


class SpatialPlacement(PowerPlantURLMixin, OrganizationalModel):
	spatial_frame = models.ForeignKey(
		to=SpatialFrame,
		on_delete=models.CASCADE,
		related_name='placements',
	)
	assigned_object_type = models.ForeignKey(
		to=ContentType,
		on_delete=models.PROTECT,
		related_name='power_plant_spatial_placements',
	)
	assigned_object_id = models.PositiveBigIntegerField()
	assigned_object = GenericForeignKey(
		ct_field='assigned_object_type',
		fk_field='assigned_object_id',
	)
	x = models.DecimalField(
		max_digits=12,
		decimal_places=3,
	)
	y = models.DecimalField(
		max_digits=12,
		decimal_places=3,
	)
	z = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	width = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	depth = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	height = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	rotation_degrees = models.DecimalField(
		max_digits=7,
		decimal_places=2,
		default=0,
	)
	anchor = models.CharField(
		max_length=32,
		choices=SpatialAnchorChoices,
		default=SpatialAnchorChoices.ANCHOR_CENTER,
	)
	placement_kind = models.CharField(
		max_length=32,
		choices=SpatialPlacementKindChoices,
		default=SpatialPlacementKindChoices.KIND_PHYSICAL,
	)
	confidence = models.CharField(
		max_length=32,
		choices=SpatialConfidenceChoices,
		default=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
	)
	source_document = models.CharField(
		max_length=200,
		blank=True,
	)
	source_ref = models.CharField(
		max_length=200,
		blank=True,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('spatial_frame__site__name', 'spatial_frame__name', 'name')
		indexes = (
			models.Index(
				fields=('assigned_object_type', 'assigned_object_id'),
				name='nbpp_sp_place_obj',
			),
		)
		verbose_name = 'spatial placement'
		verbose_name_plural = 'spatial placements'

	def clean(self):
		super().clean()
		errors = {}

		if not self.assigned_object_type_id or not self.assigned_object_id:
			errors['assigned_object_id'] = _('Select an assigned object.')
		elif self.assigned_object is None:
			errors['assigned_object_id'] = _('The assigned object could not be found.')

		if self.spatial_frame_id and self.assigned_object is not None:
			self._validate_assigned_object_scope(errors)

		if errors:
			raise ValidationError(errors)

	def _validate_assigned_object_scope(self, errors):
		assigned_site_id = self._assigned_object_site_id(self.assigned_object)
		if assigned_site_id and assigned_site_id != self.spatial_frame.site_id:
			errors['assigned_object_id'] = _('The assigned object must belong to the spatial frame site.')
			return

		assigned_location_id = self._assigned_object_location_id(self.assigned_object)
		if (
			assigned_location_id
			and self.spatial_frame.location_id
			and assigned_location_id != self.spatial_frame.location_id
		):
			errors['assigned_object_id'] = _('The assigned object must belong to the spatial frame location when both are known.')

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


class PhysicalSpace(PowerPlantURLMixin, OrganizationalModel):
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_physical_spaces',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_physical_spaces',
		blank=True,
		null=True,
	)
	spatial_frame = models.ForeignKey(
		to=SpatialFrame,
		on_delete=models.PROTECT,
		related_name='physical_spaces',
		blank=True,
		null=True,
	)
	parent_space = models.ForeignKey(
		to='self',
		on_delete=models.PROTECT,
		related_name='child_spaces',
		blank=True,
		null=True,
	)
	space_kind = models.CharField(
		max_length=32,
		choices=PhysicalSpaceKindChoices,
		default=PhysicalSpaceKindChoices.KIND_ROOM,
	)
	floor_label = models.CharField(
		max_length=64,
		blank=True,
	)
	z_min = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
		help_text=_('Lower elevation bound in the spatial frame units.'),
	)
	z_max = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
		help_text=_('Upper elevation bound in the spatial frame units.'),
	)
	boundary_geometry = models.JSONField(
		default=dict,
		blank=True,
	)
	source_document = models.CharField(
		max_length=200,
		blank=True,
	)
	source_ref = models.CharField(
		max_length=200,
		blank=True,
	)
	confidence = models.CharField(
		max_length=32,
		choices=SpatialConfidenceChoices,
		default=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('site__name', 'location__name', 'space_kind', 'name')
		verbose_name = 'physical space'
		verbose_name_plural = 'physical spaces'

	def clean(self):
		super().clean()
		errors = {}

		if self.location_id and self.location.site_id != self.site_id:
			errors['location'] = _('The selected location must belong to the selected site.')

		if self.spatial_frame_id:
			if self.spatial_frame.site_id != self.site_id:
				errors['spatial_frame'] = _('The spatial frame must belong to the selected site.')
			if (
				self.location_id
				and self.spatial_frame.location_id
				and self.spatial_frame.location_id != self.location_id
			):
				errors['spatial_frame'] = _('The spatial frame location must match the physical space location when both are set.')

		if self.parent_space_id:
			if self.parent_space_id == self.pk:
				errors['parent_space'] = _('A physical space cannot be its own parent.')
			elif self.parent_space.site_id != self.site_id:
				errors['parent_space'] = _('The parent space must belong to the same site.')

		if self.z_min is not None and self.z_max is not None and self.z_min > self.z_max:
			errors['z_max'] = _('Upper elevation must be greater than or equal to lower elevation.')

		if errors:
			raise ValidationError(errors)


class PhysicalElementType(PowerPlantURLMixin, OrganizationalModel):
	discipline = models.CharField(
		max_length=32,
		choices=PlantDisciplineChoices,
		default=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
	)
	element_kind = models.CharField(
		max_length=32,
		choices=PhysicalElementKindChoices,
		default=PhysicalElementKindChoices.KIND_CUSTOM,
	)
	default_width = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	default_depth = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	default_height = models.DecimalField(
		max_digits=12,
		decimal_places=3,
		blank=True,
		null=True,
	)
	default_color = ColorField(
		default='9e9e9e',
	)
	symbol_key = models.CharField(
		max_length=64,
		blank=True,
	)
	is_pathway = models.BooleanField(
		default=False,
	)
	is_supporting_structure = models.BooleanField(
		default=False,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('discipline', 'element_kind', 'name')
		verbose_name = 'physical element type'
		verbose_name_plural = 'physical element types'


class PhysicalElement(PowerPlantURLMixin, OrganizationalModel):
	element_type = models.ForeignKey(
		to=PhysicalElementType,
		on_delete=models.PROTECT,
		related_name='physical_elements',
	)
	site = models.ForeignKey(
		to=Site,
		on_delete=models.PROTECT,
		related_name='power_plant_physical_elements',
	)
	location = models.ForeignKey(
		to=Location,
		on_delete=models.PROTECT,
		related_name='power_plant_physical_elements',
		blank=True,
		null=True,
	)
	physical_space = models.ForeignKey(
		to=PhysicalSpace,
		on_delete=models.PROTECT,
		related_name='physical_elements',
		blank=True,
		null=True,
	)
	label = models.CharField(
		max_length=120,
		blank=True,
	)
	role = models.CharField(
		max_length=120,
		blank=True,
	)
	manufacturer = models.CharField(
		max_length=100,
		blank=True,
	)
	model_name = models.CharField(
		max_length=100,
		blank=True,
	)
	asset_tag = models.CharField(
		max_length=100,
		blank=True,
	)
	install_state = models.CharField(
		max_length=32,
		choices=TopologyStateChoices,
		default=TopologyStateChoices.STATE_PLANNED,
	)
	design_state = models.CharField(
		max_length=32,
		choices=DesignStateChoices,
		default=DesignStateChoices.STATE_PLANNED,
	)
	source_label = models.CharField(
		max_length=120,
		blank=True,
	)
	confidence = models.CharField(
		max_length=32,
		choices=SpatialConfidenceChoices,
		default=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('site__name', 'location__name', 'element_type__discipline', 'name')
		verbose_name = 'physical element'
		verbose_name_plural = 'physical elements'

	def clean(self):
		super().clean()
		errors = {}

		if self.location_id and self.location.site_id != self.site_id:
			errors['location'] = _('The selected location must belong to the selected site.')

		if self.physical_space_id:
			if self.physical_space.site_id != self.site_id:
				errors['physical_space'] = _('The physical space must belong to the selected site.')
			if (
				self.location_id
				and self.physical_space.location_id
				and self.physical_space.location_id != self.location_id
			):
				errors['physical_space'] = _('The physical space location must match the element location when both are set.')

		if errors:
			raise ValidationError(errors)


class PhysicalObjectBinding(PowerPlantURLMixin, OrganizationalModel):
	physical_element = models.ForeignKey(
		to=PhysicalElement,
		on_delete=models.CASCADE,
		related_name='object_bindings',
		blank=True,
		null=True,
	)
	spatial_placement = models.ForeignKey(
		to=SpatialPlacement,
		on_delete=models.CASCADE,
		related_name='object_bindings',
		blank=True,
		null=True,
	)
	assigned_object_type = models.ForeignKey(
		to=ContentType,
		on_delete=models.PROTECT,
		related_name='power_plant_object_bindings',
	)
	assigned_object_id = models.PositiveBigIntegerField()
	assigned_object = GenericForeignKey(
		ct_field='assigned_object_type',
		fk_field='assigned_object_id',
	)
	binding_role = models.CharField(
		max_length=32,
		choices=PhysicalObjectBindingRoleChoices,
		default=PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
	)
	confidence = models.CharField(
		max_length=32,
		choices=SpatialConfidenceChoices,
		default=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
	)
	is_primary = models.BooleanField(
		default=False,
	)
	metadata = models.JSONField(
		default=dict,
		blank=True,
	)

	class Meta:
		ordering = ('physical_element__name', 'spatial_placement__name', 'assigned_object_type', 'assigned_object_id')
		indexes = (
			models.Index(
				fields=('assigned_object_type', 'assigned_object_id'),
				name='nbpp_obj_bind_obj',
			),
		)
		verbose_name = 'physical object binding'
		verbose_name_plural = 'physical object bindings'

	def clean(self):
		super().clean()
		errors = {}

		if not self.physical_element_id and not self.spatial_placement_id:
			errors['physical_element'] = _('Select a physical element, spatial placement, or both.')

		if not self.assigned_object_type_id or not self.assigned_object_id:
			errors['assigned_object_id'] = _('Select an assigned object.')
		elif self.assigned_object is None:
			errors['assigned_object_id'] = _('The assigned object could not be found.')

		if self.physical_element_id and self.spatial_placement_id:
			if self.physical_element.site_id != self.spatial_placement.spatial_frame.site_id:
				errors['spatial_placement'] = _('The spatial placement must belong to the same site as the physical element.')

		if errors:
			raise ValidationError(errors)


class InternalPowerBus(PowerPlantURLMixin, OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='internal_power_buses',
	)
	rack = models.ForeignKey(
		to=Rack,
		on_delete=models.PROTECT,
		related_name='power_plant_internal_buses',
	)
	bus_role = models.CharField(
		max_length=32,
		choices=InternalPowerBusRoleChoices,
		default=InternalPowerBusRoleChoices.ROLE_BUSBAR,
	)
	supply_type = models.CharField(
		max_length=16,
		choices=SupplyTypeChoices,
		default=SupplyTypeChoices.SUPPLY_DC,
	)
	nominal_voltage = models.DecimalField(
		max_digits=8,
		decimal_places=2,
		blank=True,
		null=True,
		help_text=_('Nominal bus voltage, expressed in volts.'),
	)
	design_state = models.CharField(
		max_length=32,
		choices=DesignStateChoices,
		default=DesignStateChoices.STATE_PLANNED,
	)

	class Meta:
		ordering = ('power_system__name', 'rack__name', 'name')
		constraints = (
			models.UniqueConstraint(
				fields=('rack', 'name'),
				name='netbox_power_plant_internalpowerbus_rack_name',
			),
		)
		verbose_name = 'internal power bus'
		verbose_name_plural = 'internal power buses'

	def clean(self):
		super().clean()
		errors = {}

		if self.rack_id and self.power_system_id:
			if self.rack.site_id != self.power_system.site_id:
				errors['rack'] = _('The selected rack must belong to the same site as the power system.')
			elif self.power_system.location_id and self.rack.location_id != self.power_system.location_id:
				errors['rack'] = _('The selected rack must belong to the same location as the power system.')

		if errors:
			raise ValidationError(errors)


class InternalPowerBusAttachment(PowerPlantURLMixin, OrganizationalModel):
	internal_power_bus = models.ForeignKey(
		to=InternalPowerBus,
		on_delete=models.CASCADE,
		related_name='attachments',
	)
	power_port = models.ForeignKey(
		to=PowerPort,
		on_delete=models.PROTECT,
		related_name='power_plant_internal_bus_attachments',
	)
	attachment_role = models.CharField(
		max_length=16,
		choices=InternalPowerBusAttachmentRoleChoices,
	)
	position_index = models.PositiveSmallIntegerField(
		blank=True,
		null=True,
	)
	design_state = models.CharField(
		max_length=32,
		choices=DesignStateChoices,
		default=DesignStateChoices.STATE_PLANNED,
	)

	class Meta:
		ordering = ('internal_power_bus__name', 'attachment_role', 'position_index', 'power_port__device__name', 'power_port__name')
		constraints = (
			models.UniqueConstraint(
				fields=('internal_power_bus', 'power_port'),
				name='netbox_power_plant_internalpowerbusattachment_bus_port',
			),
		)
		verbose_name = 'internal power bus attachment'
		verbose_name_plural = 'internal power bus attachments'

	def clean(self):
		super().clean()
		errors = {}

		if self.internal_power_bus_id and self.power_port_id:
			bus = self.internal_power_bus
			device = self.power_port.device
			if device.site_id != bus.power_system.site_id:
				errors['power_port'] = _('The attached power port device must belong to the same site as the power system.')
			elif device.rack_id != bus.rack_id:
				errors['power_port'] = _('The attached power port device must belong to the bus rack.')

		if errors:
			raise ValidationError(errors)
