from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

from netbox_power_plant import PowerPlantConfig


class PluginConfigTestCase(SimpleTestCase):
    def test_plugin_config_metadata_matches_repo_contract(self):
        self.assertEqual(PowerPlantConfig.name, 'netbox_power_plant')
        self.assertEqual(PowerPlantConfig.base_url, 'power-plant')
        self.assertEqual(PowerPlantConfig.min_version, '4.5.0')
        self.assertEqual(PowerPlantConfig.max_version, '4.5.99')

    def test_test_configuration_enables_plugin(self):
        self.assertIn('netbox_power_plant', settings.PLUGINS)

    def test_plugin_home_route_is_registered(self):
        self.assertEqual(reverse('plugins:netbox_power_plant:home'), '/plugins/power-plant/')
