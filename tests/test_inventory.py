from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image

from accounts.permissions import user_can_admin, user_can_read, user_can_write
from inventory.labels import LABEL_SIZES, render_label_png
from inventory.models import Category, Item, Loan, Location, Project, StocktakeScan

User = get_user_model()


class PermissionsTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student", password="x", is_student=True
        )
        self.supervisor = User.objects.create_user(
            username="supervisor", password="x", is_supervisor=True
        )
        self.staff = User.objects.create_user(
            username="staff", password="x", is_staff=True
        )
        self.outsider = User.objects.create_user(username="outsider", password="x")

    def test_role_matrix(self):
        self.assertTrue(user_can_read(self.student))
        self.assertFalse(user_can_write(self.student))
        self.assertFalse(user_can_admin(self.student))

        self.assertTrue(user_can_read(self.supervisor))
        self.assertTrue(user_can_write(self.supervisor))
        self.assertFalse(user_can_admin(self.supervisor))

        self.assertTrue(user_can_read(self.staff))
        self.assertTrue(user_can_write(self.staff))
        self.assertTrue(user_can_admin(self.staff))

        self.assertFalse(user_can_read(self.outsider))
        self.assertFalse(user_can_write(self.outsider))


class InventoryFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        self.reader = User.objects.create_user(
            username="reader", password="x", is_student=True
        )
        self.loc = Location.objects.create(name="Observatory")
        self.box = Location.objects.create(name="Box A", parent=self.loc)
        self.client = Client()

    def test_create_item_and_loan(self):
        self.client.login(username="writer", password="x")
        Category.objects.create(name="Optics")
        resp = self.client.get(reverse("inventory:item_create"))
        self.assertContains(resp, "Required")
        self.assertContains(resp, "Quantity *")
        self.assertContains(resp, "Categories *")
        self.assertContains(resp, "Room *")
        self.assertContains(resp, "Tools → Locations")
        self.assertContains(resp, 'name="room"')
        self.assertContains(resp, 'name="category_1"')
        self.assertContains(resp, 'list="category-suggestions"')
        self.assertContains(resp, "Optics")
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "Filter wheel",
                "room": self.loc.pk,
                "place": self.box.pk,
                "quantity": 1,
                "category_1": "Filter",
                "description": "",
                "comment": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        item = Item.objects.get(name="Filter wheel")
        self.assertEqual(item.inventory_number, f"#{item.pk:04d}")
        self.assertEqual(item.categories.get().name, "Filter")
        self.assertEqual(item.location.path_display(), "Observatory / Box A")

        resp = self.client.post(
            reverse("inventory:loan_create", args=[item.pk]),
            {
                "borrower_name": "Guest",
                "borrower_contact": "guest@example.com",
                "due_date": "2099-01-01",
                "note": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(item.loans.filter(returned_at__isnull=True).exists())

        # second open loan must fail at DB/constraint level via view guard
        resp = self.client.post(
            reverse("inventory:loan_create", args=[item.pk]),
            {
                "borrower_name": "Other",
                "borrower_contact": "",
                "due_date": "2099-02-01",
                "note": "",
            },
        )
        self.assertEqual(Loan.objects.filter(item=item, returned_at__isnull=True).count(), 1)

    def test_reader_cannot_create(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:item_create"))
        self.assertEqual(resp.status_code, 403)

    def test_search_requires_role(self):
        outsider = User.objects.create_user(username="x", password="x")
        self.client.login(username="x", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertEqual(resp.status_code, 403)

    def test_short_urls(self):
        item = Item.objects.create(
            name="Camera",
            location=self.loc,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("item_short", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse("location_short", args=[self.loc.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_category_reuse_case_insensitive(self):
        t1, created1 = Category.get_or_create_by_name("CCD")
        t2, created2 = Category.get_or_create_by_name("ccd")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(t1.pk, t2.pk)

    def test_up_to_four_categories_and_reuse(self):
        Category.objects.create(name="CCD")
        self.client.login(username="writer", password="x")
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "Camera",
                "room": self.loc.pk,
                "quantity": 1,
                "description": "",
                "comment": "",
                "category_1": "ccd",
                "category_2": "Optics",
                "category_3": "Imaging",
                "category_4": "Sensor",
                "category_5": "Extra",
            },
        )
        self.assertEqual(resp.status_code, 302)
        item = Item.objects.get(name="Camera")
        names = list(item.categories.order_by("name").values_list("name", flat=True))
        self.assertEqual(names, ["CCD", "Imaging", "Optics", "Sensor"])
        self.assertEqual(Category.objects.filter(name__iexact="ccd").count(), 1)
        self.assertFalse(Category.objects.filter(name="Extra").exists())
        resp = self.client.get(reverse("inventory:item_edit", args=[item.pk]))
        self.assertContains(resp, 'value="CCD"')
        self.assertContains(resp, 'value="Optics"')
        self.assertNotContains(resp, 'name="category_5"')

    def test_category_required(self):
        self.client.login(username="writer", password="x")
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "No category",
                "room": self.loc.pk,
                "quantity": 1,
                "description": "",
                "comment": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Item.objects.filter(name="No category").exists())

    def test_project_container_and_approximate_quantity(self):
        self.client.login(username="writer", password="x")
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "M4 screws",
                "room": self.loc.pk,
                "quantity": 80,
                "quantity_is_approximate": "on",
                "container": "Crate 4",
                "project_name": "Sternwarte 2026",
                "category_1": "Hardware",
                "description": "",
                "comment": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        item = Item.objects.get(name="M4 screws")
        self.assertEqual(item.quantity_display, "~80")
        self.assertTrue(item.quantity_is_approximate)
        self.assertEqual(item.container, "Crate 4")
        self.assertEqual(item.project.name, "Sternwarte 2026")

        reused, created = Project.get_or_create_by_name("sternwarte 2026")
        self.assertFalse(created)
        self.assertEqual(reused.pk, item.project_id)

        self.client.login(username="reader", password="x")
        search = self.client.get(reverse("inventory:search"), {"project": item.project_id})
        self.assertContains(search, "M4 screws")
        search = self.client.get(reverse("inventory:search"), {"container": "Crate 4"})
        self.assertContains(search, "M4 screws")
        detail = self.client.get(reverse("inventory:item_detail", args=[item.pk]))
        self.assertContains(detail, "~80")
        self.assertContains(detail, "Crate 4")
        self.assertContains(detail, "Hardware")
        self.assertContains(detail, "Sternwarte 2026")

    def test_locations_page_and_add_place(self):
        self.client.login(username="writer", password="x")
        resp = self.client.get(reverse("inventory:locations"))
        self.assertContains(resp, "Observatory")
        self.assertContains(resp, "Box A")
        resp = self.client.post(
            reverse("inventory:location_add_room"),
            {"name": "PRA"},
        )
        self.assertEqual(resp.status_code, 302)
        pra = Location.objects.get(name="PRA", parent=None)
        resp = self.client.post(
            reverse("inventory:location_add_place"),
            {"room": pra.pk, "name": "2a"},
        )
        self.assertEqual(resp.status_code, 302)
        place = Location.objects.get(name="2a", parent=pra)
        self.assertEqual(place.path_display(), "PRA / 2a")

    def test_rename_room_and_remove_place(self):
        item = Item.objects.create(
            name="Eyepiece",
            location=self.box,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client.login(username="writer", password="x")
        resp = self.client.get(reverse("inventory:locations"))
        self.assertContains(resp, "Rename")
        self.assertContains(resp, "Remove")

        resp = self.client.post(
            reverse("inventory:location_rename_room", args=[self.loc.pk]),
            {"name": "Sternwarte"},
        )
        self.assertEqual(resp.status_code, 302)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.name, "Sternwarte")
        item.refresh_from_db()
        self.assertEqual(item.location.path_display(), "Sternwarte / Box A")

        clash = Location.objects.create(name="Lab")
        resp = self.client.post(
            reverse("inventory:location_rename_room", args=[self.loc.pk]),
            {"name": "lab"},
        )
        self.assertEqual(resp.status_code, 302)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.name, "Sternwarte")
        self.assertTrue(Location.objects.filter(pk=clash.pk, name="Lab").exists())

        empty = Location.objects.create(name="Shelf", parent=self.loc)
        resp = self.client.post(
            reverse("inventory:location_delete_place", args=[empty.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Location.objects.filter(pk=empty.pk).exists())

        resp = self.client.post(
            reverse("inventory:location_delete_place", args=[self.box.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Location.objects.filter(pk=self.box.pk).exists())
        item.refresh_from_db()
        self.assertEqual(item.location_id, self.loc.pk)
        self.assertEqual(item.location.path_display(), "Sternwarte")

    def test_reader_cannot_rename_or_remove_locations(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:locations"))
        self.assertContains(resp, "Observatory")
        self.assertNotContains(resp, "Rename")
        self.assertNotContains(resp, "Remove")
        resp = self.client.post(
            reverse("inventory:location_rename_room", args=[self.loc.pk]),
            {"name": "Nope"},
        )
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(
            reverse("inventory:location_delete_place", args=[self.box.pk]),
        )
        self.assertEqual(resp.status_code, 403)
        self.loc.refresh_from_db()
        self.assertEqual(self.loc.name, "Observatory")
        self.assertTrue(Location.objects.filter(pk=self.box.pk).exists())

    def test_item_form_selects_existing_locations_only(self):
        self.client.login(username="writer", password="x")
        resp = self.client.get(reverse("inventory:item_create"))
        self.assertContains(resp, 'id="id_room"')
        self.assertContains(resp, 'id="id_place"')
        self.assertContains(resp, reverse("inventory:locations"))
        self.assertNotContains(resp, "room_name")
        self.assertNotContains(resp, "place_name")

        before = Location.objects.count()
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "Orphan item",
                "room_name": "Brand new hall",
                "place_name": "Shelf Z",
                "quantity": 1,
                "category_1": "Misc",
                "description": "",
                "comment": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Item.objects.filter(name="Orphan item").exists())
        self.assertEqual(Location.objects.count(), before)
        self.assertFalse(Location.objects.filter(name="Brand new hall").exists())

        other = Location.objects.create(name="Workshop")
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "Mismatched place",
                "room": other.pk,
                "place": self.box.pk,
                "quantity": 1,
                "category_1": "Misc",
                "description": "",
                "comment": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Item.objects.filter(name="Mismatched place").exists())
        self.assertContains(resp, "Place must belong to the selected room.")


class LabelPngTests(TestCase):
    def test_all_presets_match_pixel_size(self):
        for size in LABEL_SIZES.values():
            png = render_label_png(
                "http://testserver/i/1/",
                "Camera body",
                "#0001",
                "Observatory / Box A",
                size,
            )
            img = Image.open(BytesIO(png))
            self.assertEqual(
                img.size,
                (size.width_px, size.height_px),
                msg=size.key,
            )


class StocktakeFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        self.reader = User.objects.create_user(
            username="reader", password="x", is_student=True
        )
        self.room = Location.objects.create(name="Observatory")
        self.place = Location.objects.create(name="Box A", parent=self.room)
        self.other = Location.objects.create(name="Workshop")
        self.here = Item.objects.create(
            name="Eyepiece",
            location=self.place,
            created_by=self.user,
            updated_by=self.user,
        )
        self.missing = Item.objects.create(
            name="Filter",
            location=self.place,
            created_by=self.user,
            updated_by=self.user,
        )
        self.elsewhere = Item.objects.create(
            name="Mount",
            location=self.other,
            created_by=self.user,
            updated_by=self.user,
        )
        self.client = Client()

    def test_reader_cannot_start_stocktake(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:stocktake"))
        self.assertEqual(resp.status_code, 403)

    def test_scan_short_urls_and_finish_report(self):
        self.client.login(username="writer", password="x")
        resp = self.client.post(
            reverse("inventory:stocktake"),
            {"scope_location": str(self.room.pk)},
        )
        self.assertEqual(resp.status_code, 302)
        stocktake_pk = int(resp["Location"].rstrip("/").split("/")[-1])

        resp = self.client.get(reverse("location_short", args=[self.place.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], reverse("inventory:stocktake_detail", args=[stocktake_pk]))

        resp = self.client.get(reverse("item_short", args=[self.here.pk]))
        self.assertEqual(resp.status_code, 302)
        self.here.refresh_from_db()
        self.assertIsNotNone(self.here.last_seen_at)

        resp = self.client.get(reverse("item_short", args=[self.elsewhere.pk]))
        self.assertEqual(resp.status_code, 302)

        resp = self.client.get(reverse("inventory:item_detail", args=[self.missing.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(
            StocktakeScan.objects.filter(stocktake_id=stocktake_pk, item=self.missing).exists()
        )

        resp = self.client.post(reverse("inventory:stocktake_finish", args=[stocktake_pk]))
        self.assertEqual(resp.status_code, 302)
        report = self.client.get(reverse("inventory:stocktake_detail", args=[stocktake_pk]))
        self.assertContains(report, "Eyepiece")
        self.assertContains(report, "Not found")
        self.assertContains(report, "Filter")
        self.assertContains(report, "Found elsewhere")
        self.assertContains(report, "Mount")
        self.assertContains(report, "Move here")

        scan = StocktakeScan.objects.get(stocktake_id=stocktake_pk, item=self.elsewhere)
        resp = self.client.post(
            reverse("inventory:stocktake_move_here", args=[stocktake_pk, scan.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.elsewhere.refresh_from_db()
        self.assertEqual(self.elsewhere.location_id, self.place.pk)
