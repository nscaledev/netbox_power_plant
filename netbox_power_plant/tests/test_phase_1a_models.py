from django.core.exceptions import ValidationError
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import PowerDomainKindChoices, RedundancyTopologyChoices
from netbox_power_plant.models import PowerDomain, PowerSystem, RedundancyGroup


class Phase1AModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.other_site = Site.objects.create(name='Other Site', slug='other-site')
        cls.location = Location.objects.create(site=cls.site, name='Hall A', slug='hall-a')
        cls.other_location = Location.objects.create(site=cls.other_site, name='Hall B', slug='hall-b')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )

    def test_power_system_rejects_location_from_another_site(self):
        power_system = PowerSystem(
            name='Invalid System',
            slug='invalid-system',
            site=self.site,
            location=self.other_location,
        )

        with self.assertRaises(ValidationError):
            power_system.full_clean()

    def test_power_domain_code_is_unique_within_a_power_system(self):
        PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=self.power_system,
            code='A',
            kind=PowerDomainKindChoices.KIND_PRIMARY,
        )
        duplicate = PowerDomain(
            name='Domain A Duplicate',
            slug='domain-a-duplicate',
            power_system=self.power_system,
            code='A',
            kind=PowerDomainKindChoices.KIND_REDUNDANT,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_redundancy_group_tracks_power_domains(self):
        domain_a = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=self.power_system,
            code='A',
        )
        domain_b = PowerDomain.objects.create(
            name='Domain B',
            slug='domain-b',
            power_system=self.power_system,
            code='B',
        )
        redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=self.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        redundancy_group.power_domains.set([domain_a, domain_b])

        self.assertQuerySetEqual(
            redundancy_group.power_domains.order_by('code'),
            PowerDomain.objects.filter(pk__in=[domain_a.pk, domain_b.pk]).order_by('code'),
            transform=lambda domain: domain,
        )