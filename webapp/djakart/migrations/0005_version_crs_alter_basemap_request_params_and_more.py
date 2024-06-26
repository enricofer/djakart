# Generated by Django 5.0.6 on 2024-06-17 21:31

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('djakart', '0004_alter_modelli_options_version_extent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='version',
            name='crs',
            field=models.CharField(default='EPSG:4326', max_length=20, verbose_name='Coordinate system epsg code'),
        ),
        migrations.AlterField(
            model_name='basemap',
            name='request_params',
            field=models.JSONField(blank=True, default={'CRS': '', 'DPI': 150, 'LAYERS': ''}, null=True),
        ),
        migrations.AlterField(
            model_name='basemap',
            name='srid',
            field=models.CharField(max_length=20),
        ),
    ]
