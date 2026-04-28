from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from utilities.testing import TestCase

from dcim.models import Location, Rack, Site

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices, SupplyTypeChoices, TerminalDirectionChoices
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    PowerDomain,
    PowerSystem,
    RackDeliveryPoint,
)
from netbox_power_plant.services.workflow_urls import build_delivery_edit_url, build_placement_edit_url


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


class FakeFloorplan(SimpleNamespace):
    def __str__(self):
        return f'Floorplan {self.pk}'


def make_floorplan_module(*floorplans):
    floorplan_model = type('FakeFloorplanModel', (), {'objects': FakeFloorplanManager(floorplans)})
    return SimpleNamespace(Floorplan=floorplan_model)


def make_floorplan(pk, *, site=None, location=None, canvas=None):
    return FakeFloorplan(
        pk=pk,
        site=site,
        location=location,
        assigned_image=SimpleNamespace(pk=pk + 1000),
        width=Decimal('42.50'),
        height=Decimal('18.25'),
        measurement_unit='m',
        canvas=canvas or {},
        get_absolute_url=lambda: f'/plugins/floorplan/{pk}/',
    )


class Phase5WorkflowViewTestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_powerdomain',
        'netbox_power_plant.view_electricalnode',
        'netbox_power_plant.view_electricalterminal',
        'netbox_power_plant.view_electricalsegment',
        'netbox_power_plant.view_rackdeliverypoint',
        'netbox_power_plant.view_electricalnodeplacement',
        'netbox_power_plant.add_rackdeliverypoint',
        'netbox_power_plant.add_electricalnodeplacement',
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
        cls.domain_a = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        cls.source_node = ElectricalNode.objects.create(
            name='Primary UPS',
            slug='primary-ups',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
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
        cls.source_terminal = ElectricalTerminal.objects.create(
            name='Output A',
            slug='output-a',
            node=cls.source_node,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        cls.boundary_terminal = ElectricalTerminal.objects.create(
            name='Rack Input A',
            slug='rack-input-a',
            node=cls.boundary_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        cls.modeled_boundary_node = ElectricalNode.objects.create(
            name='Rack Boundary B',
            slug='rack-boundary-b',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            topology_state='active',
        )
        cls.modeled_boundary_terminal = ElectricalTerminal.objects.create(
            name='Rack Input B',
            slug='rack-input-b',
            node=cls.modeled_boundary_node,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )
        ElectricalSegment.objects.create(
            name='UPS to Rack Feed',
            slug='ups-to-rack-feed',
            power_system=cls.power_system,
            power_domain=cls.domain_a,
            from_terminal=cls.source_terminal,
            to_terminal=cls.boundary_terminal,
            segment_kind='rack_feed',
            path_state='active',
        )
        ElectricalSegment.objects.create(
            name='UPS to Rack Feed B',
            slug='ups-to-rack-feed-b',
            power_system=cls.power_system,
            power_domain=cls.domain_a,
            from_terminal=cls.source_terminal,
            to_terminal=cls.modeled_boundary_terminal,
            segment_kind='rack_feed',
            path_state='active',
        )
        cls.placement = ElectricalNodePlacement.objects.create(
            name='Primary UPS Placement',
            slug='primary-ups-placement',
            power_system=cls.power_system,
            electrical_node=cls.source_node,
            site=cls.site,
            location=cls.location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='12.50',
            y='8.25',
            symbol_kind='source',
        )
        cls.rack = Rack.objects.create(name='Rack B1', site=cls.site, location=cls.location)
        cls.delivery_point = RackDeliveryPoint.objects.create(
            name='Rack B Delivery',
            slug='rack-b-delivery',
            power_system=cls.power_system,
            electrical_node=cls.modeled_boundary_node,
            electrical_terminal=cls.modeled_boundary_terminal,
            rack=cls.rack,
            feed_label='B-feed',
        )

    def test_power_system_detail_context_exposes_scoped_workflow_urls(self):
        response = self.client.get(reverse('plugins:netbox_power_plant:powersystem', kwargs={'pk': self.power_system.pk}))

        self.assertHttpStatus(response, 200)

        layout_url = reverse('plugins:netbox_power_plant:powersystem_layout', kwargs={'pk': self.power_system.pk})
        rack_delivery_url = reverse('plugins:netbox_power_plant:powersystem_rack_delivery', kwargs={'pk': self.power_system.pk})
        expected_placement_add = '{}?{}'.format(
            reverse('plugins:netbox_power_plant:electricalnodeplacement_add'),
            urlencode({
                'power_system': self.power_system.pk,
                'site': self.site.pk,
                'location': self.location.pk,
                'placement_scope_type': PlacementScopeChoices.SCOPE_LOCATION,
                'return_url': layout_url,
            }),
        )
        expected_delivery_add = '{}?{}'.format(
            reverse('plugins:netbox_power_plant:rackdeliverypoint_add'),
            urlencode({
                'power_system': self.power_system.pk,
                'return_url': rack_delivery_url,
            }),
        )

        self.assertEqual(response.context['workflow_urls']['layout'], layout_url)
        self.assertEqual(response.context['workflow_urls']['rack_delivery'], rack_delivery_url)
        self.assertEqual(response.context['workflow_urls']['placement_add'], expected_placement_add)
        self.assertEqual(response.context['workflow_urls']['delivery_add'], expected_delivery_add)

    def test_scoped_placement_add_form_prefills_power_system_scope(self):
        layout_url = reverse('plugins:netbox_power_plant:powersystem_layout', kwargs={'pk': self.power_system.pk})
        placement_add_url = '{}?{}'.format(
            reverse('plugins:netbox_power_plant:electricalnodeplacement_add'),
            urlencode({
                'power_system': self.power_system.pk,
                'site': self.site.pk,
                'location': self.location.pk,
                'placement_scope_type': PlacementScopeChoices.SCOPE_LOCATION,
                'return_url': layout_url,
            }),
        )

        response = self.client.get(placement_add_url)

        self.assertHttpStatus(response, 200)
        self.assertEqual(str(response.context['form']['power_system'].value()), str(self.power_system.pk))
        self.assertEqual(str(response.context['form']['site'].value()), str(self.site.pk))
        self.assertEqual(str(response.context['form']['location'].value()), str(self.location.pk))
        self.assertEqual(response.context['form']['placement_scope_type'].value(), PlacementScopeChoices.SCOPE_LOCATION)
        self.assertEqual(response.context['return_url'], layout_url)

    def test_layout_view_exposes_inferred_delivery_workflow_and_prefills_add_form(self):
        plugins = list(getattr(settings, 'PLUGINS', ()))
        if 'netbox_floorplan' not in plugins:
            plugins.append('netbox_floorplan')

        layout_url = reverse('plugins:netbox_power_plant:powersystem_layout', kwargs={'pk': self.power_system.pk})
        create_url = '{}?{}'.format(
            reverse('plugins:netbox_power_plant:rackdeliverypoint_add'),
            urlencode({
                'power_system': self.power_system.pk,
                'electrical_node': self.boundary_node.pk,
                'electrical_terminal': self.boundary_terminal.pk,
                'return_url': layout_url,
            }),
        )

        with override_settings(PLUGINS=plugins):
            with patch(
                'netbox_power_plant.services.floorplan.import_module',
                return_value=make_floorplan_module(make_floorplan(101, site=self.site, location=self.location)),
            ):
                response = self.client.get(layout_url)

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Model delivery point')
        self.assertEqual(len(response.context['inferred_delivery_actions']), 1)
        self.assertEqual(response.context['inferred_delivery_actions'][0].create_url, create_url)

        response = self.client.get(create_url)

        self.assertHttpStatus(response, 200)
        self.assertEqual(str(response.context['form']['power_system'].value()), str(self.power_system.pk))
        self.assertEqual(str(response.context['form']['electrical_node'].value()), str(self.boundary_node.pk))
        self.assertEqual(str(response.context['form']['electrical_terminal'].value()), str(self.boundary_terminal.pk))
        self.assertEqual(response.context['return_url'], layout_url)

    def test_layout_view_exposes_scoped_edit_workflows_for_existing_objects(self):
        self.add_permissions(
            'netbox_power_plant.change_electricalnodeplacement',
            'netbox_power_plant.change_rackdeliverypoint',
        )
        plugins = list(getattr(settings, 'PLUGINS', ()))
        if 'netbox_floorplan' not in plugins:
            plugins.append('netbox_floorplan')

        layout_url = reverse('plugins:netbox_power_plant:powersystem_layout', kwargs={'pk': self.power_system.pk})
        expected_placement_edit_url = build_placement_edit_url(self.placement, return_url=layout_url)
        expected_delivery_edit_url = build_delivery_edit_url(self.delivery_point, return_url=layout_url)

        with override_settings(PLUGINS=plugins):
            with patch(
                'netbox_power_plant.services.floorplan.import_module',
                return_value=make_floorplan_module(make_floorplan(101, site=self.site, location=self.location)),
            ):
                response = self.client.get(layout_url)

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Edit placement')
        self.assertContains(response, 'Edit delivery point')
        self.assertEqual(response.context['placement_actions'][0].edit_url, expected_placement_edit_url)
        self.assertEqual(response.context['delivery_overlay_actions'][0].edit_url, expected_delivery_edit_url)

        response = self.client.get(expected_placement_edit_url)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.context['return_url'], layout_url)
        self.assertEqual(response.context['object'].pk, self.placement.pk)

        response = self.client.get(expected_delivery_edit_url)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.context['return_url'], layout_url)
        self.assertEqual(response.context['object'].pk, self.delivery_point.pk)

    def test_rack_delivery_summary_table_exposes_modeled_and_inferred_workflows(self):
        self.add_permissions('netbox_power_plant.change_rackdeliverypoint')
        rack_delivery_url = reverse('plugins:netbox_power_plant:powersystem_rack_delivery', kwargs={'pk': self.power_system.pk})
        expected_delivery_edit_url = build_delivery_edit_url(self.delivery_point, return_url=rack_delivery_url)
        expected_inferred_add_url = '{}?{}'.format(
            reverse('plugins:netbox_power_plant:rackdeliverypoint_add'),
            urlencode({
                'power_system': self.power_system.pk,
                'electrical_node': self.boundary_node.pk,
                'electrical_terminal': self.boundary_terminal.pk,
                'return_url': rack_delivery_url,
            }),
        )

        response = self.client.get(rack_delivery_url)

        self.assertHttpStatus(response, 200)
        self.assertContains(response, expected_delivery_edit_url)
        self.assertContains(response, expected_inferred_add_url.replace('&', '&amp;'))