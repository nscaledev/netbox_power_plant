from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from netbox_power_plant.services.floorplan import (
    get_floorplan_availability,
    get_floorplan_context_for_power_system,
    has_floorplan_context,
    list_mapped_devices,
    list_mapped_racks,
)


class FakeFloorplanQuerySet:
    def __init__(self, floorplans):
        self.floorplans = list(floorplans)

    def order_by(self, *_args):
        return self

    def first(self):
        return self.floorplans[0] if self.floorplans else None


class FakeFloorplanManager:
    def __init__(self, floorplans):
        self.floorplans = list(floorplans)

    def filter(self, **kwargs):
        matches = []
        for floorplan in self.floorplans:
            if all(getattr(floorplan, field_name) == value for field_name, value in kwargs.items()):
                matches.append(floorplan)
        return FakeFloorplanQuerySet(matches)


def make_floorplan_module(*floorplans):
    floorplan_model = type('FakeFloorplanModel', (), {'objects': FakeFloorplanManager(floorplans)})
    return SimpleNamespace(Floorplan=floorplan_model)


def make_floorplan(pk, *, site=None, location=None, canvas=None):
    return SimpleNamespace(
        pk=pk,
        site=site,
        location=location,
        assigned_image=SimpleNamespace(pk=pk + 1000),
        width=Decimal('42.50'),
        height=Decimal('18.25'),
        measurement_unit='m',
        canvas=canvas or {},
        get_absolute_url=lambda: f'/plugins/floorplan/{pk}/',
        __str__=lambda self=None, identifier=pk: f'Floorplan {identifier}',
    )


class FloorplanIntegrationTestCase(SimpleTestCase):
    def setUp(self):
        self.site = SimpleNamespace(pk=11, name='Primary Site')
        self.location = SimpleNamespace(pk=22, name='Hall A', site=self.site)
        self.power_system = SimpleNamespace(pk=33, site=self.site, location=self.location)

    @override_settings(PLUGINS=['netbox_power_plant'])
    def test_reports_unavailable_when_floorplan_module_cannot_be_imported(self):
        with patch('netbox_power_plant.services.floorplan.import_module', side_effect=ModuleNotFoundError('netbox_floorplan')):
            availability = get_floorplan_availability()
            context = get_floorplan_context_for_power_system(self.power_system)

        self.assertFalse(availability.is_available)
        self.assertFalse(availability.is_importable)
        self.assertIn('could not be imported', availability.reason)
        self.assertFalse(context.has_floorplan)
        self.assertFalse(has_floorplan_context(self.power_system))

    @override_settings(PLUGINS=['netbox_power_plant'])
    def test_reports_disabled_when_plugin_is_not_enabled(self):
        floorplan_module = make_floorplan_module()

        with patch('netbox_power_plant.services.floorplan.import_module', return_value=floorplan_module):
            availability = get_floorplan_availability()
            context = get_floorplan_context_for_power_system(self.power_system)

        self.assertTrue(availability.is_importable)
        self.assertFalse(availability.is_available)
        self.assertIn('not enabled', availability.reason)
        self.assertFalse(context.has_floorplan)

    @override_settings(PLUGINS=['netbox_floorplan', 'netbox_power_plant'])
    def test_prefers_location_floorplan_and_normalizes_canvas_mappings(self):
        location_floorplan = make_floorplan(
            101,
            site=self.site,
            location=self.location,
            canvas={
                'objects': [
                    {
                        'type': 'group',
                        'objects': [
                            {
                                'type': 'rect',
                                'left': '10',
                                'top': '15',
                                'custom_meta': {
                                    'object_type': 'rack',
                                    'object_id': '5001',
                                    'object_name': 'Rack-A1',
                                },
                            },
                            {
                                'type': 'rect',
                                'left': 22,
                                'top': 31,
                                'custom_meta': {
                                    'object_type': 'device',
                                    'object_id': '7001',
                                    'object_name': 'PDU-A1',
                                },
                            },
                        ],
                    }
                ]
            },
        )
        site_floorplan = make_floorplan(202, site=self.site)
        floorplan_module = make_floorplan_module(location_floorplan, site_floorplan)

        with patch('netbox_power_plant.services.floorplan.import_module', return_value=floorplan_module):
            context = get_floorplan_context_for_power_system(self.power_system)

        self.assertTrue(context.availability.is_available)
        self.assertTrue(context.has_floorplan)
        self.assertEqual(context.floorplan_id, 101)
        self.assertEqual(context.source_scope, 'location')
        self.assertEqual(context.source_object_id, self.location.pk)
        self.assertEqual(context.floorplan_url, '/plugins/floorplan/101/')
        self.assertEqual(context.width, 42.5)
        self.assertEqual(context.height, 18.25)
        self.assertEqual(len(context.mapped_racks), 1)
        self.assertEqual(context.mapped_racks[0].object_id, 5001)
        self.assertEqual(context.mapped_racks[0].object_name, 'Rack-A1')
        self.assertEqual(context.mapped_devices[0].object_id, 7001)
        self.assertEqual(context.mapped_devices[0].x, 22.0)
        self.assertEqual(list_mapped_racks(self.power_system)[0].object_id, 5001)
        self.assertEqual(list_mapped_devices(self.power_system)[0].object_id, 7001)

    @override_settings(PLUGINS=['netbox_floorplan', 'netbox_power_plant'])
    def test_falls_back_to_site_floorplan_when_location_floorplan_is_missing(self):
        site_floorplan = make_floorplan(303, site=self.site)
        floorplan_module = make_floorplan_module(site_floorplan)

        with patch('netbox_power_plant.services.floorplan.import_module', return_value=floorplan_module):
            context = get_floorplan_context_for_power_system(self.power_system)

        self.assertTrue(context.has_floorplan)
        self.assertEqual(context.floorplan_id, 303)
        self.assertEqual(context.source_scope, 'site')
        self.assertEqual(context.source_object_id, self.site.pk)