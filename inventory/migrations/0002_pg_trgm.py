from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


def apply_trigram(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    TrigramExtension().database_forwards("inventory", schema_editor, None, None)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(apply_trigram, noop_reverse),
    ]
