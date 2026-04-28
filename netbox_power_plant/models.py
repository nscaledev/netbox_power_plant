from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from dcim.models import Device, Location, Rack, Site
from netbox.models import OrganizationalModel
from utilities.fields import ColorField

from .choices import (
	DesignStateChoices,
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
from .services.validation import validate_topology_segment, validate_topology_terminal


class PowerSystem(OrganizationalModel):
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


class PowerDomain(OrganizationalModel):
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


class RedundancyGroup(OrganizationalModel):
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


class ElectricalNode(OrganizationalModel):
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


class ElectricalTerminal(OrganizationalModel):
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


class ElectricalSegment(OrganizationalModel):
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


class RackDeliveryPoint(OrganizationalModel):
	power_system = models.ForeignKey(
		to=PowerSystem,
		on_delete=models.CASCADE,
		related_name='rack_delivery_points',
	)
	electrical_node = models.ForeignKey(
		to=ElectricalNode,
		on_delete=models.PROTECT,
		related_name='rack_delivery_points',
		blank=True,
		null=True,
	)
	electrical_terminal = models.ForeignKey(
		to=ElectricalTerminal,
		on_delete=models.PROTECT,
		related_name='rack_delivery_points',
		blank=True,
		null=True,
	)
	rack = models.ForeignKey(
		to=Rack,
		on_delete=models.PROTECT,
		related_name='power_plant_delivery_points',
		blank=True,
		null=True,
	)
	device = models.ForeignKey(
		to=Device,
		on_delete=models.PROTECT,
		related_name='power_plant_delivery_points',
		blank=True,
		null=True,
	)
	expected_redundancy_group = models.ForeignKey(
		to=RedundancyGroup,
		on_delete=models.PROTECT,
		related_name='rack_delivery_points',
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
		verbose_name = 'rack delivery point'
		verbose_name_plural = 'rack delivery points'

	def clean(self):
		super().clean()
		errors = {}

		if bool(self.rack) == bool(self.device):
			errors['rack'] = _('Select exactly one of rack or device.')
			errors['device'] = _('Select exactly one of rack or device.')

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

		if self.rack_id:
			self._validate_site_location_scope(errors, self.rack, 'rack')

		if self.device_id:
			self._validate_site_location_scope(errors, self.device, 'device')

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


class ElectricalNodePlacement(OrganizationalModel):
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
		help_text=_('Horizontal floorplan coordinate in plugin-owned overlay space.'),
	)
	y = models.DecimalField(
		max_digits=10,
		decimal_places=2,
		help_text=_('Vertical floorplan coordinate in plugin-owned overlay space.'),
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
		else:
			if self.placement_scope_type != PlacementScopeChoices.SCOPE_SITE:
				errors['placement_scope_type'] = _('Site-scoped power systems require site placements.')
			if self.location_id:
				errors['location'] = _('Leave location blank when the power system does not resolve to a location floorplan.')

		if self.placement_scope_type == PlacementScopeChoices.SCOPE_SITE and self.location_id:
			errors['location'] = _('Site-scoped placements cannot set a location.')

		if self.placement_scope_type == PlacementScopeChoices.SCOPE_LOCATION and not self.location_id:
			errors['location'] = _('Select a location for location-scoped placements.')

		if self._has_duplicate_scope():
			errors['electrical_node'] = _('A placement already exists for this node in the resolved floorplan scope.')

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

