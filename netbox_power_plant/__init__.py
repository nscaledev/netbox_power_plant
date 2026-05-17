from importlib.metadata import PackageNotFoundError, version

from netbox.plugins import PluginConfig


try:
    __version__ = version('netbox_power_plant')
except PackageNotFoundError:
    __version__ = '0+unknown'


class PowerPlantConfig(PluginConfig):
    name = 'netbox_power_plant'
    verbose_name = 'NetBox Power Plant'
    description = 'Facility-side electrical plant modeling for NetBox.'
    version = __version__
    author = 'Mencken Davidson'
    author_email = 'mencken@gmail.com'
    base_url = 'power-plant'
    min_version = '4.2.0'
    max_version = '4.2.99'
    required_settings = []
    default_settings = {
        'top_level_menu': True,
    }


config = PowerPlantConfig
