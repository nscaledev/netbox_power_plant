from netbox.plugins import PluginMenuButton, PluginMenuItem


menu_items = (
    PluginMenuItem(
        link='plugins:netbox_power_plant:home',
        link_text='System Overview',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:operator_dashboard',
        link_text='Operator Center',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:neocloud_cockpit',
        link_text='Neocloud Cockpit',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:template_workflow',
        link_text='Template Workflow',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:madison_underlay_review',
        link_text='Madison Underlay Review',
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
        link='plugins:netbox_power_plant:powervalidationrun_list',
        link_text='Validation Runs',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:powervalidationrun_add',
                title='Add validation run',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:powerfinding_list',
        link_text='Power Findings',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:powerfinding_add',
                title='Add power finding',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:powerarchitecturetemplate_list',
        link_text='Architecture Templates',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:instantiationrun_list',
        link_text='Instantiation Runs',
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:capacityreservation_list',
        link_text='Capacity Reservations',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:capacityreservation_add',
                title='Add capacity reservation',
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
        link='plugins:netbox_power_plant:upsdetail_list',
        link_text='UPS Details',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:upsdetail_add',
                title='Add UPS detail',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:generatordetail_list',
        link_text='Generator Details',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:generatordetail_add',
                title='Add generator detail',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:transformerdetail_list',
        link_text='Transformer Details',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:transformerdetail_add',
                title='Add transformer detail',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:bessdetail_list',
        link_text='BESS Details',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:bessdetail_add',
                title='Add BESS detail',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:buswaysectiondetail_list',
        link_text='Busway Section Details',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:buswaysectiondetail_add',
                title='Add busway section detail',
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
        link='plugins:netbox_power_plant:powerhandoffpoint_list',
        link_text='Power Handoff Points',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:powerhandoffpoint_add',
                title='Add power handoff point',
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
        link='plugins:netbox_power_plant:plantsourcedocument_list',
        link_text='Plant Source Documents',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:plantsourcedocument_add',
                title='Add plant source document',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:plantsourcesheet_list',
        link_text='Plant Source Sheets',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:plantsourcesheet_add',
                title='Add plant source sheet',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:plantsourcelayer_list',
        link_text='Plant Source Layers',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:plantsourcelayer_add',
                title='Add plant source layer',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:plantprovenance_list',
        link_text='Plant Provenance',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:plantprovenance_add',
                title='Add plant provenance record',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:spatialframe_list',
        link_text='Spatial Frames',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:spatialframe_add',
                title='Add spatial frame',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:spatialplacement_list',
        link_text='Spatial Placements',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:spatialplacement_add',
                title='Add spatial placement',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:physicalspace_list',
        link_text='Physical Spaces',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:physicalspace_add',
                title='Add physical space',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:physicalelementtype_list',
        link_text='Physical Element Types',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:physicalelementtype_add',
                title='Add physical element type',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:physicalelement_list',
        link_text='Physical Elements',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:physicalelement_add',
                title='Add physical element',
                icon_class='mdi mdi-plus-thick',
            ),
        ),
    ),
    PluginMenuItem(
        link='plugins:netbox_power_plant:physicalobjectbinding_list',
        link_text='Physical Object Bindings',
        buttons=(
            PluginMenuButton(
                link='plugins:netbox_power_plant:physicalobjectbinding_add',
                title='Add physical object binding',
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
