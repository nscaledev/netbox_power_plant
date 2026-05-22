from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site
from tenancy.models import Tenant

from netbox_power_plant.choices import (
    CapacityReservationStatusChoices,
    InternalPowerBusAttachmentRoleChoices,
    NodeKindChoices,
    PhaseModeChoices,
    PowerFindingStatusChoices,
    PowerValidationRunKindChoices,
)
from netbox_power_plant.models import (
    BESSDetail,
    BuswaySectionDetail,
    CapacityReservation,
    ElectricalNode,
    ElectricalSegment,
    ElectricalTerminal,
    TransformerDetail,
    InternalPowerBus,
    InternalPowerBusAttachment,
    PowerFinding,
    PowerHandoffPoint,
    PowerSystem,
    UPSDetail,
)
from netbox_power_plant.services.capacity import build_node_capacity_path_rollup, build_power_system_capacity_summary
from netbox_power_plant.services.findings import run_and_persist_capacity_findings


class CapacityServiceTestCase(TestCase):
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
        cls.manufacturer = Manufacturer.objects.create(name='Test Manufacturer', slug='test-manufacturer')
        cls.device_type = DeviceType.objects.create(
            model='Capacity Device',
            slug='capacity-device',
            manufacturer=cls.manufacturer,
        )
        cls.device_role = DeviceRole.objects.create(name='Capacity Role', slug='capacity-role', color='ff0000')
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.other_site = Site.objects.create(name='Secondary Site', slug='secondary-site')
        cls.other_rack = Rack.objects.create(name='Rack B1', site=cls.other_site)
        cls.tenant = Tenant.objects.create(name='GPU Tenant', slug='gpu-tenant')
        cls.device = Device.objects.create(
            name='Rack A1 Server',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )

        cls.source_node = ElectricalNode.objects.create(
            name='UPS A',
            slug='ups-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
            phase_mode=PhaseModeChoices.MODE_SINGLE_PHASE,
            usable_capacity_kw=Decimal('1.00'),
            reserve_margin_pct=Decimal('25.00'),
        )
        cls.rack_node = ElectricalNode.objects.create(
            name='Rack A1 Boundary',
            slug='rack-a1-boundary',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            parent_node=cls.source_node,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            phase_mode=PhaseModeChoices.MODE_SINGLE_PHASE,
            usable_capacity_kw=Decimal('2.00'),
        )
        cls.source_terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=cls.source_node,
        )
        cls.rack_terminal = ElectricalTerminal.objects.create(
            name='Input A',
            slug='input-a',
            node=cls.rack_node,
        )
        cls.segment = ElectricalSegment.objects.create(
            name='UPS A to Rack A1',
            slug='ups-a-to-rack-a1',
            power_system=cls.power_system,
            from_terminal=cls.source_terminal,
            to_terminal=cls.rack_terminal,
            voltage_nominal=Decimal('120'),
            ampacity_a=Decimal('10'),
        )
        cls.power_port = PowerPort.objects.create(
            device=cls.device,
            name='PSU A',
            allocated_draw=800,
            maximum_draw=1200,
        )
        cls.missing_draw_port = PowerPort.objects.create(device=cls.device, name='PSU B')
        cls.handoff = PowerHandoffPoint.objects.create(
            name='Rack A1 Handoff A',
            slug='rack-a1-handoff-a',
            power_system=cls.power_system,
            electrical_node=cls.rack_node,
            electrical_terminal=cls.rack_terminal,
            power_port=cls.power_port,
        )
        cls.missing_handoff = PowerHandoffPoint.objects.create(
            name='Rack A1 Handoff B',
            slug='rack-a1-handoff-b',
            power_system=cls.power_system,
            electrical_node=cls.rack_node,
            electrical_terminal=cls.rack_terminal,
            power_port=cls.missing_draw_port,
        )
        cls.bus = InternalPowerBus.objects.create(
            name='Rack A1 Bus',
            slug='rack-a1-bus',
            power_system=cls.power_system,
            rack=cls.rack,
        )
        InternalPowerBusAttachment.objects.create(
            name='Rack A1 Bus Load A',
            slug='rack-a1-bus-load-a',
            internal_power_bus=cls.bus,
            power_port=cls.power_port,
            attachment_role=InternalPowerBusAttachmentRoleChoices.ROLE_LOAD,
        )

    def test_capacity_summary_rolls_up_handoff_load_and_headroom(self):
        summary = build_power_system_capacity_summary(self.power_system)

        source_rollup = next(rollup for rollup in summary.node_rollups if rollup.node == self.source_node)
        rack_rollup = next(rollup for rollup in summary.node_rollups if rollup.node == self.rack_node)
        segment_rollup = summary.segment_rollups[0]
        bus_rollup = summary.bus_rollups[0]

        self.assertEqual(summary.total_load_kw, Decimal('0.800'))
        self.assertEqual(summary.total_capacity_kw, Decimal('1.00'))
        self.assertEqual(summary.headroom_kw, Decimal('0.200'))
        self.assertEqual(source_rollup.total_load_kw, Decimal('0.800'))
        self.assertEqual(source_rollup.headroom_kw, Decimal('0.200'))
        self.assertEqual(rack_rollup.direct_load_kw, Decimal('0.800'))
        self.assertEqual(rack_rollup.headroom_kw, Decimal('1.200'))
        self.assertEqual(segment_rollup.load_kw, Decimal('0.800'))
        self.assertEqual(segment_rollup.capacity_kw, Decimal('1.200'))
        self.assertEqual(bus_rollup.load_kw, Decimal('0.800'))

    def test_capacity_reservation_validation(self):
        reservation = CapacityReservation(
            name='Invalid reservation',
            slug='invalid-reservation',
            node=self.rack_node,
            tenant=self.tenant,
            rack=self.other_rack,
            reserved_kw=Decimal('0.00'),
            valid_from='2026-05-22',
            valid_until='2026-05-21',
        )

        with self.assertRaises(ValidationError) as error:
            reservation.full_clean()

        self.assertIn('reserved_kw', error.exception.message_dict)
        self.assertIn('rack', error.exception.message_dict)
        self.assertIn('valid_until', error.exception.message_dict)

    def test_capacity_summary_subtracts_active_reservations(self):
        CapacityReservation.objects.create(
            name='Rack A1 reserved capacity',
            slug='rack-a1-reserved-capacity',
            node=self.rack_node,
            tenant=self.tenant,
            rack=self.rack,
            reserved_kw=Decimal('0.30'),
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        CapacityReservation.objects.create(
            name='Released rack capacity',
            slug='released-rack-capacity',
            node=self.rack_node,
            tenant=self.tenant,
            rack=self.rack,
            reserved_kw=Decimal('0.50'),
            status=CapacityReservationStatusChoices.STATUS_RELEASED,
        )

        summary = build_power_system_capacity_summary(self.power_system)
        source_rollup = next(rollup for rollup in summary.node_rollups if rollup.node == self.source_node)
        rack_rollup = next(rollup for rollup in summary.node_rollups if rollup.node == self.rack_node)

        self.assertEqual(rack_rollup.direct_reserved_kw, Decimal('0.30'))
        self.assertEqual(rack_rollup.headroom_kw, Decimal('0.900'))
        self.assertEqual(source_rollup.descendant_reserved_kw, Decimal('0.30'))
        self.assertEqual(source_rollup.headroom_kw, Decimal('-0.100'))
        self.assertEqual(summary.headroom_kw, Decimal('-0.100'))

    def test_node_capacity_path_rollup_reports_segment_first_bottleneck(self):
        source_node = ElectricalNode.objects.create(
            name='UPS B',
            slug='ups-b',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_UPS,
            phase_mode=PhaseModeChoices.MODE_SINGLE_PHASE,
            installed_capacity_kw=Decimal('20.00'),
            derating_factor=Decimal('0.5000'),
            reserve_margin_pct=Decimal('10.00'),
        )
        rack_node = ElectricalNode.objects.create(
            name='Rack A2 Boundary',
            slug='rack-a2-boundary',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            parent_node=source_node,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            phase_mode=PhaseModeChoices.MODE_SINGLE_PHASE,
            usable_capacity_kw=Decimal('30.00'),
        )
        source_terminal = ElectricalTerminal.objects.create(
            name='Output B',
            slug='output-b',
            node=source_node,
        )
        rack_terminal = ElectricalTerminal.objects.create(
            name='Input B',
            slug='input-b',
            node=rack_node,
        )
        segment = ElectricalSegment.objects.create(
            name='UPS B to Rack A2',
            slug='ups-b-to-rack-a2',
            power_system=self.power_system,
            from_terminal=source_terminal,
            to_terminal=rack_terminal,
            voltage_nominal=Decimal('120'),
            ampacity_a=Decimal('10'),
            derated_ampacity_a=Decimal('5'),
        )
        CapacityReservation.objects.create(
            name='UPS B active reservation',
            slug='ups-b-active-reservation',
            node=source_node,
            tenant=self.tenant,
            reserved_kw=Decimal('1.00'),
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )

        rollup = build_node_capacity_path_rollup(rack_node)

        self.assertEqual(len(rollup.hops), 2)
        self.assertEqual(rollup.first_bottleneck.segment, segment)
        self.assertEqual(rollup.first_bottleneck.bottleneck_type, 'segment')
        self.assertEqual(rollup.first_bottleneck.segment_capacity_kw, Decimal('0.600'))
        self.assertEqual(rollup.first_bottleneck.node_available_kw, Decimal('8.000'))
        self.assertEqual(rollup.available_kw, Decimal('0.600'))

    def test_detail_model_validation_guards_node_kind_and_percent_ranges(self):
        pdu_node = ElectricalNode.objects.create(
            name='PDU A',
            slug='pdu-a',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        transformer_node = ElectricalNode.objects.create(
            name='Transformer A',
            slug='transformer-a',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_TRANSFORMER,
        )
        bess_node = ElectricalNode.objects.create(
            name='BESS A',
            slug='bess-a',
            power_system=self.power_system,
            site=self.site,
            location=self.location,
            node_kind=NodeKindChoices.KIND_BESS,
        )

        with self.assertRaises(ValidationError):
            UPSDetail(node=pdu_node).full_clean()

        with self.assertRaises(ValidationError):
            TransformerDetail(node=transformer_node, impedance_pct=Decimal('101.00')).full_clean()

        with self.assertRaises(ValidationError):
            BESSDetail(
                node=bess_node,
                usable_soc_min_pct=Decimal('90.00'),
                usable_soc_max_pct=Decimal('10.00'),
            ).full_clean()

        with self.assertRaises(ValidationError):
            BuswaySectionDetail(node=pdu_node, busway_system=pdu_node).full_clean()

    def test_capacity_findings_persist_with_capacity_run_kind(self):
        result = run_and_persist_capacity_findings(self.power_system, name='Capacity Run')

        self.assertEqual(result.run.run_kind, PowerValidationRunKindChoices.KIND_CAPACITY)
        self.assertEqual(result.open_count, 2)
        self.assertEqual(
            set(PowerFinding.objects.filter(run=result.run).values_list('finding_type', flat=True)),
            {'missing_load_data', 'reserve_margin_breached'},
        )
        self.assertTrue(
            PowerFinding.objects.filter(
                run=result.run,
                finding_type='reserve_margin_breached',
                status=PowerFindingStatusChoices.STATUS_OPEN,
                assigned_object_id=self.source_node.pk,
            ).exists()
        )
