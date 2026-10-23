from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.management.commands.purge_personal_data import ANONYMISED
from inventory.models import Borrowing, Category, Item, Loan, Location

User = get_user_model()


class BorrowingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="writer", password="x", is_supervisor=True, email="writer@example.com"
        )
        self.dome = Location.objects.create(name="Dome")
        Category.objects.create(name="Telescope")
        self.client = Client()
        self.client.login(username="writer", password="x")

    def make(self, name, **extra):
        return Item.objects.create(
            name=name, location=self.dome, created_by=self.user, updated_by=self.user, **extra
        )

    def borrow(self, item, due=None):
        return Borrowing.objects.create(
            item=item, lender_name="Dr. Lens", lender_contact="lens@example.org",
            due_date=due, recorded_by=self.user,
        )

    def test_add_item_as_borrowed(self):
        resp = self.client.post(
            reverse("inventory:item_create"),
            {
                "name": "Celestron C8 (colleague)",
                "room": self.dome.pk,
                "quantity": 1,
                "category_1": "Telescope",
                "borrow-lender_name": "Dr. Lens",
                "borrow-lender_contact": "lens@example.org",
                "borrow-due_date": "",
            },
        )
        self.assertEqual(resp.status_code, 302)
        scope = Item.objects.get(name="Celestron C8 (colleague)")
        self.assertTrue(scope.is_borrowed)
        self.assertIsNone(scope.current_borrowing.due_date)
        detail = self.client.get(reverse("inventory:item_detail", args=[scope.pk]))
        self.assertContains(detail, "chip-borrowed")
        self.assertContains(detail, "Dr. Lens")
        self.assertContains(detail, "no return date")
        self.assertContains(detail, "Give back")
        self.assertNotContains(detail, "Record loan")

    def test_add_item_without_lender_is_ours(self):
        self.client.post(
            reverse("inventory:item_create"),
            {"name": "Own scope", "room": self.dome.pk, "quantity": 1, "category_1": "Telescope"},
        )
        self.assertFalse(Item.objects.get(name="Own scope").is_borrowed)
        form = self.client.get(reverse("inventory:item_create"))
        self.assertContains(form, "Borrowed from someone else?")

    def test_mark_existing_item_and_no_lending_on(self):
        scope = self.make("C8")
        bad = self.client.post(reverse("inventory:borrowing_create", args=[scope.pk]), {"borrow-lender_name": ""})
        self.assertEqual(bad.status_code, 302)
        self.assertFalse(scope.is_borrowed)
        self.client.post(
            reverse("inventory:borrowing_create", args=[scope.pk]),
            {"borrow-lender_name": "Dr. Lens", "borrow-due_date": "2030-01-31"},
        )
        self.assertEqual(scope.current_borrowing.due_date, date(2030, 1, 31))
        self.client.post(
            reverse("inventory:loan_create", args=[scope.pk]),
            {"borrower_name": "Ada", "due_date": "2030-01-01"},
        )
        self.assertFalse(Loan.objects.filter(item=scope).exists())

    def test_give_back_requires_our_items_off_it(self):
        scope = self.make("C8")
        borrowing = self.borrow(scope)
        adapter = self.make("M68 adapter", installed_in=scope)
        camera = self.make("QHY268M", installed_in=adapter)
        url = reverse("inventory:borrowing_give_back", args=[borrowing.pk])
        resp = self.client.post(url, follow=True)
        self.assertContains(resp, "Take off or out our items first")
        self.assertContains(resp, adapter.inventory_number)
        scope.refresh_from_db()
        self.assertTrue(scope.is_active)

        for part in (camera, adapter):
            part.installed_in = None
            part.save()
        self.client.post(url)
        scope.refresh_from_db()
        borrowing.refresh_from_db()
        self.assertFalse(scope.is_active)
        self.assertIsNotNone(borrowing.returned_at)
        self.assertIn("Given back to its owner", scope.notes)

    def test_lender_hidden_without_permission(self):
        scope = self.make("C8")
        self.borrow(scope)
        User.objects.create_user(username="student", password="x", is_student=True)
        self.client.login(username="student", password="x")
        detail = self.client.get(reverse("inventory:item_detail", args=[scope.pk]))
        self.assertContains(detail, "Borrowed from someone else")
        self.assertNotContains(detail, "Dr. Lens")
        loans = self.client.get(reverse("inventory:current_loans"))
        self.assertContains(loans, scope.inventory_number)
        self.assertNotContains(loans, "Dr. Lens")

    def test_search_filter_list_chip_label_and_export(self):
        scope = self.make("C8")
        self.borrow(scope)
        self.make("Own scope")
        found = self.client.get(reverse("inventory:search"), {"borrowed": "1"})
        self.assertContains(found, scope.inventory_number)
        self.assertNotContains(found, "Own scope")
        self.assertContains(found, "chip-borrowed")
        self.assertEqual(scope.label_title, "BORROWED · C8")
        export = self.client.get(reverse("inventory:export_csv")).content.decode()
        header, *rows = export.strip().splitlines()
        column = header.split(",").index("is_borrowed")
        flags = {r.split(",")[2]: r.split(",")[column] for r in rows}
        self.assertEqual(flags, {"C8": "yes", "Own scope": ""})

    def test_overdue_borrowing_reminds_recorder_and_counts_in_nav(self):
        late = self.make("Late scope")
        self.borrow(late, due=timezone.localdate() - timedelta(days=1))
        self.borrow(self.make("Open-ended scope"))
        page = self.client.get(reverse("inventory:current_loans"))
        self.assertEqual(page.context["overdue_loan_count"], 1)
        self.assertContains(page, "Borrowed from others")
        self.assertContains(page, "open-ended")
        call_command("send_overdue_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["writer@example.com"])
        self.assertIn(late.inventory_number, mail.outbox[0].subject)
        call_command("send_overdue_reminders", stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(LOAN_RETENTION_DAYS=30)
    def test_lender_data_is_anonymised_after_retention(self):
        old = self.borrow(self.make("Old scope"))
        old.returned_at = timezone.now() - timedelta(days=40)
        old.save()
        recent = self.borrow(self.make("Recent scope"))
        recent.returned_at = timezone.now() - timedelta(days=5)
        recent.save()
        out = StringIO()
        call_command("purge_personal_data", stdout=out)
        old.refresh_from_db()
        recent.refresh_from_db()
        self.assertEqual((old.lender_name, old.lender_contact), (ANONYMISED, ""))
        self.assertEqual(recent.lender_name, "Dr. Lens")
        self.assertIn("1 borrowing(s)", out.getvalue())
