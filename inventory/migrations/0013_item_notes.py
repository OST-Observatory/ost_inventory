from django.db import migrations


def merge_comment_into_notes(apps, schema_editor):
    Item = apps.get_model("inventory", "Item")
    for item in Item.objects.exclude(comment="").only("pk", "notes", "comment").iterator():
        notes = item.notes.rstrip()
        item.notes = f"{notes}\n\n{item.comment.strip()}" if notes else item.comment.strip()
        item.save(update_fields=["notes"])


class Migration(migrations.Migration):
    """Description and comment become one free-text field, notes."""

    dependencies = [
        ("inventory", "0012_remove_legacy_container"),
    ]

    operations = [
        migrations.RenameField(model_name="item", old_name="description", new_name="notes"),
        migrations.RunPython(merge_comment_into_notes, migrations.RunPython.noop),
        migrations.RemoveField(model_name="item", name="comment"),
    ]
