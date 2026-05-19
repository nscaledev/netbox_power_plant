from netbox.plugins.templates import PluginTemplateExtension

from .models import InternalPowerBusAttachment, RackDeliveryPoint


class PowerPortPowerPlantContext(PluginTemplateExtension):
    models = ['dcim.powerport']

    def right_page(self):
        power_port = self.context['object']
        delivery_points = tuple(
            RackDeliveryPoint.objects.filter(power_port=power_port)
            .select_related('power_system', 'electrical_node', 'electrical_terminal', 'expected_redundancy_group')
            .order_by('power_system__name', 'name')
        )
        bus_attachments = tuple(
            InternalPowerBusAttachment.objects.filter(power_port=power_port)
            .select_related('internal_power_bus', 'internal_power_bus__power_system', 'internal_power_bus__rack')
            .order_by('internal_power_bus__name', 'attachment_role', 'position_index', 'name')
        )

        return self.render(
            'netbox_power_plant/includes/power_port_power_plant.html',
            extra_context={
                'power_port': power_port,
                'delivery_points': delivery_points,
                'bus_attachments': bus_attachments,
                'has_power_plant_paths': bool(delivery_points or bus_attachments),
            },
        )


template_extensions = [PowerPortPowerPlantContext]
