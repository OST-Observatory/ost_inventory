import io
from tempfile import NamedTemporaryFile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from inventory.container_migration import apply_plan, build_plan, read_plan, write_plan
from inventory.models import Item, Location

User = get_user_model()


class ContainerMigrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="x", is_superuser=True)
        self.lab = Location.objects.create(name="Lab")
        self.shelf = Location.objects.create(name="3g", parent=self.lab)
        self.drawer = Location.objects.create(name="2e", parent=self.lab)
        self.dome = Location.objects.create(name="Dome")
        mk = self.make
        self.baches = mk("BACHES echelle spectrograph", self.shelf)
        self.case = mk("BACHES case", self.shelf, installed_in=self.baches)
        self.baches.container = "BACHES case"
        self.baches.save()
        self.camera = mk("QHY268M", self.shelf, installed_in=self.baches, container="BACHES case")
        self.eyepiece_case = mk("Eyepiece case TS", self.shelf)
        self.eyepiece = mk("Plössl 25 mm", self.drawer, container="Eyepiece case")
        self.screws = mk("M4 screws", self.drawer, container="Screws, etc.")
        self.nuts = mk("M4 nuts", self.drawer, container="screws, etc")
        self.c11 = mk("Celestron C11", self.dome)
        self.clamp = mk("Seeker clamp", self.dome, container="C11")
        self.cds = mk("CDs", self.drawer, container="CDs")
        mk("Lamp A", self.drawer, container="Lamps I")
        mk("Lamp B", self.drawer, container="Lamps II")

    def make(self, name, location, **extra):
        return Item.objects.create(
            name=name, location=location, created_by=self.user, updated_by=self.user, **extra
        )

    def plan(self):
        return {(r["kind"], r.get("container_text"), r.get("items")): r for r in build_plan()}

    def text_row(self, plan, text):
        return next(r for (kind, t, _), r in plan.items() if kind == "text" and t == text)

    def test_plan_proposals(self):
        plan = self.plan()
        self.assertEqual(self.text_row(plan, "BACHES case")["action"], "link")
        self.assertEqual(self.text_row(plan, "BACHES case")["target"], self.case.inventory_number)
        eyepieces = self.text_row(plan, "Eyepiece case")
        self.assertEqual((eyepieces["action"], eyepieces["target"]), ("link", self.eyepiece_case.inventory_number))
        variant = self.text_row(plan, "screws, etc")
        self.assertEqual((variant["action"], variant["target"]), ("merge", "Screws, etc."))
        self.assertEqual(self.text_row(plan, "Screws, etc.")["action"], "new")
        c11 = self.text_row(plan, "C11")
        self.assertEqual((c11["action"], c11["target"]), ("mount", self.c11.inventory_number))
        self.assertEqual(self.text_row(plan, "CDs")["action"], "clear")
        self.assertEqual(self.text_row(plan, "Lamps I")["action"], "new")
        self.assertEqual(self.text_row(plan, "Lamps II")["action"], "new")
        items = {(r["items"], r["action"]): r for r in plan.values() if r["kind"] == "item"}
        self.assertIn((self.case.inventory_number, "unmount"), items)
        self.assertEqual(items[(self.baches.inventory_number, "store")]["target"], self.case.inventory_number)
        camera = items[(self.camera.inventory_number, "store")]
        self.assertEqual(camera["target"], "BACHES case")

    def run_plan(self, rows, commit):
        buf = io.StringIO()
        write_plan(rows, buf)
        buf.seek(0)
        return apply_plan(read_plan(buf), self.user, commit=commit)

    def test_dry_run_changes_nothing(self):
        result = self.run_plan(build_plan(), commit=False)
        self.assertEqual(result.errors, [])
        self.assertGreater(result.items_changed, 0)
        self.assertEqual(Item.objects.filter(is_container=True).count(), 0)
        self.assertEqual(Item.objects.exclude(container="").count(), 9)

    def test_commit_with_reviewed_override(self):
        # The proposal already stores the camera loose in the case.
        result = self.run_plan(build_plan(), commit=True)
        self.assertEqual(result.errors, [])
        for item in Item.objects.all():
            item.refresh_from_db()
        self.case.refresh_from_db()
        self.baches.refresh_from_db()
        self.camera.refresh_from_db()
        self.assertTrue(self.case.is_container)
        self.assertIsNone(self.case.installed_in_id)
        self.assertEqual(self.baches.stored_in_id, self.case.pk)
        self.assertEqual(self.camera.stored_in_id, self.case.pk)
        self.assertIsNone(self.camera.installed_in_id)
        self.eyepiece.refresh_from_db()
        self.assertEqual(self.eyepiece.stored_in_id, self.eyepiece_case.pk)
        self.assertEqual(self.eyepiece.location_id, self.shelf.pk)
        self.screws.refresh_from_db()
        self.nuts.refresh_from_db()
        box = self.screws.stored_in
        self.assertEqual(box.name, "Screws, etc.")
        self.assertEqual(self.nuts.stored_in_id, box.pk)
        self.assertEqual([c.name for c in box.categories.all()], ["Container"])
        self.clamp.refresh_from_db()
        self.assertEqual(self.clamp.installed_in_id, self.c11.pk)
        self.assertEqual(Item.objects.exclude(container="").count(), 0)
        self.assertEqual(build_plan(), [])

    def test_errors_roll_back_everything(self):
        rows = build_plan()
        rows.append({"kind": "item", "items": self.screws.inventory_number, "action": "store", "target": "#9999"})
        result = self.run_plan(rows, commit=True)
        self.assertTrue(result.errors)
        self.assertEqual(Item.objects.filter(is_container=True).count(), 0)
        self.assertEqual(Item.objects.exclude(container="").count(), 9)

    def test_commands(self):
        with NamedTemporaryFile("w+", suffix=".csv") as fh:
            call_command("container_plan", out=fh.name, stdout=io.StringIO())
            out = io.StringIO()
            call_command("container_apply", fh.name, stdout=out)
            self.assertIn("Dry run", out.getvalue())
            fh.seek(0)
            fh.write("kind,container_text,room,action,target,items,places,note\ntext,C11,Dome,explode,,,,\n")
            fh.truncate()
            fh.flush()
            with self.assertRaises(CommandError):
                call_command("container_apply", fh.name, "--commit", stdout=io.StringIO())
