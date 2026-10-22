from django.test import TransactionTestCase

from django.core.management import call_command
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from django.contrib.auth import get_user_model

from inventory.models import Category, Item, Location, Project

User = get_user_model()


class ImportCommandTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", "a@b.c", "pass")

    def test_dry_run_and_import(self):
        csv_body = (
            "name,location_path,quantity,quantity_approximate,categories,item_type,project,comment\n"
            "Cable,Lab/Drawer 1,5,yes,Electronics;Cables,USB,Outreach,spare\n"
        )
        with NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(csv_body)
            path = fh.name
        try:
            out = StringIO()
            call_command("import_inventory", file=path, dry_run=True, stdout=out)
            self.assertEqual(Item.objects.count(), 0)
            self.assertEqual(Location.objects.count(), 0)
            self.assertEqual(Category.objects.count(), 0)
            self.assertEqual(Project.objects.count(), 0)
            call_command("import_inventory", file=path, stdout=out)
            self.assertEqual(Item.objects.count(), 1)
            item = Item.objects.get()
            self.assertEqual(item.location.path_display(), "Lab / Drawer 1")
            self.assertEqual(item.quantity, 5)
            self.assertTrue(item.quantity_is_approximate)
            self.assertEqual(
                set(item.categories.values_list("name", flat=True)),
                {"Electronics", "Cables", "USB"},
            )
            self.assertEqual(item.project.name, "Outreach")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_installed_in_column(self):
        loc = Location.objects.create(name="Lab")
        host = Item.objects.create(
            name="Telescope",
            location=loc,
            created_by=self.user,
            updated_by=self.user,
        )
        csv_body = (
            "name,location_path,categories,installed_in\n"
            f"Camera,Dome,Imaging,{host.inventory_number}\n"
        )
        with NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(csv_body)
            path = fh.name
        try:
            call_command("import_inventory", file=path)
            camera = Item.objects.get(name="Camera")
            self.assertEqual(camera.installed_in_id, host.pk)
            self.assertEqual(camera.location_id, loc.pk)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_stored_in_and_is_container_columns(self):
        loc = Location.objects.create(name="Lab")
        case = Item.objects.create(
            name="DADOS case",
            location=loc,
            is_container=True,
            created_by=self.user,
            updated_by=self.user,
        )
        plain = Item.objects.create(
            name="Telescope", location=loc, created_by=self.user, updated_by=self.user
        )
        csv_body = (
            "name,location_path,categories,stored_in,is_container\n"
            f"Grating,Dome,Optics,{case.inventory_number},\n"
            "Small pouch,Dome,Bags,,yes\n"
            f"Slit,Dome,Optics,{plain.inventory_number},\n"
        )
        with NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(csv_body)
            path = fh.name
        try:
            out = StringIO()
            call_command("import_inventory", file=path, stdout=out)
            grating = Item.objects.get(name="Grating")
            self.assertEqual(grating.stored_in_id, case.pk)
            self.assertEqual(grating.location_id, loc.pk)
            self.assertTrue(Item.objects.get(name="Small pouch").is_container)
            self.assertFalse(Item.objects.filter(name="Slit").exists())
        finally:
            Path(path).unlink(missing_ok=True)
