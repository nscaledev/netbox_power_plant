from netbox.plugins import PluginMenuButton, PluginMenuItem


menu_items = (
    PluginMenuItem(
        link='plugins:netbox_power_plant:home',
        link_text='System Overview',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:powersystem_list',
        link_text='Power Systems',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:powersystem_add',
                title='Add power system',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:powerdomain_list',
        link_text='Power Domains',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:powerdomain_add',
                title='Add power domain',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:redundancygroup_list',
        link_text='Redundancy Groups',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:redundancygroup_add',
                title='Add redundancy group',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:electricalnode_list',
        link_text='Electrical Nodes',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:electricalnode_add',
                title='Add electrical node',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:electricalterminal_list',
        link_text='Electrical Terminals',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:electricalterminal_add',
                title='Add electrical terminal',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:electricalsegment_list',
        link_text='Electrical Segments',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:electricalsegment_add',
                title='Add electrical segment',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:rackdeliverypoint_list',
        link_text='Rack Delivery Points',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:rackdeliverypoint_add',
                title='Add rack delivery point',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:internalpowerbus_list',
        link_text='Internal Power Buses',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:internalpowerbus_add',
                title='Add internal power bus',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:internalpowerbusattachment_list',
        link_text='Bus Power Port Attachments',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:internalpowerbusattachment_add',
                title='Add bus power port attachment',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:electricalnodeplacement_list',
        link_text='Electrical Node Placements',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:electricalnodeplacement_add',
                title='Add electrical node placement',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
)
