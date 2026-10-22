from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Category, Item, Location, StocktakeScan

User = get_user_model()


class ContainerTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        self.lab = Location.objects.create(name="Lab")
        self.shelf = Location.objects.create(name="3i", parent=self.lab)
        self.seminar = Location.objects.create(name="Seminar")
        self.case = self.make("UVEX case", location=self.shelf, is_container=True)
        self.client = Client()
        self.client.login(username="writer", password="x")

    def make(self, name, location=None, **extra):
        return Item.objects.create(
            name=name,
            location=location or self.lab,
            created_by=self.user,
            updated_by=self.user,
            **extra,
        )


class ContainerModelTests(ContainerTestBase):
    def test_stored_item_follows_container_and_its_mounted_parts(self):
        spectrograph = self.make("UVEX spectrograph", location=self.seminar)
        camera = self.make("Main camera", installed_in=spectrograph)
        spectrograph.stored_in = self.case
        spectrograph.save()
        camera.refresh_from_db()
        self.assertEqual(spectrograph.location_id, self.shelf.pk)
        self.assertEqual(camera.location_id, self.shelf.pk)
        self.assertEqual(camera.effective_container, self.case)

        self.case.location = self.seminar
        self.case.save()
        spectrograph.refresh_from_db()
        camera.refresh_from_db()
        self.assertEqual(spectrograph.location_id, self.seminar.pk)
        self.assertEqual(camera.location_id, self.seminar.pk)

    def test_rules_for_stored_in(self):
        plain = self.make("Not a box")
        host = self.make("Host")
        item = self.make("Eyepiece", stored_in=None)
        item.stored_in = plain
        with self.assertRaises(ValidationError):
            item.full_clean()
        item.stored_in = self.case
        item.installed_in = host
        with self.assertRaises(ValidationError):
            item.full_clean()
        item.installed_in = None
        item.full_clean()
        item.save()
        self.case.is_container = False
        with self.assertRaises(ValidationError):
            self.case.full_clean()

    def test_loops_through_mount_and_storage_are_rejected(self):
        inner = self.make("Inner bag", is_container=True, stored_in=self.case)
        self.case.stored_in = inner
        with self.assertRaises(ValidationError):
            self.case.full_clean()
        host = self.make("Host", stored_in=self.case)
        self.case.stored_in = None
        self.case.installed_in = host
        with self.assertRaises(ValidationError):
            self.case.full_clean()


class ContainerViewTests(ContainerTestBase):
    def test_store_in_dialog_and_new_container(self):
        lens = self.make("Lens", location=self.seminar)
        resp = self.client.post(
            reverse("inventory:item_store", args=[lens.pk]), {"store-stored_in": self.case.pk}
        )
        self.assertEqual(resp.status_code, 302)
        lens.refresh_from_db()
        self.assertEqual(lens.stored_in_id, self.case.pk)
        self.assertEqual(lens.location_id, self.shelf.pk)

        resp = self.client.post(
            reverse("inventory:item_store", args=[lens.pk]),
            {"store-stored_in": "", "store-new_container_name": "Lens pouch"},
        )
        lens.refresh_from_db()
        pouch = lens.stored_in
        self.assertEqual(pouch.name, "Lens pouch")
        self.assertTrue(pouch.is_container)
        self.assertEqual(pouch.location_id, self.shelf.pk)
        self.assertEqual([c.name for c in pouch.categories.all()], ["Container"])

        self.client.post(reverse("inventory:item_store", args=[lens.pk]), {"store-stored_in": ""})
        lens.refresh_from_db()
        self.assertIsNone(lens.stored_in_id)

    def test_store_refuses_non_container(self):
        lens = self.make("Lens")
        plain = self.make("Plain item")
        self.client.post(reverse("inventory:item_store", args=[lens.pk]), {"store-stored_in": plain.pk})
        lens.refresh_from_db()
        self.assertIsNone(lens.stored_in_id)

    def test_mounting_takes_item_out_of_container(self):
        host = self.make("Telescope", location=self.seminar)
        camera = self.make("Camera", stored_in=self.case)
        self.client.post(reverse("inventory:item_install", args=[camera.pk]), {"installed_in": host.pk})
        camera.refresh_from_db()
        self.assertEqual(camera.installed_in_id, host.pk)
        self.assertIsNone(camera.stored_in_id)
        self.assertEqual(camera.location_id, self.seminar.pk)

    def test_detail_pages_show_container_and_contents(self):
        spectrograph = self.make("UVEX spectrograph", stored_in=self.case)
        camera = self.make("Main camera", installed_in=spectrograph)
        detail = self.client.get(reverse("inventory:item_detail", args=[self.case.pk]))
        self.assertContains(detail, "chip-container")
        self.assertContains(detail, "Contents")
        self.assertContains(detail, "UVEX spectrograph")
        self.assertContains(detail, "Main camera")
        self.assertContains(detail, "Stocktake this container")
        part = self.client.get(reverse("inventory:item_detail", args=[camera.pk]))
        self.assertContains(part, "UVEX case")
        self.assertContains(part, "(with #")
        listing = self.client.get(reverse("inventory:containers"))
        self.assertContains(listing, "UVEX case")
        self.assertContains(listing, "1 item")

    def test_move_contents_merges_containers(self):
        other = self.make("Second case", location=self.seminar, is_container=True)
        a = self.make("A", stored_in=self.case)
        b = self.make("B", stored_in=self.case)
        resp = self.client.post(
            reverse("inventory:item_move_contents", args=[self.case.pk]), {"move-into": other.pk}
        )
        self.assertRedirects(resp, reverse("inventory:item_detail", args=[other.pk]))
        for item in (a, b):
            item.refresh_from_db()
            self.assertEqual(item.stored_in_id, other.pk)
            self.assertEqual(item.location_id, self.seminar.pk)

    def test_item_form_sets_container_and_flag(self):
        Category.objects.create(name="Optics")
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "Filter wheel",
                "quantity": 1,
                "category_1": "Optics",
                "stored_in": self.case.pk,
                "description": "",
                "comment": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        wheel = Item.objects.get(name="Filter wheel")
        self.assertEqual(wheel.stored_in_id, self.case.pk)
        self.assertEqual(wheel.location_id, self.shelf.pk)
        form = self.client.get(reverse("inventory:item_edit", args=[wheel.pk]))
        self.assertContains(form, 'data-lookup-kind="container"')
        self.assertContains(form, "data-new-container")
        self.assertContains(form, "This item is a container")

    def test_lookup_and_search_by_container(self):
        lens = self.make("Lens", stored_in=self.case)
        self.make("Loose lens")
        found = self.client.get(reverse("inventory:item_host_lookup"), {"q": "UVEX", "kind": "container"})
        self.assertEqual([r["id"] for r in found.json()["results"]], [self.case.pk])
        none = self.client.get(reverse("inventory:item_host_lookup"), {"q": "Lens", "kind": "container"})
        self.assertEqual(none.json()["results"], [])
        by_box = self.client.get(reverse("inventory:search"), {"container": self.case.pk})
        self.assertContains(by_box, lens.inventory_number)
        self.assertNotContains(by_box, "Loose lens")
        by_text = self.client.get(reverse("inventory:search"), {"q": "UVEX case"})
        self.assertContains(by_text, lens.inventory_number)
        scan = self.client.get(reverse("inventory:scan_lookup"), {"q": self.case.inventory_number})
        self.assertTrue(scan.json()["is_container"])


