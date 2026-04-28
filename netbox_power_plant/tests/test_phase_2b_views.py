from django.urls import reverse

from dcim.models import Location, Site
from utilities.testing import TestCase
from utilities.testing.utils import post_data

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, PowerSystem


class Phase2BViewTestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_electricalnode',
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
        cls.node = ElectricalNode.objects.create(
            name='Row PDU A',
            slug='row-pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.secondary_node = ElectricalNode.objects.create(
            name='Row PDU B',
            slug='row-pdu-b',
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

    def test_electrical_node_placement_detail_page_renders(self):
        response = self.client.get(
            reverse('plugins:netbox_power_plant:electricalnodeplacement', kwargs={'pk': self.placement.pk})
        )

        self.assertHttpStatus(response, 200)
        self.assertContains(response, self.placement.name)
        self.assertContains(response, self.node.name)
        self.assertContains(response, 'Electrical Node Placement Details')

    def test_electrical_node_placement_add_view_accepts_minimal_post(self):
        self.add_permissions('netbox_power_plant.add_electricalnodeplacement')
        response = self.client.post(
            reverse('plugins:netbox_power_plant:electricalnodeplacement_add'),
            post_data({
                'name': 'UPS Placement',
                'slug': 'ups-placement',
                'power_system': self.power_system,
                'electrical_node': self.secondary_node,
                'site': self.site,
                'location': self.location,
                'placement_scope_type': PlacementScopeChoices.SCOPE_LOCATION,
                'x': '55.00',
                'y': '65.00',
                'width': '',
                'height': '',
                'rotation_degrees': '0.00',
                'symbol_kind': 'distribution',
                'label_mode': 'name',
                'color': '',
                'z_index': '120',
                'description': '',
                'comments': '',
            }),
        )

        self.assertHttpStatus(response, 302)
        self.assertTrue(ElectricalNodePlacement.objects.filter(slug='ups-placement').exists())