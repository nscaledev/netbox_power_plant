from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from utilities.testing import TestCase as UITestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices, RedundancyTopologyChoices, SupplyTypeChoices, TerminalDirectionChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, ElectricalSegment, ElectricalTerminal, PowerDomain, PowerSystem, PowerHandoffPoint, RedundancyGroup
from netbox_power_plant.services.layout_validation import build_layout_health_summary, run_layout_checks


class FakeQuerySet:
    def __init__(self, objects):
        self.objects = list(objects)

    def select_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def first(self):
        return self.objects[0] if self.objects else None

    def __iter__(self):
        return iter(self.objects)


class FakeManager:
    def __init__(self, objects):
        self.objects = list(objects)

    def filter(self, **kwargs):
        return FakeQuerySet([
            obj
            for obj in self.objects
            if all(_matches(obj, field_name, value) for field_name, value in kwargs.items())
        ])


class FakeSpatialFrame(SimpleNamespace):
    def __str__(self):
        return self.name


class FakeSpatialPlacement(SimpleNamespace):
    def __str__(self):
        return self.name


def make_spatial_models(*, frames=(), placements=()):
    frame_model = type('FakeSpatialFrameModel', (), {'objects': FakeManager(frames)})
    placement_model = type('FakeSpatialPlacementModel', (), {'objects': FakeManager(placements)})
    return frame_model, placement_model, None


def make_spatial_frame(pk, *, site=None, location=None):
    return FakeSpatialFrame(
        pk=pk,
        name=f'Spatial Underlay {pk}',
        site=site,
        location=location,
        assigned_image=SimpleNamespace(pk=pk + 1000),
        width=Decimal('42.50'),
        height=Decimal('18.25'),
        measurement_unit='m',
        get_absolute_url=lambda: f'/plugins/power-plant/spatial-frames/{pk}/',
    )


def _matches(obj, field_name, value):
    if field_name.endswith('__isnull'):
        attr_name = field_name.removesuffix('__isnull')
        return (getattr(obj, attr_name, None) is None) is value
    return getattr(obj, field_name, None) == value


class LayoutValidationServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.other_location = Location.objects.create(site=cls.site, name='Electrical Room B', slug='electrical-room-b')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.domain_a = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        cls.domain_b = PowerDomain.objects.create(
            name='Domain B',
            slug='domain-b',
            power_system=cls.power_system,
            code='B',
        )
        cls.redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=cls.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        cls.redundancy_group.power_domains.set([cls.domain_a, cls.domain_b])
        cls.pdu_node = ElectricalNode.objects.create(
            name='Row PDU A',
            slug='row-pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.source_node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.source_terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=cls.source_node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        cls.pdu_terminal = ElectricalTerminal.objects.create(
            name='Input A',
            slug='input-a',
            node=cls.pdu_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        cls.boundary_node = ElectricalNode.objects.create(
            name='Rack Boundary A',
            slug='rack-boundary-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            topology_state='active',
        )
        cls.boundary_terminal = ElectricalTerminal.objects.create(
            name='Rack Input A',
            slug='rack-input-a',
            node=cls.boundary_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        ElectricalSegment.objects.create(
            name='UPS to PDU Feed',
            slug='ups-to-pdu-feed',
            power_system=cls.power_system,
            power_domain=cls.domain_a,
            from_terminal=cls.source_terminal,
            to_terminal=cls.pdu_terminal,
            segment_kind='feeder',
            path_state='active',
        )
        ElectricalSegment.objects.create(
            name='PDU to Rack Feed',
            slug='pdu-to-rack-feed',
            power_system=cls.power_system,
            power_domain=cls.domain_a,
            from_terminal=cls.pdu_terminal,
            to_terminal=cls.boundary_terminal,
            segment_kind='rack_feed',
            path_state='active',
        )
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.unmapped_rack = Rack.objects.create(name='Rack B1', site=cls.site, location=cls.location)
        cls.orphan_rack = Rack.objects.create(name='Rack C1', site=cls.site, location=cls.location)
        cls.manufacturer = Manufacturer.objects.create(name='Layout Validation Manufacturer', slug='layout-validation-manufacturer')
        cls.device_type = DeviceType.objects.create(model='Layout Validation Device', slug='layout-validation-device', manufacturer=cls.manufacturer)
        cls.device_role = DeviceRole.objects.create(name='Layout Validation Role', slug='layout-validation-role', color='ff0000')
        cls.device = Device.objects.create(
            name='Layout Validation Device A',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.unmapped_device = Device.objects.create(
            name='Layout Validation Device B',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.unmapped_rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='PSU A')
        cls.unmapped_power_port = PowerPort.objects.create(device=cls.unmapped_device, name='PSU A')
        cls.delivery_point = PowerHandoffPoint.objects.create(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=cls.power_system,
            electrical_node=cls.boundary_node,
            electrical_terminal=cls.boundary_terminal,
            power_port=cls.power_port,
            expected_redundancy_group=cls.redundancy_group,
            feed_label='A-feed',
        )
        cls.unmapped_delivery_point = PowerHandoffPoint.objects.create(
            name='Rack B Delivery',
            slug='rack-b-delivery',
            power_system=cls.power_system,
            electrical_node=cls.boundary_node,
            electrical_terminal=cls.boundary_terminal,
            power_port=cls.unmapped_power_port,
            expected_redundancy_group=cls.redundancy_group,
            feed_label='B-feed',
        )
        cls.placement = ElectricalNodePlacement.objects.create(
            name='Row PDU Placement',
            slug='row-pdu-placement',
            power_system=cls.power_system,
            electrical_node=cls.pdu_node,
            site=cls.site,
            location=cls.location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='10.00',
            y='20.00',
            symbol_kind='distribution',
        )
        cls.mis_scoped_placement = ElectricalNodePlacement.objects.create(
            name='Bad Placement',
            slug='bad-placement',
            power_system=cls.power_system,
            electrical_node=cls.source_node,
            site=cls.site,
            location=cls.other_location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='30.00',
            y='40.00',
            symbol_kind='distribution',
        )

    def test_missing_spatial_underlay_is_not_a_layout_finding(self):
        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=make_spatial_models(),
        ):
            findings = run_layout_checks(self.power_system)

        self.assertNotIn('missing_spatial_underlay', {finding.finding_type for finding in findings})

    def test_reports_spatial_placement_and_redundancy_findings(self):
        spatial_frame = make_spatial_frame(101, site=self.site, location=self.location)
        rack_placement = FakeSpatialPlacement(
            pk=201,
            name='Rack A1 Placement',
            frame=spatial_frame,
            rack=self.rack,
            x='15',
            y='25',
            z_index=1,
        )
        orphan_placement = FakeSpatialPlacement(
            pk=202,
            name='Rack C1 Placement',
            frame=spatial_frame,
            rack=self.orphan_rack,
            x='35',
            y='45',
            z_index=2,
        )
        node_placement = FakeSpatialPlacement(
            pk=203,
            name='Row PDU Placement',
            frame=spatial_frame,
            electrical_node=self.pdu_node,
            x='10',
            y='20',
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            z_index=3,
        )
        mis_scoped_placement = FakeSpatialPlacement(
            pk=204,
            name='Bad Spatial Placement',
            frame=spatial_frame,
            electrical_node=self.source_node,
            site=self.site,
            location=self.other_location,
            site_id=self.site.pk,
            location_id=self.other_location.pk,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='30',
            y='40',
            z_index=4,
        )

        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=make_spatial_models(
                frames=(spatial_frame,),
                placements=(rack_placement, orphan_placement, node_placement, mis_scoped_placement),
            ),
        ):
            summary = build_layout_health_summary(self.power_system)

        finding_types = {finding.finding_type for finding in summary.findings}
        self.assertIn('unmapped_delivery_handoff', finding_types)
        self.assertIn('orphan_spatial_placement', finding_types)
        self.assertIn('redundancy_gap_visible_in_layout', finding_types)
        self.assertIn('spatial_placement_scope_mismatch', finding_types)
        self.assertEqual(summary.unmapped_delivery_count, 1)
        self.assertEqual(summary.orphan_mapped_asset_count, 1)
        self.assertEqual(summary.redundancy_gap_count, 1)
        self.assertEqual(summary.mis_scoped_placement_count, 1)


class LayoutValidationPowerSystemViewTestCase(UITestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'dcim.view_rack',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_powerdomain',
        'netbox_power_plant.view_redundancygroup',
        'netbox_power_plant.view_electricalnode',
        'netbox_power_plant.view_electricalterminal',
        'netbox_power_plant.view_electricalsegment',
        'netbox_power_plant.view_powerhandoffpoint',
        'netbox_power_plant.view_electricalnodeplacement',
    )

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
        domain_a = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        domain_b = PowerDomain.objects.create(
            name='Domain B',
            slug='domain-b',
            power_system=cls.power_system,
            code='B',
        )
        redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=cls.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        redundancy_group.power_domains.set([domain_a, domain_b])
        source_node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        pdu_node = ElectricalNode.objects.create(
            name='Row PDU A',
            slug='row-pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        boundary_node = ElectricalNode.objects.create(
            name='Rack Boundary A',
            slug='rack-boundary-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            topology_state='active',
        )
        source_terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=source_node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        pdu_terminal = ElectricalTerminal.objects.create(
            name='Input A',
            slug='input-a',
            node=pdu_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        boundary_terminal = ElectricalTerminal.objects.create(
            name='Rack Input A',
            slug='rack-input-a',
            node=boundary_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        ElectricalSegment.objects.create(
            name='UPS to PDU Feed',
            slug='ups-to-pdu-feed',
            power_system=cls.power_system,
            power_domain=domain_a,
            from_terminal=source_terminal,
            to_terminal=pdu_terminal,
            segment_kind='feeder',
            path_state='active',
        )
        ElectricalSegment.objects.create(
            name='PDU to Rack Feed',
            slug='pdu-to-rack-feed',
            power_system=cls.power_system,
            power_domain=domain_a,
            from_terminal=pdu_terminal,
            to_terminal=boundary_terminal,
            segment_kind='rack_feed',
            path_state='active',
        )
        manufacturer = Manufacturer.objects.create(name='Layout Validation View Manufacturer', slug='layout-validation-view-manufacturer')
        device_type = DeviceType.objects.create(model='Layout Validation View Device', slug='layout-validation-view-device', manufacturer=manufacturer)
        device_role = DeviceRole.objects.create(name='Layout Validation View Role', slug='layout-validation-view-role', color='ff0000')
        rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        device = Device.objects.create(
            name='Layout Validation View Device A',
            device_type=device_type,
            role=device_role,
            site=cls.site,
            location=cls.location,
            rack=rack,
        )
        power_port = PowerPort.objects.create(device=device, name='PSU A')
        PowerHandoffPoint.objects.create(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=cls.power_system,
            electrical_node=boundary_node,
            electrical_terminal=boundary_terminal,
            power_port=power_port,
            expected_redundancy_group=redundancy_group,
            feed_label='A-feed',
        )

    def test_power_system_detail_renders_layout_health_summary(self):
        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=make_spatial_models(),
        ):
            response = self.client.get(reverse('plugins:netbox_power_plant:powersystem', kwargs={'pk': self.power_system.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Layout Health')
        self.assertContains(response, 'Needs attention')
        self.assertContains(response, 'has no matching spatial placement')