class ContainerStocktakeTests(ContainerTestBase):
    def setUp(self):
        super().setUp()
        self.spectrograph = self.make("UVEX spectrograph", stored_in=self.case)
        self.camera = self.make("Main camera", installed_in=self.spectrograph)
        self.missing = self.make("Calibration lamp", stored_in=self.case)
        self.other_case = self.make("BACHES case", location=self.shelf, is_container=True)
        self.stray = self.make("QHY268M", stored_in=self.other_case)

    def _start(self):
        resp = self.client.post(reverse("inventory:stocktake"), {"scope": f"container:{self.case.pk}"})
        return int(resp["Location"].rstrip("/").split("/")[-1])

    def _scan(self, item):
        self.client.get(reverse("item_short", args=[item.pk]))

    def test_container_scope_expects_contents_and_mounted_parts(self):
        pk = self._start()
        detail = self.client.get(reverse("inventory:stocktake_detail", args=[pk]))
        self.assertContains(detail, "UVEX case")
        self.assertContains(detail, "Counting inside")
        self.assertContains(detail, "3 expected")
        self._scan(self.spectrograph)
        self._scan(self.camera)
        self._scan(self.stray)
        report = self.client.get(reverse("inventory:stocktake_detail", args=[pk]))
        found_here = [s.item_id for s in report.context["report"]["found_here"]]
        self.assertCountEqual(found_here, [self.spectrograph.pk, self.camera.pk])
        elsewhere = [s.item_id for s in report.context["report"]["found_elsewhere"]]
        self.assertEqual(elsewhere, [self.stray.pk])
        self.assertEqual([i.pk for i in report.context["report"]["missing"]], [self.missing.pk])
        self.assertEqual([s.item_id for s in report.context["report"]["unexpected"]], [self.stray.pk])

    def test_move_here_puts_item_into_found_container(self):
        pk = self._start()
        self._scan(self.stray)
        scan = StocktakeScan.objects.get(stocktake_id=pk, item=self.stray)
        self.assertEqual(scan.found_container_id, self.case.pk)
        self.assertEqual(scan.expected_container_id, self.other_case.pk)
        self.client.post(reverse("inventory:stocktake_move_here", args=[pk, scan.pk]))
        self.stray.refresh_from_db()
        self.assertEqual(self.stray.stored_in_id, self.case.pk)

    def test_scanning_container_opens_it_and_location_closes_it(self):
        resp = self.client.post(reverse("inventory:stocktake"), {"scope": f"room:{self.lab.pk}"})
        pk = int(resp["Location"].rstrip("/").split("/")[-1])
        self.client.get(reverse("location_short", args=[self.shelf.pk]))
        self._scan(self.other_case)
        self._scan(self.stray)
        scan = StocktakeScan.objects.get(stocktake_id=pk, item=self.stray)
        self.assertEqual(scan.found_container_id, self.other_case.pk)
        self.assertTrue(scan.found_where_expected)
        self.client.get(reverse("location_short", args=[self.shelf.pk]))
        self._scan(self.missing)
        scan = StocktakeScan.objects.get(stocktake_id=pk, item=self.missing)
        self.assertIsNone(scan.found_container_id)
        self.assertTrue(scan.found_where_expected)
