from django.db import migrations


CREATE_LEGACY_RACK_DELIVERY_POINT_VIEW = """
CREATE VIEW netbox_power_plant_rackdeliverypoint AS
SELECT
    php.id,
    php.created,
    php.last_updated,
    php.custom_field_data,
    php.name,
    php.slug,
    php.description,
    php.delivery_role,
    php.feed_label,
    php.design_state,
    pp.device_id,
    php.electrical_node_id,
    php.electrical_terminal_id,
    php.expected_redundancy_group_id,
    php.power_system_id,
    d.rack_id,
    php.power_port_id
FROM netbox_power_plant_powerhandoffpoint php
JOIN dcim_powerport pp ON pp.id = php.power_port_id
JOIN dcim_device d ON d.id = pp.device_id
"""


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_power_plant', '0007_power_handoff_point'),
    ]

    operations = [
        migrations.RunSQL(
            sql=f"""
                DROP VIEW IF EXISTS netbox_power_plant_rackdeliverypoint;
                {CREATE_LEGACY_RACK_DELIVERY_POINT_VIEW};
            """,
            reverse_sql='DROP VIEW IF EXISTS netbox_power_plant_rackdeliverypoint;',
        ),
    ]
