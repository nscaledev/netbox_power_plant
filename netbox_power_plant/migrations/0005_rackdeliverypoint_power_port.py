from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_power_plant', '0004_electricalnodeplacement'),
    ]

    operations = [
        migrations.AddField(
            model_name='rackdeliverypoint',
            name='power_port',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='power_plant_rack_delivery_points', to='dcim.powerport'),
        ),
    ]
