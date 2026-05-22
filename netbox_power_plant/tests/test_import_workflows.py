from decimal import Decimal

from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Site

from netbox_power_plant.models import ElectricalNode, ElectricalTerminal, PowerHandoffPoint, PowerSystem
from netbox_power_plant.services.import_workflows import (
    StagedCircuitEndpointImportRowResult,
    StagedCircuitEndpointImportSummary,
    import_staged_circuit_endpoints,
)
from netbox_power_plant.services.staging import StagedCircuitEndpoint


class ImportWorkflowServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='MAD-1', slug='mad-1')
        cls.location = Location.objects.create(site=cls.site, name='Data Hall 1', slug='data-hall-1')
        cls.power_system = PowerSystem.objects.create(
            name='MAD-1 Power Plant',
            slug='mad-1-power-plant',
            site=cls.site,
            location=cls.location,
        )
        cls.manufacturer = Manufacturer.objects.create(name='Import Manufacturer', slug='import-manufacturer')
        cls.device_type = DeviceType.objects.create(
            manufacturer=cls.manufacturer,
            model='Rack PDU',
            slug='import-rack-pdu',
        )
        cls.device_role = DeviceRole.objects.create(name='Rack PDU', slug='import-rack-pdu', color='ff0000')
        cls.device = Device.objects.create(
            name='MAD1-RACK-A1-PDU-A',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='Input A')

    def test_dry_run_reports_creates_and_bindings_without_persisting(self):
        endpoints = (
            StagedCircuitEndpoint(
                source_key='MAD1-RPP-01-L21-A1-A',
                cabinet_label='A1',
                feed_label='A-feed',
                voltage_nominal='415',
                amperage_rating='60',
            ),
            {
                'source_key': 'MAD1-RPP-01-L22-A1-B',
                'cabinet_label': 'A1',
                'feed_label': 'B-feed',
                'power_port_id': self.power_port.pk,
            },
        )

        summary = import_staged_circuit_endpoints(self.power_system, endpoints)

        self.assertIsInstance(summary, StagedCircuitEndpointImportSummary)
        self.assertTrue(summary.dry_run)
        self.assertTrue(summary.succeeded)
        self.assertEqual(summary.total_count, 2)
        self.assertEqual(summary.created_count, 2)
        self.assertEqual(summary.updated_count, 0)
        self.assertEqual(summary.blocked_count, 0)
        self.assertEqual(summary.bound_count, 1)
        self.assertEqual(summary.handoff_created_count, 1)
        self.assertEqual(ElectricalNode.objects.count(), 0)
        self.assertEqual(ElectricalTerminal.objects.count(), 0)
        self.assertEqual(PowerHandoffPoint.objects.count(), 0)

    def test_apply_idempotently_stamps_and_reconciles_power_port_bindings(self):
        endpoints = (
            {
                'source_key': 'MAD1-RPP-01-L23-A2-A',
                'cabinet_label': 'A2',
                'feed_label': 'A-feed',
                'voltage_nominal': '415',
            },
            StagedCircuitEndpoint(
                source_key='MAD1-RPP-01-L24-A2-B',
                cabinet_label='A2',
                feed_label='B-feed',
            ),
        )
        bindings = {
            'MAD1-RPP-01-L24-A2-B': {
                'device_name': self.device.name,
                'power_port_name': self.power_port.name,
                'delivery_role': 'primary',
            },
        }

        first_summary = import_staged_circuit_endpoints(
            self.power_system,
            endpoints,
            apply=True,
            power_port_bindings=bindings,
        )

        self.assertFalse(first_summary.dry_run)
        self.assertEqual(first_summary.created_count, 2)
        self.assertEqual(first_summary.updated_count, 0)
        self.assertEqual(first_summary.blocked_count, 0)
        self.assertEqual(first_summary.node_created_count, 2)
        self.assertEqual(first_summary.terminal_created_count, 2)
        self.assertEqual(first_summary.handoff_created_count, 1)
        self.assertEqual(ElectricalNode.objects.count(), 2)
        self.assertEqual(ElectricalTerminal.objects.count(), 2)
        self.assertEqual(PowerHandoffPoint.objects.count(), 1)
        handoff = PowerHandoffPoint.objects.get()
        self.assertEqual(handoff.power_port, self.power_port)
        self.assertEqual(handoff.delivery_role, 'primary')

        second_summary = import_staged_circuit_endpoints(
            self.power_system,
            (
                {**endpoints[0], 'voltage_nominal': '400'},
                endpoints[1],
            ),
            apply=True,
            power_port_bindings={
                'MAD1-RPP-01-L24-A2-B': {
                    'power_port': self.power_port,
                    'delivery_role': 'redundant',
                },
            },
        )

        self.assertEqual(second_summary.created_count, 0)
        self.assertEqual(second_summary.updated_count, 2)
        self.assertEqual(second_summary.blocked_count, 0)
        self.assertEqual(second_summary.handoff_created_count, 0)
        self.assertEqual(ElectricalNode.objects.count(), 2)
        self.assertEqual(ElectricalTerminal.objects.count(), 2)
        self.assertEqual(PowerHandoffPoint.objects.count(), 1)
        updated_terminal = ElectricalTerminal.objects.get(
            slug='madison-power-endpoint-mad1-rpp-01-l23-a2-a-terminal'
        )
        self.assertEqual(updated_terminal.voltage_nominal, Decimal('400'))
        handoff.refresh_from_db()
        self.assertEqual(handoff.delivery_role, 'redundant')

    def test_blocked_rows_report_clear_reasons_without_partial_row_writes(self):
        endpoints = (
            {'cabinet_label': 'A1'},
            {
                'source_key': 'MAD1-RPP-01-L25-A3-A',
                'cabinet_label': 'A3',
                'power_port_id': 999999,
            },
            {
                'source_key': 'MAD1-RPP-01-L26-A3-B',
                'cabinet_label': 'A3',
            },
        )

        summary = import_staged_circuit_endpoints(self.power_system, endpoints, apply=True)

        self.assertFalse(summary.succeeded)
        self.assertEqual(summary.created_count, 1)
        self.assertEqual(summary.updated_count, 0)
        self.assertEqual(summary.blocked_count, 2)
        self.assertEqual(ElectricalNode.objects.count(), 1)
        self.assertEqual(ElectricalTerminal.objects.count(), 1)
        self.assertEqual(PowerHandoffPoint.objects.count(), 0)
        self.assertIn('source_key is required.', summary.failure_reasons[0])
        self.assertIn('PowerPort not found for pk 999999.', summary.failure_reasons[1])

    def test_duplicate_source_keys_are_blocked_before_stamping(self):
        endpoints = (
            {'source_key': 'MAD1-RPP-01-L27-A4-A', 'cabinet_label': 'A4'},
            {'source_key': 'MAD1-RPP-01-L27-A4-A', 'cabinet_label': 'A4 duplicate'},
        )

        summary = import_staged_circuit_endpoints(self.power_system, endpoints, apply=True)

        self.assertEqual(summary.created_count, 0)
        self.assertEqual(summary.updated_count, 0)
        self.assertEqual(summary.blocked_count, 2)
        self.assertEqual(ElectricalNode.objects.count(), 0)
        self.assertEqual(ElectricalTerminal.objects.count(), 0)
        for row in summary.rows:
            self.assertIsInstance(row, StagedCircuitEndpointImportRowResult)
            self.assertIn('duplicate source_key in import batch', row.failure_reason)
