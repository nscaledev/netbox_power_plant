import django.db.models.deletion
from django.db import migrations, models


def require_power_port_targets(apps, schema_editor):
    PowerHandoffPoint = apps.get_model('netbox_power_plant', 'PowerHandoffPoint')
    legacy_count = PowerHandoffPoint.objects.filter(power_port__isnull=True).count()
    if legacy_count:
        raise RuntimeError(
            'Cannot migrate RackDeliveryPoint to PowerHandoffPoint while '
            f'{legacy_count} rows do not target a power_port. Bind legacy rows to '
            'dcim.PowerPort first, then re-run migrations.'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_power_plant', '0006_internal_power_bus'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='RackDeliveryPoint',
            new_name='PowerHandoffPoint',
        ),
        migrations.AlterModelOptions(
            name='powerhandoffpoint',
            options={
                'ordering': ('power_system__name', 'name'),
                'verbose_name': 'power handoff point',
                'verbose_name_plural': 'power handoff points',
            },
        ),
        migrations.RunPython(require_power_port_targets, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='powerhandoffpoint',
            name='device',
        ),
        migrations.RemoveField(
            model_name='powerhandoffpoint',
            name='rack',
        ),
        migrations.AlterField(
            model_name='powerhandoffpoint',
            name='electrical_node',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='power_handoff_points',
                to='netbox_power_plant.electricalnode',
            ),
        ),
        migrations.AlterField(
            model_name='powerhandoffpoint',
            name='electrical_terminal',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='power_handoff_points',
                to='netbox_power_plant.electricalterminal',
            ),
        ),
        migrations.AlterField(
            model_name='powerhandoffpoint',
            name='expected_redundancy_group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='power_handoff_points',
                to='netbox_power_plant.redundancygroup',
            ),
        ),
        migrations.AlterField(
            model_name='powerhandoffpoint',
            name='power_port',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='power_plant_power_handoff_points',
                to='dcim.powerport',
            ),
        ),
        migrations.AlterField(
            model_name='powerhandoffpoint',
            name='power_system',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='power_handoff_points',
                to='netbox_power_plant.powersystem',
            ),
        ),
    ]
