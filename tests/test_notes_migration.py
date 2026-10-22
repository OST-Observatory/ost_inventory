from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class NotesMigrationTests(TransactionTestCase):
    """0013 joins description and comment into notes without losing text."""

    before = [("inventory", "0012_remove_legacy_container")]
    after = [("inventory", "0013_item_notes")]

    def test_comment_is_appended_to_description(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old_apps = executor.loader.project_state(self.before).apps
        User = old_apps.get_model("accounts", "User")
        Location = old_apps.get_model("inventory", "Location")
        Item = old_apps.get_model("inventory", "Item")
        user = User.objects.create(username="u")
        loc = Location.objects.create(name="Lab")
        common = {"location": loc, "created_by": user, "updated_by": user}
        both = Item.objects.create(name="A", description="Desc", comment="Comment", **common)
        only_comment = Item.objects.create(name="B", description="", comment="Comment", **common)
        only_desc = Item.objects.create(name="C", description="Desc", comment="", **common)

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        new_apps = executor.loader.project_state(self.after).apps
        Item = new_apps.get_model("inventory", "Item")
        self.assertEqual(Item.objects.get(pk=both.pk).notes, "Desc\n\nComment")
        self.assertEqual(Item.objects.get(pk=only_comment.pk).notes, "Comment")
        self.assertEqual(Item.objects.get(pk=only_desc.pk).notes, "Desc")
