from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from utilities.testing import TestCase as UITestCase

from dcim.models import Location, Rack, Site

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices, RedundancyTopologyChoices, SupplyTypeChoices, TerminalDirectionChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, ElectricalSegment, ElectricalTerminal, PowerDomain, PowerSystem, RackDeliveryPoint, RedundancyGroup
from netbox_power_plant.services.layout_validation import build_layout_health_summary, run_layout_checks


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
        cls.unmapped_delivery_point = RackDeliveryPoint.objects.create(
            name='Rack B Delivery',
            slug='rack-b-delivery',
            power_system=cls.power_system,
            electrical_node=cls.boundary_node,
            electrical_terminal=cls.boundary_terminal,
            rack=cls.unmapped_rack,
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

    @override_settings(PLUGINS=['netbox_floorplan', 'netbox_power_plant'])
    def test_reports_missing_floorplan_context_when_plugin_is_available_but_no_floorplan_resolves(self):
        with patch('netbox_power_plant.services.floorplan.import_module', return_value=make_floorplan_module()):
            findings = run_layout_checks(self.power_system)

        self.assertIn('missing_floorplan_context', {finding.finding_type for finding in findings})

    @override_settings(PLUGINS=['netbox_floorplan', 'netbox_power_plant'])
    def test_reports_layout_mapping_and_redundancy_findings(self):
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
                    },
                    {
                        'type': 'rect',
                        'left': '35',
                        'top': '45',
                        'custom_meta': {
                            'object_type': 'rack',
                            'object_id': str(self.orphan_rack.pk),
                            'object_name': self.orphan_rack.name,
                        },
                    },
                ]
            },
        ))

        with patch('netbox_power_plant.services.floorplan.import_module', return_value=floorplan_module):
            summary = build_layout_health_summary(self.power_system)

        finding_types = {finding.finding_type for finding in summary.findings}
        self.assertIn('unmapped_rack_delivery_point', finding_types)
        self.assertIn('orphan_floorplan_mapping', finding_types)
        self.assertIn('redundancy_gap_visible_in_layout', finding_types)
        self.assertIn('mis_scoped_node_placement', finding_types)
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
        'netbox_power_plant.view_rackdeliverypoint',
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
        rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        RackDeliveryPoint.objects.create(
            name='Rack A Delivery',
            slug='rack-a-delivery',
            power_system=cls.power_system,
            electrical_node=boundary_node,
            electrical_terminal=boundary_terminal,
            rack=rack,
            expected_redundancy_group=redundancy_group,
            feed_label='A-feed',
        )

    def test_power_system_detail_renders_layout_health_summary(self):
        plugins = list(getattr(settings, 'PLUGINS', ()))
        if 'netbox_floorplan' not in plugins:
            plugins.append('netbox_floorplan')

        with override_settings(PLUGINS=plugins):
            with patch('netbox_power_plant.services.floorplan.import_module', return_value=make_floorplan_module()):
                response = self.client.get(reverse('plugins:netbox_power_plant:powersystem', kwargs={'pk': self.power_system.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Layout Health')
        self.assertContains(response, 'Needs attention')
        self.assertContains(response, 'No site or location floorplan is resolved for this power system.')