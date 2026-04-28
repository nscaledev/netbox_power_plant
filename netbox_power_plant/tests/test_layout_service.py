from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from dcim.models import Location, Rack, Site

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices, RedundancyTopologyChoices, SupplyTypeChoices, TerminalDirectionChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, ElectricalSegment, ElectricalTerminal, PowerDomain, PowerSystem, RackDeliveryPoint, RedundancyGroup
from netbox_power_plant.services.layout import build_power_system_layout_view


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
        cls.delivery_point = RackDeliveryPoint.objects.create(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=cls.power_system,
            electrical_node=cls.boundary_node,
            electrical_terminal=cls.boundary_terminal,
            rack=cls.rack,
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

    @override_settings(PLUGINS=['netbox_power_plant'])
    def test_returns_unavailable_layout_state_when_floorplan_plugin_is_disabled(self):
        layout = build_power_system_layout_view(self.power_system)

        self.assertFalse(layout.has_floorplan)
        self.assertIsNotNone(layout.floorplan_context.availability.reason)
        self.assertIn('floorplan plugin', layout.floorplan_context.availability.reason.lower())
        self.assertEqual(len(layout.placements), 1)

    @override_settings(PLUGINS=['netbox_floorplan', 'netbox_power_plant'])
    def test_builds_layout_from_floorplan_context_placements_and_delivery_points(self):
        floorplan_module = make_floorplan_module(make_floorplan(
            101,
            site=self.site,
            location=self.location,
            canvas={
                'objects': [
                    {
                        'type': 'rect',
                        'left': '15',
                        'top': '25',
                        'custom_meta': {
                            'object_type': 'rack',
                            'object_id': str(self.rack.pk),
                            'object_name': self.rack.name,
                        },
                    }
                ]
            },
        ))

        with patch('netbox_power_plant.services.floorplan.import_module', return_value=floorplan_module):
            layout = build_power_system_layout_view(self.power_system)

        self.assertTrue(layout.has_floorplan)
        self.assertEqual(layout.floorplan_context.floorplan_id, 101)
        self.assertEqual(len(layout.placements), 1)
        self.assertEqual(layout.placements[0].placement.pk, self.placement.pk)
        self.assertEqual(len(layout.delivery_overlays), 1)
        self.assertTrue(layout.delivery_overlays[0].is_mapped_on_floorplan)
        self.assertEqual(layout.delivery_overlays[0].target_name, self.rack.name)
        self.assertEqual(layout.mapped_delivery_count, 1)
        self.assertEqual(len(layout.mapped_assets), 1)
        self.assertEqual(layout.mapped_assets[0].matched_delivery_points[0].pk, self.delivery_point.pk)