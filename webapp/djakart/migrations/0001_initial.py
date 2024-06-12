# Generated by Django 5.0.6 on 2024-06-05 15:01

import djakart.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='modelli',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('titolo', models.CharField(max_length=25)),
                ('descrizione', models.TextField(blank=True, null=True)),
                ('doc', models.FileField(upload_to=djakart.models.modelli.update_filename)),
            ],
            options={
                'verbose_name': 'Modello di documento',
                'verbose_name_plural': 'Modelli di documento',
            },
        ),
        migrations.CreateModel(
            name='version',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=20)),
                ('note', models.TextField(blank=True)),
                ('progetto', models.FileField(blank=True, upload_to='', verbose_name='Progetto di QGIS')),
                ('riservato', models.BooleanField(default=False)),
                ('base', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='djakart.version')),
                ('referente', models.ForeignKey(blank=True, limit_choices_to={'groups__name': 'gis'}, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('template_qgis', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='djakart.modelli')),
                ('versione_confronto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='confronto', to='djakart.version')),
            ],
            options={
                'verbose_name': 'Version',
                'verbose_name_plural': 'Versions',
            },
        ),
    ]
