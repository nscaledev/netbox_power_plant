from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices, RedundancyTopologyChoices, SupplyTypeChoices, TerminalDirectionChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, ElectricalSegment, ElectricalTerminal, PowerDomain, PowerSystem, PowerHandoffPoint, RedundancyGroup
from netbox_power_plant.services.layout import build_power_system_layout_view


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


class PowerSystemLayoutServiceTestCase(TestCase):
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
        source_node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
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
            from_terminal=source_terminal,
            to_terminal=pdu_terminal,
            segment_kind='feeder',
            path_state='active',
        )
        ElectricalSegment.objects.create(
            name='PDU to Rack Feed',
            slug='pdu-to-rack-feed',
            power_system=cls.power_system,
            power_domain=cls.domain_a,
            from_terminal=pdu_terminal,
            to_terminal=cls.boundary_terminal,
            segment_kind='rack_feed',
            path_state='active',
        )
        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.manufacturer = Manufacturer.objects.create(name='Layout Manufacturer', slug='layout-manufacturer')
        cls.device_type = DeviceType.objects.create(model='Layout Device', slug='layout-device', manufacturer=cls.manufacturer)
        cls.device_role = DeviceRole.objects.create(name='Layout Role', slug='layout-role', color='ff0000')
        cls.device = Device.objects.create(
            name='Layout Device A',
            device_type=cls.device_type,
            role=cls.device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='PSU A')
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
            label_mode='name_kind',
        )

    def test_returns_unavailable_layout_state_until_spatial_models_exist(self):
        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=(None, None, 'Native spatial models could not be imported'),
        ):
            layout = build_power_system_layout_view(self.power_system)

        self.assertFalse(layout.has_spatial_frame)
        self.assertIsNotNone(layout.spatial_context.availability.reason)
        self.assertIn('spatial models', layout.spatial_context.availability.reason.lower())
        self.assertEqual(len(layout.placements), 1)

    def test_builds_layout_from_spatial_context_placements_and_delivery_points(self):
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
        node_placement = FakeSpatialPlacement(
            pk=202,
            name='Row PDU Placement',
            frame=spatial_frame,
            electrical_node=self.pdu_node,
            x='10',
            y='20',
            symbol_kind='distribution',
            label_mode='name_kind',
            z_index=2,
        )

        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=make_spatial_models(frames=(spatial_frame,), placements=(rack_placement, node_placement)),
        ):
            layout = build_power_system_layout_view(self.power_system)

        self.assertTrue(layout.has_spatial_frame)
        self.assertEqual(layout.spatial_context.spatial_frame_id, 101)
        self.assertEqual(len(layout.placements), 1)
        self.assertEqual(layout.placements[0].placement.pk, node_placement.pk)
        self.assertEqual(len(layout.delivery_overlays), 1)
        self.assertTrue(layout.delivery_overlays[0].is_mapped_on_spatial)
        self.assertEqual(layout.delivery_overlays[0].target_name, self.rack.name)
        self.assertEqual(layout.mapped_delivery_count, 1)
        self.assertEqual(len(layout.mapped_assets), 1)
        self.assertEqual(layout.mapped_assets[0].matched_delivery_points[0].pk, self.delivery_point.pk)
