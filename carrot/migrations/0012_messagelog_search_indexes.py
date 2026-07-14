# Generated manually for MessageLog status and search indexes

from django.db import migrations, models


def forwards_pg_search_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ex = schema_editor.execute
    ex("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    ex(
        "CREATE INDEX IF NOT EXISTS carrot_msglog_task_trgm "
        "ON carrot_messagelog USING gin (task gin_trgm_ops)"
    )
    ex(
        "CREATE INDEX IF NOT EXISTS carrot_msglog_content_trgm "
        "ON carrot_messagelog USING gin (content gin_trgm_ops)"
    )
    ex(
        "CREATE INDEX IF NOT EXISTS carrot_msglog_worker_trgm "
        "ON carrot_messagelog USING gin (worker gin_trgm_ops)"
    )
    ex(
        "CREATE INDEX IF NOT EXISTS carrot_msglog_queue_trgm "
        "ON carrot_messagelog USING gin (queue gin_trgm_ops)"
    )
    ex(
        "CREATE INDEX IF NOT EXISTS carrot_msglog_search_fts ON carrot_messagelog USING gin ("
        "to_tsvector('english', coalesce(task,'')||' '||coalesce(worker,'')||' '||"
        "coalesce(content,'')||' '||coalesce(task_args,''))"
        ")"
    )


def reverse_pg_search_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    ex = schema_editor.execute
    ex("DROP INDEX IF EXISTS carrot_msglog_search_fts")
    ex("DROP INDEX IF EXISTS carrot_msglog_queue_trgm")
    ex("DROP INDEX IF EXISTS carrot_msglog_worker_trgm")
    ex("DROP INDEX IF EXISTS carrot_msglog_content_trgm")
    ex("DROP INDEX IF EXISTS carrot_msglog_task_trgm")


class Migration(migrations.Migration):

    dependencies = [
        ('carrot', '0011_scheduledtask_priority'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(
                fields=['status', '-failure_time'],
                name='carrot_msglog_status_fail',
            ),
        ),
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(
                fields=['status', '-completion_time'],
                name='carrot_msglog_status_comp',
            ),
        ),
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(
                fields=['status', '-priority', 'publish_time'],
                name='carrot_msglog_status_pub',
            ),
        ),
        migrations.AddIndex(
            model_name='messagelog',
            index=models.Index(
                fields=['status', 'task'],
                name='carrot_msglog_status_task',
            ),
        ),
        # Do not B-tree index `content` (TextField): Postgres index rows are
        # capped at 8191 bytes; large JSON kwargs fail CREATE INDEX with
        # ProgramLimitExceeded. Content filtering uses the GIN trigram index.
        migrations.RunPython(forwards_pg_search_indexes, reverse_pg_search_indexes),
    ]
