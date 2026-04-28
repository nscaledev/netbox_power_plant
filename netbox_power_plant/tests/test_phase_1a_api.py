from django.urls import reverse

from dcim.models import Location, Site
from utilities.testing import APITestCase

from netbox_power_plant.models import PowerDomain, PowerSystem, RedundancyGroup


class Phase1AAPITestCase(APITestCase):
    view_namespace = 'plugins-api:netbox_power_plant'

    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Hall A', slug='hall-a')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.power_domain = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        cls.redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=cls.power_system,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        cls.redundancy_group.power_domains.add(cls.power_domain)

    def test_api_root_renders(self):
        response = self.client.get(reverse('plugins-api:netbox_power_plant-api:api-root'), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertIn('power-domains', response.data)
        self.assertIn('power-systems', response.data)
        self.assertIn('redundancy-groups', response.data)

    def test_power_system_list_endpoint_returns_objects(self):
        self.add_permissions('netbox_power_plant.view_powersystem')
        response = self.client.get(reverse('plugins-api:netbox_power_plant-api:powersystem-list'), **self.header)

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], self.power_system.name)

    def test_redundancy_group_detail_includes_power_domains(self):
        self.add_permissions('netbox_power_plant.view_redundancygroup')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:redundancygroup-detail', kwargs={'pk': self.redundancy_group.pk}),
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['name'], self.redundancy_group.name)
        self.assertEqual(len(response.data['power_domains']), 1)
        self.assertEqual(response.data['power_domains'][0]['code'], self.power_domain.code)