from importlib.metadata import PackageNotFoundError, version

try:
    from netbox.plugins import PluginConfig
except ModuleNotFoundError:
    PluginConfig = object
    _NETBOX_AVAILABLE = False
else:
    _NETBOX_AVAILABLE = True


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
    template_extensions = 'template_extensions.template_extensions'

    def ready(self):
        if not _NETBOX_AVAILABLE:
            return
        super().ready()
        self._extend_power_component_type_choices()
        # Register optional cross-plugin cache invalidation hooks. The service
        # degrades to no-op behavior when netbox_multiplanar_fabrics is absent.
        from netbox_power_plant.services import cross_plugin  # noqa: F401

    def _extend_power_component_type_choices(self):
        # NetBox 4.2 exposes these connector types as static ChoiceSets without
        # FIELD_CHOICES keys. Extend them at plugin startup so Madison can model
        # power-port-only handoffs without flattening them into less-specific
        # stock types.
        from dcim.choices import PowerPortTypeChoices
        from dcim.models import PowerPort, PowerPortTemplate
        from utilities.choices import unpack_grouped_choices

        power_port_extensions = (
            ('TYPE_NVL72_BUSBAR', 'nvl72-busbar', 'NVL72 busbar', 'NVIDIA'),
            (
                'TYPE_IEC_60309_560P6',
                'iec-60309-560p6',
                'IEC 60309 60A 3P+N+PE (560P6)',
                'APC / Schneider Electric',
            ),
        )

        for constant, value, label, group in power_port_extensions:
            self._append_choice(PowerPortTypeChoices, constant, value, label, group, unpack_grouped_choices)
            self._append_field_choice((PowerPort, PowerPortTemplate), value, label, group, unpack_grouped_choices)

    def _append_choice(self, choice_set, constant, value, label, group, unpack_grouped_choices):
        setattr(choice_set, constant, value)
        if value in {choice for choice, _ in unpack_grouped_choices(choice_set._choices)}:
            return
        choice_set.CHOICES = tuple(choice_set.CHOICES) + (
            (group, ((value, label),)),
        )
        choice_set._choices = tuple(choice_set._choices) + (
            (group, [(value, label)]),
        )

    def _append_field_choice(self, models, value, label, group, unpack_grouped_choices):
        for model in models:
            field = model._meta.get_field('type')
            if value in {choice for choice, _ in unpack_grouped_choices(field.choices)}:
                continue
            field.choices = tuple(field.choices) + (
                (group, ((value, label),)),
            )


config = PowerPlantConfig
