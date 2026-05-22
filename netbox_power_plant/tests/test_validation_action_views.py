from django.urls import reverse
from utilities.testing import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import PowerValidationRunKindChoices
from netbox_power_plant.models import PowerSystem, PowerValidationRun


class ValidationActionViewTestCase(TestCase):
    user_permissions = (
        'netbox_power_plant.view_powersystem',
        'netbox_power_plant.add_powervalidationrun',
        'netbox_power_plant.view_powervalidationrun',
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

    def test_power_system_detail_exposes_validation_actions(self):
        response = self.client.get(reverse('plugins:netbox_power_plant:powersystem', kwargs={'pk': self.power_system.pk}))

        self.assertHttpStatus(response, 200)
        self.assertContains(response, 'Run topology validation')
        self.assertContains(
            response,
            reverse(
                'plugins:netbox_power_plant:powersystem_validation_action',
                kwargs={'pk': self.power_system.pk, 'run_kind': PowerValidationRunKindChoices.KIND_TOPOLOGY},
            ),
        )

    def test_posting_validation_action_persists_run_and_redirects_to_it(self):
        response = self.client.post(
            reverse(
                'plugins:netbox_power_plant:powersystem_validation_action',
                kwargs={'pk': self.power_system.pk, 'run_kind': PowerValidationRunKindChoices.KIND_TOPOLOGY},
            ),
        )

        run = PowerValidationRun.objects.get()
        self.assertHttpStatus(response, 302)
        self.assertEqual(response['Location'], run.get_absolute_url())
        self.assertEqual(run.run_kind, PowerValidationRunKindChoices.KIND_TOPOLOGY)
