from decimal import Decimal

from django.test import TestCase as DjangoTestCase
from django.urls import reverse
from utilities.testing import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PhaseModeChoices,
    PowerFindingSeverityChoices,
    PowerFindingStatusChoices,
    PowerValidationRunKindChoices,
    PowerValidationRunStatusChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalTerminal,
    InstantiationRun,
    PowerArchitectureTemplate,
    PowerFinding,
    PowerHandoffPoint,
    PowerSystem,
    PowerValidationRun,
)
from netbox_power_plant.services.operator_dashboard import build_operator_dashboard


class OperatorDashboardServiceTestCase(DjangoTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.node = ElectricalNode.objects.create(
            name='UPS A',
            slug='ups-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
            phase_mode=PhaseModeChoices.MODE_SINGLE_PHASE,
            usable_capacity_kw=Decimal('2.00'),
        )
        cls.terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=cls.node,
        )
        cls.manufacturer = Manufacturer.objects.create(name='Operator Manufacturer', slug='operator-manufacturer')
        cls.device_type = DeviceType.objects.create(
            model='Operator Device',
            slug='operator-device',
            manufacturer=cls.manufacturer,
        )
        cls.device_role = DeviceRole.objects.create(name='Operator Role', slug='operator-role', color='ff0000')
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.device = Device.objects.create(
            name='Rack A1 Server',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(
            device=cls.device,
            name='PSU A',
            allocated_draw=500,
            maximum_draw=700,
        )
        PowerHandoffPoint.objects.create(
            name='Rack A1 Handoff A',
            slug='rack-a1-handoff-a',
            power_system=cls.power_system,
            electrical_node=cls.node,
            electrical_terminal=cls.terminal,
            power_port=cls.power_port,
        )
        cls.validation_run = PowerValidationRun.objects.create(
            name='Capacity Run',
            slug='capacity-run',
            power_system=cls.power_system,
            run_kind=PowerValidationRunKindChoices.KIND_CAPACITY,
            status=PowerValidationRunStatusChoices.STATUS_COMPLETED,
            finding_count=1,
        )
        PowerFinding.objects.create(
            name='Critical Finding',
            slug='critical-finding',
            run=cls.validation_run,
            power_system=cls.power_system,
            fingerprint='a' * 64,
            finding_type='capacity_exceeded',
            severity=PowerFindingSeverityChoices.SEVERITY_CRITICAL,
            status=PowerFindingStatusChoices.STATUS_OPEN,
            message='Capacity exceeded.',
        )
        PowerFinding.objects.create(
            name='Resolved Finding',
            slug='resolved-finding',
            run=cls.validation_run,
            power_system=cls.power_system,
            fingerprint='b' * 64,
            finding_type='old_capacity_exceeded',
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            status=PowerFindingStatusChoices.STATUS_RESOLVED,
            message='Old capacity finding.',
        )
        cls.template = PowerArchitectureTemplate.objects.create(
            name='Operator Template',
            slug='operator-template',
            version='1',
        )
        InstantiationRun.objects.create(
            name='Operator Template Dry Run',
            slug='operator-template-dry-run',
            power_system=cls.power_system,
            template=cls.template,
            status='dry-run',
            dry_run=True,
            artifact_count=2,
        )

    def test_dashboard_rolls_up_operator_state(self):
        dashboard = build_operator_dashboard()
        row = dashboard.rows[0]

        self.assertEqual(dashboard.system_count, 1)
        self.assertEqual(dashboard.open_finding_count, 1)
        self.assertEqual(dashboard.critical_finding_count, 1)
        self.assertEqual(row.total_load_kw, Decimal('0.500'))
        self.assertEqual(row.total_capacity_kw, Decimal('2.00'))
        self.assertEqual(row.headroom_kw, Decimal('1.500'))
        self.assertEqual(row.open_finding_count, 1)
        self.assertEqual(row.severity_counts[0].severity, PowerFindingSeverityChoices.SEVERITY_CRITICAL)
        self.assertEqual(row.severity_counts[0].count, 1)
        self.assertEqual(row.severity_counts[1].count, 0)
        self.assertEqual(row.recent_validation_runs, (self.validation_run,))
        self.assertEqual(row.recent_instantiation_runs[0].template, self.template)
        self.assertIn('power_system_id={}'.format(self.power_system.pk), row.links['findings'])
        self.assertIn('status=open', row.links['findings'])


class OperatorDashboardViewTestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_powerfinding',
        'netbox_power_plant.view_powervalidationrun',
        'netbox_power_plant.view_powerhandoffpoint',
    )

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
        )

    def test_operator_dashboard_renders_read_only_center(self):
        response = self.client.get(reverse('plugins:netbox_power_plant:operator_dashboard'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Operator Center')
        self.assertContains(response, self.power_system.name)
        self.assertContains(
            response,
            reverse('plugins:netbox_power_plant:powersystem_layout', kwargs={'pk': self.power_system.pk}),
        )

        post_response = self.client.post(reverse('plugins:netbox_power_plant:operator_dashboard'), {})
        self.assertEqual(post_response.status_code, 405)
