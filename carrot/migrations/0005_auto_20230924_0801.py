# Generated by Django 2.2.24 on 2023-09-24 13:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carrot', '0004_set_unique_task_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledtask',
            name='last_run_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
