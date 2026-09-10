from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from inventory.models import Item, Loan, Location
from inventory.templatetags.display import relative_due

User = get_user_model()


class UiNavTests(TestCase):
    def setUp(self):
        self.writer = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        self.reader = User.objects.create_user(
            username="reader", password="x", is_student=True
        )
        loc = Location.objects.create(name="Lab")
        item = Item.objects.create(
            name="Scope", location=loc, created_by=self.writer, updated_by=self.writer
        )
        Loan.objects.create(
            item=item,
            borrower_name="A",
            borrower_contact="a@example.com",
            due_date=date.today() - timedelta(days=2),
            recorded_by=self.writer,
        )
        self.client = Client()

    def test_tools_hidden_for_student(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Add item")
        self.assertNotContains(resp, "Import")
        self.assertNotContains(resp, "Stocktake")
        self.assertNotContains(resp, "QR labels")
        self.assertContains(resp, "Loan history")
        self.assertContains(resp, "On loan")
        self.assertContains(resp, "Not seen")
        self.assertContains(resp, "Tools")

    def test_tools_visible_for_writer(self):
        self.client.login(username="writer", password="x")
        resp = self.client.get(reverse("inventory:search"))
        html = resp.content.decode()
        self.assertContains(resp, "Add item")
        self.assertContains(resp, "QR labels")
        self.assertContains(resp, "Stocktake")
        self.assertContains(resp, "Import")
        add_pos = html.index("Add item")
        labels_pos = html.index("QR labels")
        tools_pos = html.index("Tools")
        self.assertLess(add_pos, tools_pos)
        self.assertLess(labels_pos, tools_pos)
        panel = html[html.index('class="tools-panel"'):]
        self.assertIn("On loan", panel)
        self.assertIn("Not seen", panel)
        self.assertIn("Stocktake", panel)
        self.assertNotIn("Add item", panel)
        self.assertNotIn("QR labels", panel)

    def test_overdue_badge_count(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertContains(resp, 'class="badge-count"')
        self.assertEqual(resp.context["overdue_loan_count"], 1)

    def test_admin_menu_for_staff_only(self):
        User.objects.create_user(username="staff", password="x", is_staff=True)
        self.client.login(username="staff", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertContains(resp, ">Admin</summary>")
        self.assertContains(resp, "Access control")
        self.client.logout()
        self.client.login(username="writer", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertNotContains(resp, ">Admin</summary>")

    def test_mobile_drawer_markup(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:search"))
        self.assertContains(resp, 'class="nav-drawer"')
        self.assertContains(resp, "nav-drawer-toggle")
        self.assertContains(resp, "nav-hamburger")
        self.assertContains(resp, "Menu")

    def test_list_pages_use_block_cards(self):
        self.client.login(username="writer", password="x")
        writer_pages = (
            "inventory:search",
            "inventory:current_loans",
            "inventory:not_seen",
            "inventory:loan_history",
            "inventory:locations",
            "inventory:stocktake",
            "inventory:csv_import",
        )
        for name in writer_pages:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, name)
            self.assertContains(resp, "block-card", msg_prefix=name)
            self.assertContains(resp, 'class="container page"', msg_prefix=name)
        User.objects.create_user(username="aclstaff", password="x", is_staff=True)
        self.client.login(username="aclstaff", password="x")
        for name in ("accounts:access", "accounts:groups"):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 200, name)
            self.assertContains(resp, "block-card", msg_prefix=name)


class SearchChipTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        Location.objects.create(name="Lab")
        self.client = Client()
        self.client.login(username="writer", password="x")

    def test_filter_chip_drops_query_param(self):
        resp = self.client.get(reverse("inventory:search"), {"q": "lens", "on_loan": "1"})
        self.assertContains(resp, "chip-filter")
        self.assertContains(resp, "On loan ×")
        html = resp.content.decode()
        self.assertIn("on_loan=1", html)
        self.assertRegex(html, r'href="\?[^"]*on_loan=1')
        # Removing q keeps on_loan.
        self.assertIn("on_loan", html)

    def test_still_here_partial_has_updated_time(self):
        loc = Location.objects.get(name="Lab")
        item = Item.objects.create(
            name="Cam", location=loc, created_by=self.user, updated_by=self.user
        )
        resp = self.client.post(
            reverse("inventory:still_here", args=[item.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'id="item-status-{item.pk}"')
        self.assertContains(resp, 'id="last-seen"')
        item.refresh_from_db()
        self.assertIsNotNone(item.last_seen_at)


class LabelsUiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        loc = Location.objects.create(name="Lab")
        self.item = Item.objects.create(
            name="Cam", location=loc, created_by=self.user, updated_by=self.user
        )
        self.client = Client()
        self.client.login(username="writer", password="x")

    def test_labels_page_has_filter_markup(self):
        resp = self.client.get(reverse("inventory:labels"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-filter-input")
        self.assertContains(resp, "data-select-visible")
        self.assertContains(resp, "data-filter-text")
        self.assertContains(resp, "label_size")
        self.assertContains(resp, "Generate labels")
        self.assertContains(resp, "Cable flag")
        self.assertContains(resp, "label-sil")
        self.assertContains(resp, "label-sil-flag")
        self.assertContains(resp, "label-sil-body")
        self.assertContains(resp, "label-sil-50x80")
        self.assertContains(resp, "label-sil-40x30")
        self.assertContains(resp, "label-sil-40x20")
        self.assertContains(resp, "label-sil-30x20")
        self.assertNotContains(resp, 'style="width:')

    def test_generate_preview_and_png(self):
        resp = self.client.post(
            reverse("inventory:labels"),
            {"items": [str(self.item.pk)], "label_size": "40x30"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data:image/png;base64,")
        self.assertContains(resp, "Download ZIP")
        self.assertContains(resp, "Download ODS")
        png = self.client.get(
            reverse("inventory:labels_png"),
            {"kind": "item", "id": self.item.pk, "size": "30x20"},
        )
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png["Content-Type"], "image/png")
        self.assertTrue(png.content.startswith(b"\x89PNG"))

    def test_item_detail_qr_dialog(self):
        resp = self.client.get(reverse("inventory:item_detail", args=[self.item.pk]))
        self.assertContains(resp, "QR label")
        self.assertContains(resp, "qr-label-dialog")
        self.assertContains(resp, "label-sil-40x30")
        self.assertNotContains(resp, 'href="#loan"')
        preview = self.client.post(
            reverse("inventory:labels"),
            {"items": [str(self.item.pk)], "label_size": "40x30"},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "data:image/png;base64,")
        self.assertContains(preview, self.item.name)

    def test_zip_and_ods(self):
        data = {"items": [str(self.item.pk)], "label_size": "50x80"}
        zresp = self.client.post(reverse("inventory:labels_zip"), data)
        self.assertEqual(zresp.status_code, 200)
        self.assertTrue(zresp.content.startswith(b"PK"))
        ods = self.client.post(reverse("inventory:labels_ods"), data)
        self.assertEqual(ods.status_code, 200)
        self.assertIn("opendocument.spreadsheet", ods["Content-Type"])
        self.assertTrue(ods.content.startswith(b"PK"))
        self.assertIn(b"content.xml", ods.content)


class CsvImportPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        self.client = Client()
        self.client.login(username="writer", password="x")

    def test_import_page_layout(self):
        resp = self.client.get(reverse("inventory:csv_import"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "add-inline")
        self.assertContains(resp, "import-columns")
        self.assertContains(resp, "Preview import")
        self.assertContains(resp, "location_path")
        self.assertContains(resp, "installed_in")

    def test_preview_and_confirm_without_reupload(self):
        csv_body = b"name,location_path\nScope,Lab\n"
        resp = self.client.post(
            reverse("inventory:csv_import"),
            {"file": SimpleUploadedFile("items.csv", csv_body, content_type="text/csv")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "chip-available")
        self.assertContains(resp, "Confirm import")
        self.assertContains(resp, 'name="csv_text"')
        self.assertFalse(Item.objects.filter(name="Scope").exists())
        confirm = self.client.post(
            reverse("inventory:csv_import"),
            {"confirm": "1", "csv_text": csv_body.decode()},
        )
        self.assertEqual(confirm.status_code, 302)
        self.assertTrue(Item.objects.filter(name="Scope").exists())


class RelativeDueTests(TestCase):
    def test_relative_due_wording(self):
        today = date.today()
        self.assertEqual(relative_due(today), "due today")
        self.assertEqual(relative_due(today + timedelta(days=3)), "due in 3 days")
        self.assertEqual(relative_due(today - timedelta(days=1)), "overdue 1 day")
