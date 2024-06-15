# Generated by Django 5.0.6 on 2024-06-14 10:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('djakart', '0002_basemap'),
    ]

    operations = [
        migrations.AddField(
            model_name='basemap',
            name='depth',
            field=models.CharField(choices=[('background', 'background'), ('foreground', 'foreground')], default='background', max_length=10),
        ),
        migrations.AddField(
            model_name='basemap',
            name='srid',
            field=models.CharField(default='EPSG:3003', max_length=20),
        ),
    ]