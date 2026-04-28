from decimal import Decimal

from django.urls import reverse

from dcim.models import Location, Site
from utilities.testing import APITestCase

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, PowerSystem


class Phase2BAPITestCase(APITestCase):
    view_namespace = 'plugins-api:netbox_power_plant'

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
        cls.placement = ElectricalNodePlacement.objects.create(
            name='Row PDU Placement',
            slug='row-pdu-placement',
            power_system=cls.power_system,
            electrical_node=cls.node,
            site=cls.site,
            location=cls.location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='12.50',
            y='34.00',
            symbol_kind='distribution',
        )

    def test_api_root_includes_node_placement_endpoint(self):
        response = self.client.get(reverse('plugins-api:netbox_power_plant-api:api-root'), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('electrical-node-placements', response.data)

    def test_node_placement_detail_includes_scope_and_coordinates(self):
        self.add_permissions('netbox_power_plant.view_electricalnodeplacement')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:electricalnodeplacement-detail', kwargs={'pk': self.placement.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.placement.name)
        self.assertEqual(response.data['electrical_node']['name'], self.node.name)
        self.assertEqual(response.data['site']['name'], self.site.name)
        self.assertEqual(response.data['location']['name'], self.location.name)
        self.assertEqual(response.data['placement_scope_type']['value'], PlacementScopeChoices.SCOPE_LOCATION)
        self.assertEqual(response.data['x'], Decimal('12.50'))
        self.assertEqual(response.data['y'], Decimal('34.00'))