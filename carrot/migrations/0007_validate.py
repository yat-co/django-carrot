# Generated manually 2023-03-18 09:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carrot', '0006_scheduled_task_time'),
    ]

    operations = [
        migrations.AddField(
            model_name='messagelog',
            name='validate',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='scheduledtask',
            name='validate',
            field=models.BooleanField(default=True),
        ),
    ]
