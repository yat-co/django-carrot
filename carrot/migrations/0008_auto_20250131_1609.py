# Generated by Django 2.2.28 on 2025-01-31 22:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('carrot', '0007_validate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='messagelog',
            name='uuid',
            field=models.CharField(db_index=True, max_length=200),
        ),
    ]
