from django.db import migrations
from django_scopes import scopes_disabled


def backfill_table_categories(apps, schema_editor):
    # Uses the real model, not the historical apps.get_model() snapshot, because the actual
    # work happens in Table.sync_pretix_objects() - re-running it is how every existing table
    # picks up the dedicated "Tables" category introduced alongside this migration.
    from pretix_tables.models import Table

    with scopes_disabled():
        for table in Table.objects.all():
            table.sync_pretix_objects()


class Migration(migrations.Migration):

    dependencies = [
        ('pretix_tables', '0002_tableseat'),
    ]

    operations = [
        migrations.RunPython(backfill_table_categories, migrations.RunPython.noop),
    ]
