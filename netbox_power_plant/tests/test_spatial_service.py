from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, Rack, Site

from netbox_power_plant.choices import NodeKindChoices
from netbox_power_plant.models import ElectricalNode, PowerSystem
from netbox_power_plant.services.spatial import get_spatial_context_for_power_system


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


def _matches(obj, field_name, value):
    if field_name.endswith('__isnull'):
        attr_name = field_name.removesuffix('__isnull')
        return (getattr(obj, attr_name, None) is None) is value
    return getattr(obj, field_name, None) == value


class SpatialServiceTestCase(TestCase):
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
            name='Row PDU A',
            slug='row-pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        manufacturer = Manufacturer.objects.create(name='Spatial Manufacturer', slug='spatial-manufacturer')
        device_type = DeviceType.objects.create(model='Spatial Device', slug='spatial-device', manufacturer=manufacturer)
        device_role = DeviceRole.objects.create(name='Spatial Role', slug='spatial-role', color='ff0000')
        cls.device = Device.objects.create(
            name='Spatial Device A',
            device_type=device_type,
            role=device_role,
            site=cls.site,
            location=cls.location,
            rack=rack,
        )
        cls.rack = rack

    def test_resolves_native_frame_and_spatial_placements(self):
        frame = FakeSpatialFrame(
            pk=101,
            name='Electrical Room A Underlay',
            site=self.site,
            location=self.location,
            width=Decimal('42.50'),
            height=Decimal('18.25'),
            measurement_unit='m',
            get_absolute_url=lambda: '/plugins/power-plant/spatial-frames/101/',
        )
        rack_placement = FakeSpatialPlacement(
            pk=201,
            name='Rack A1 Placement',
            frame=frame,
            rack=self.rack,
            x='15',
            y='25',
            width='2',
            height='3',
            rotation_degrees='0',
            z_index=1,
        )
        device_placement = FakeSpatialPlacement(
            pk=202,
            name='Device Placement',
            frame=frame,
            device=self.device,
            x='18',
            y='28',
            z_index=2,
        )
        node_placement = FakeSpatialPlacement(
            pk=203,
            name='Row PDU Placement',
            frame=frame,
            electrical_node=self.node,
            x='10',
            y='20',
            symbol_kind='distribution',
            label_mode='name_kind',
            color='336699',
            z_index=3,
        )

        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=make_spatial_models(frames=(frame,), placements=(rack_placement, device_placement, node_placement)),
        ):
            context = get_spatial_context_for_power_system(self.power_system)

        self.assertTrue(context.availability.is_available)
        self.assertTrue(context.has_spatial_frame)
        self.assertEqual(context.spatial_frame_id, 101)
        self.assertEqual(context.spatial_frame_url, '/plugins/power-plant/spatial-frames/101/')
        self.assertEqual(context.width, 42.5)
        self.assertEqual(len(context.mapped_racks), 1)
        self.assertEqual(context.mapped_racks[0].object_id, self.rack.pk)
        self.assertEqual(len(context.mapped_devices), 1)
        self.assertEqual(context.mapped_devices[0].object_id, self.device.pk)
        self.assertEqual(len(context.node_placements), 1)
        self.assertEqual(context.node_placements[0].object_id, self.node.pk)

    def test_reports_unavailable_until_worker_a_models_exist(self):
        with patch(
            'netbox_power_plant.services.spatial._load_spatial_models',
            return_value=(None, None, 'Native spatial models could not be imported'),
        ):
            context = get_spatial_context_for_power_system(self.power_system)

        self.assertFalse(context.availability.is_available)
        self.assertFalse(context.has_spatial_frame)
        self.assertIn('Native spatial models', context.availability.reason)
