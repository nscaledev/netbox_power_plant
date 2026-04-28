from django.urls import reverse

from dcim.models import Location, Site
from utilities.testing import TestCase
from utilities.testing.utils import post_data

from netbox_power_plant.models import PowerDomain, PowerSystem, RedundancyGroup


class Phase1AViewTestCase(TestCase):
    user_permissions = (
        'dcim.view_site',
        'dcim.view_location',
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.view_powerdomain',
        'netbox_power_plant.view_redundancygroup',
    )

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

    def test_overview_page_renders(self):
        response = self.client.get(reverse('plugins:netbox_power_plant:home'))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Power Plant Overview')
        self.assertContains(response, self.power_system.name)

    def test_object_detail_pages_render(self):
        for url_name, expected_text in (
            ('plugins:netbox_power_plant:powersystem', self.power_system.name),
            ('plugins:netbox_power_plant:powerdomain', self.power_domain.name),
            ('plugins:netbox_power_plant:redundancygroup', self.redundancy_group.name),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name, kwargs={'pk': self._resolve_pk(url_name)}))
                self.assertHttpStatus(response, 200)
                self.assertContains(response, expected_text)

    def test_power_system_add_view_accepts_minimal_post(self):
        self.add_permissions('netbox_power_plant.add_powersystem')
        form_data = {
            'name': 'Secondary Hall Power',
            'slug': 'secondary-hall-power',
            'site': self.site,
            'location': self.location,
            'scope_type': 'hall',
            'upstream_supply_type': 'ac',
            'design_state': 'planned',
            'nominal_distribution_voltage': 415,
            'frequency_hz': 60,
            'is_template_derived': False,
            'description': '',
            'comments': '',
        }
        response = self.client.post(
            reverse('plugins:netbox_power_plant:powersystem_add'),
            post_data(form_data),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PowerSystem.objects.filter(slug='secondary-hall-power').exists())

    def _resolve_pk(self, url_name):
        if url_name.endswith('powersystem'):
            return self.power_system.pk
        if url_name.endswith('powerdomain'):
            return self.power_domain.pk
        return self.redundancy_group.pk