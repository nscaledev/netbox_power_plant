from decimal import Decimal

from django.core.exceptions import ValidationError
from django.template.loader import get_template
from django.test import TestCase

from dcim.models import Location, Rack, Site
from tenancy.models import Tenant

from netbox_power_plant import filtersets, forms, tables
from netbox_power_plant.choices import (
    CapacityReservationStatusChoices,
    NodeKindChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import (
    BESSDetail,
    BuswaySectionDetail,
    CapacityReservation,
    ElectricalNode,
    GeneratorDetail,
    PowerSystem,
    TransformerDetail,
    UPSDetail,
)
from netbox_power_plant.services.validation import run_topology_checks


class NeocloudReservationWorkflowTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.other_site = Site.objects.create(name='Secondary Site', slug='secondary-site')
        cls.location = Location.objects.create(site=cls.site, name='Hall A', slug='hall-a')
        cls.power_system = PowerSystem.objects.create(
            name='AI Hall Power',
            slug='ai-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.tenant = Tenant.objects.create(name='GPU Tenant', slug='gpu-tenant')
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.other_rack = Rack.objects.create(name='Rack B1', site=cls.other_site)

        cls.ups_node = cls._node('UPS A', 'ups-a', NodeKindChoices.KIND_UPS)
        cls.generator_node = cls._node('Generator A', 'generator-a', NodeKindChoices.KIND_GENERATOR)
        cls.transformer_node = cls._node('Transformer A', 'transformer-a', NodeKindChoices.KIND_TRANSFORMER)
        cls.bess_node = cls._node('BESS A', 'bess-a', NodeKindChoices.KIND_BESS)
        cls.busway_node = cls._node('Busway A', 'busway-a', NodeKindChoices.KIND_BUSWAY_RUN)
        cls.pdu_node = cls._node('PDU A', 'pdu-a', NodeKindChoices.KIND_PDU)

    @classmethod
    def _node(cls, name, slug, node_kind):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=node_kind,
            topology_state=TopologyStateChoices.STATE_ACTIVE,
        )

    def test_capacity_reservation_form_surfaces_operator_validation_errors(self):
        form = forms.CapacityReservationForm(data={
            'name': 'Invalid Reservation',
            'slug': 'invalid-reservation',
            'node': self.ups_node.pk,
            'tenant': self.tenant.pk,
            'rack': self.other_rack.pk,
            'reserved_kw': '0.00',
            'status': CapacityReservationStatusChoices.STATUS_ACTIVE,
            'valid_from': '2026-05-22',
            'valid_until': '2026-05-21',
            'description': '',
            'notes': '',
            'comments': '',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('reserved_kw', form.errors)
        self.assertIn('rack', form.errors)
        self.assertIn('valid_until', form.errors)

    def test_capacity_reservation_filterset_and_table_expose_operator_columns(self):
        active = CapacityReservation.objects.create(
            name='Rack A1 active reservation',
            slug='rack-a1-active-reservation',
            node=self.ups_node,
            tenant=self.tenant,
            rack=self.rack,
            reserved_kw=Decimal('2.50'),
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
            valid_from='2026-05-22',
        )
        CapacityReservation.objects.create(
            name='Rack A1 released reservation',
            slug='rack-a1-released-reservation',
            node=self.ups_node,
            tenant=self.tenant,
            rack=self.rack,
            reserved_kw=Decimal('1.00'),
            status=CapacityReservationStatusChoices.STATUS_RELEASED,
        )

        queryset = filtersets.CapacityReservationFilterSet(
            data={'status': CapacityReservationStatusChoices.STATUS_ACTIVE},
            queryset=CapacityReservation.objects.all(),
        ).qs
        table = tables.CapacityReservationTable(queryset)

        self.assertQuerySetEqual(queryset, [active], transform=lambda item: item)
        self.assertIn('node', table.base_columns)
        self.assertIn('tenant', table.base_columns)
        self.assertIn('rack', table.base_columns)
        self.assertIn('reserved_kw', table.base_columns)
        self.assertIn('status', table.base_columns)
        self.assertIn('valid_from', table.base_columns)
        self.assertIn('valid_until', table.base_columns)
        self.assertIn('Active', str(table.render_status(active.status, active)))

    def test_detail_forms_constrain_node_choices_by_kind(self):
        form_expectations = (
            (forms.UPSDetailForm, self.ups_node, self.pdu_node),
            (forms.GeneratorDetailForm, self.generator_node, self.pdu_node),
            (forms.TransformerDetailForm, self.transformer_node, self.pdu_node),
            (forms.BESSDetailForm, self.bess_node, self.pdu_node),
            (forms.BuswaySectionDetailForm, self.busway_node, self.pdu_node),
        )

        for form_class, allowed_node, excluded_node in form_expectations:
            with self.subTest(form_class=form_class.__name__):
                form = form_class()
                self.assertTrue(form.fields['node'].queryset.filter(pk=allowed_node.pk).exists())
                self.assertFalse(form.fields['node'].queryset.filter(pk=excluded_node.pk).exists())

    def test_detail_model_validation_guards_node_kind_and_percent_ranges(self):
        with self.assertRaises(ValidationError):
            UPSDetail(node=self.pdu_node).full_clean()

        with self.assertRaises(ValidationError):
            TransformerDetail(node=self.transformer_node, impedance_pct=Decimal('101.00')).full_clean()

        with self.assertRaises(ValidationError):
            BESSDetail(
                node=self.bess_node,
                usable_soc_min_pct=Decimal('90.00'),
                usable_soc_max_pct=Decimal('10.00'),
            ).full_clean()

        with self.assertRaises(ValidationError):
            BuswaySectionDetail(node=self.pdu_node, busway_system=self.pdu_node).full_clean()

    def test_detail_tables_render_parent_node_and_audit_fields(self):
        ups_detail = UPSDetail.objects.create(
            node=self.ups_node,
            ups_topology='double-conversion',
            battery_autonomy_minutes=Decimal('12.00'),
            module_count=4,
            module_rating_kw=Decimal('500.00'),
            maintenance_bypass_present=True,
        )
        generator_detail = GeneratorDetail.objects.create(
            node=self.generator_node,
            fuel_type='diesel',
            runtime_at_full_load_hours=Decimal('48.00'),
        )
        transformer_detail = TransformerDetail.objects.create(
            node=self.transformer_node,
            primary_kv=Decimal('13.800'),
            secondary_kv=Decimal('0.480'),
            kva_rating=Decimal('2500.00'),
        )
        bess_detail = BESSDetail.objects.create(
            node=self.bess_node,
            technology='Li-ion',
            energy_capacity_kwh=Decimal('2000.00'),
        )
        busway_detail = BuswaySectionDetail.objects.create(
            node=self.busway_node,
            busway_system=self.busway_node,
            section_index=1,
            rated_ampacity_a=Decimal('800.00'),
        )

        table_expectations = (
            (tables.UPSDetailTable([ups_detail]), 'module_rating_kw'),
            (tables.GeneratorDetailTable([generator_detail]), 'fuel_type'),
            (tables.TransformerDetailTable([transformer_detail]), 'kva_rating'),
            (tables.BESSDetailTable([bess_detail]), 'energy_capacity_kwh'),
            (tables.BuswaySectionDetailTable([busway_detail]), 'rated_ampacity_a'),
        )

        for table, audit_column in table_expectations:
            with self.subTest(table=table.__class__.__name__):
                self.assertIn('node', table.base_columns)
                self.assertIn('power_system', table.base_columns)
                self.assertIn(audit_column, table.base_columns)

    def test_topology_validation_flags_missing_active_equipment_details(self):
        output = run_topology_checks(self.power_system)
        finding_types = [finding['finding_type'] for finding in output['findings']]

        self.assertIn('missing_equipment_detail', finding_types)
        self.assertTrue(
            any(
                finding.get('object') == self.ups_node
                and finding.get('expected_detail_model') == 'netbox_power_plant.upsdetail'
                for finding in output['findings']
            )
        )

        UPSDetail.objects.create(node=self.ups_node, ups_topology='double-conversion')
        output = run_topology_checks(self.power_system)

        self.assertFalse(
            any(
                finding.get('object') == self.ups_node
                and finding['finding_type'] == 'missing_equipment_detail'
                for finding in output['findings']
            )
        )

    def test_detail_templates_are_available_for_wired_object_views(self):
        for template_name in (
            'netbox_power_plant/capacityreservation.html',
            'netbox_power_plant/upsdetail.html',
            'netbox_power_plant/generatordetail.html',
            'netbox_power_plant/transformerdetail.html',
            'netbox_power_plant/bessdetail.html',
            'netbox_power_plant/buswaysectiondetail.html',
        ):
            with self.subTest(template_name=template_name):
                self.assertIsNotNone(get_template(template_name))
