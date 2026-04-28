from urllib.parse import urlencode

from django.urls import reverse

from netbox_power_plant.choices import PlacementScopeChoices


def build_query_url(viewname, *, kwargs=None, **params):
    query = {
        key: value
        for key, value in params.items()
        if value not in (None, '')
    }
    base_url = reverse(viewname, kwargs=kwargs)
    if not query:
        return base_url
    return f'{base_url}?{urlencode(query)}'


def build_layout_url(power_system):
    return reverse('plugins:netbox_power_plant:powersystem_layout', kwargs={'pk': power_system.pk})


def build_rack_delivery_url(power_system):
    return reverse('plugins:netbox_power_plant:powersystem_rack_delivery', kwargs={'pk': power_system.pk})


def default_placement_scope_type(power_system):
    if power_system.location_id:
        return PlacementScopeChoices.SCOPE_LOCATION
    return PlacementScopeChoices.SCOPE_SITE


def build_placement_add_url(power_system, *, return_url):
    return build_query_url(
        'plugins:netbox_power_plant:electricalnodeplacement_add',
        power_system=power_system.pk,
        site=power_system.site_id,
        location=power_system.location_id,
        placement_scope_type=default_placement_scope_type(power_system),
        return_url=return_url,
    )


def build_placement_edit_url(placement, *, return_url):
    return build_query_url(
        'plugins:netbox_power_plant:electricalnodeplacement_edit',
        kwargs={'pk': placement.pk},
        return_url=return_url,
    )


def build_delivery_add_url(power_system, *, return_url, electrical_node_id=None, electrical_terminal_id=None):
    return build_query_url(
        'plugins:netbox_power_plant:rackdeliverypoint_add',
        power_system=power_system.pk,
        electrical_node=electrical_node_id,
        electrical_terminal=electrical_terminal_id,
        return_url=return_url,
    )


def build_delivery_edit_url(delivery_point, *, return_url):
    return build_query_url(
        'plugins:netbox_power_plant:rackdeliverypoint_edit',
        kwargs={'pk': delivery_point.pk},
        return_url=return_url,
    )


def build_workflow_urls(power_system, *, placement_return_url, delivery_return_url):
    return {
        'layout': build_layout_url(power_system),
        'rack_delivery': build_rack_delivery_url(power_system),
        'placement_add': build_placement_add_url(power_system, return_url=placement_return_url),
        'delivery_add': build_delivery_add_url(power_system, return_url=delivery_return_url),
    }