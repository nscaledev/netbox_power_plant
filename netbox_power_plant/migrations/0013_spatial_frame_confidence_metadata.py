from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('netbox_power_plant', '0012_physical_plant_core'),
    ]

    operations = [
        migrations.AddField(
            model_name='spatialframe',
            name='confidence',
            field=models.CharField(default='unknown', max_length=32),
        ),
        migrations.AddField(
            model_name='spatialframe',
            name='metadata',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
