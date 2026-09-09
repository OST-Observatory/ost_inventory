from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.http import Http404
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.ldap_setup import bind_ldap_connection
from config.security_checks import (
    is_insecure_secret_key,
    ldap_tls_is_required,
    normalize_django_env,
    validate_production_settings,
)
from inventory.csv_utils import sanitize_csv_cell
from inventory.forms import ItemForm
from inventory.management.commands.import_inventory import parse_csv
from inventory.models import Item, Loan, Location
from inventory.views.media import _safe_media_path

User = get_user_model()


class SecurityCheckTests(TestCase):
    def test_django_env_rejects_unknown(self):
        with self.assertRaises(ImproperlyConfigured):
            normalize_django_env("staging")

    def test_placeholder_secret_is_insecure(self):
        self.assertTrue(is_insecure_secret_key("change-me-in-production-use-a-long-random-string"))
        self.assertTrue(is_insecure_secret_key("short"))
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(
                secret_key="dev-only-insecure-secret-key-change-me",
                debug=False,
                allowed_hosts=["inventory.example.edu"],
                databases={"default": {"ENGINE": "django.db.backends.postgresql"}},
            )

    def test_production_requires_hosts_and_postgres(self):
        key = "a" * 50
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(
                secret_key=key,
                debug=True,
                allowed_hosts=["x"],
                databases={"default": {"ENGINE": "django.db.backends.postgresql"}},
            )
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(
                secret_key=key,
                debug=False,
                allowed_hosts=[],
                databases={"default": {"ENGINE": "django.db.backends.postgresql"}},
            )
        with self.assertRaises(ImproperlyConfigured):
            validate_production_settings(
                secret_key=key,
                debug=False,
                allowed_hosts=["x"],
                databases={"default": {"ENGINE": "django.db.backends.sqlite3"}},
            )

    def test_production_ldap_forbids_cleartext(self):
        with self.assertRaises(ImproperlyConfigured):
            ldap_tls_is_required("ldap://ldap.example.edu", False, "production")
        ldap_tls_is_required("ldaps://ldap.example.edu", False, "production")
        ldap_tls_is_required("ldap://ldap.example.edu", True, "production")
        ldap_tls_is_required("ldap://ldap.example.edu", False, "development")


class LdapTlsTests(TestCase):
    def test_starttls_failure_does_not_bind(self):
        ldap_module = MagicMock()
        conn = MagicMock()
        conn.start_tls_s.side_effect = Exception("tls fail")
        ldap_module.initialize.return_value = conn
        ldap_module.OPT_REFERRALS = 0
        ldap_module.OPT_NETWORK_TIMEOUT = 1
        ldap_module.OPT_X_TLS_REQUIRE_CERT = 2
        ldap_module.OPT_X_TLS_DEMAND = 3
        ldap_module.OPT_X_TLS_CACERTFILE = 4
        ldap_module.OPT_X_TLS_NEWCTX = 5

        result = bind_ldap_connection(
            ldap_module,
            "ldap://example",
            start_tls=True,
            bind_dn="cn=bind",
            bind_password="secret",
        )
        self.assertIsNone(result)
        conn.simple_bind_s.assert_not_called()


class MediaAccessTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student", password="x", is_student=True
        )
        self.rel = Path("items") / "probe.bin"
        self.abs = Path(settings.MEDIA_ROOT) / self.rel
        self.abs.parent.mkdir(parents=True, exist_ok=True)
        self.abs.write_bytes(b"inventory-photo")
        self.url = reverse("protected_media", kwargs={"path": self.rel.as_posix()})
        self.client = Client()

    def test_anonymous_redirected(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)

    def test_student_can_read(self):
        self.client.login(username="student", password="x")
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

    def test_traversal_rejected(self):
        with self.assertRaises(Http404):
            _safe_media_path("../settings.py")


class PiiAndInactiveTests(TestCase):
    def setUp(self):
        self.writer = User.objects.create_user(
            username="writer", password="x", is_supervisor=True
        )
        self.reader = User.objects.create_user(
            username="reader", password="x", is_student=True
        )
        self.loc = Location.objects.create(name="Lab")
        self.item = Item.objects.create(
            name="Camera",
            location=self.loc,
            created_by=self.writer,
            updated_by=self.writer,
        )
        self.inactive = Item.objects.create(
            name="Retired",
            location=self.loc,
            is_active=False,
            created_by=self.writer,
            updated_by=self.writer,
        )
        Loan.objects.create(
            item=self.item,
            borrower_name="Guest Scientist",
            borrower_contact="secret-contact@example.com",
            due_date=date.today() + timedelta(days=7),
            recorded_by=self.writer,
        )
        self.client = Client()

    def test_student_does_not_see_borrower_contact(self):
        self.client.login(username="reader", password="x")
        detail = self.client.get(reverse("inventory:item_detail", args=[self.item.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "secret-contact@example.com")
        self.assertNotContains(detail, "Guest Scientist")
        loans = self.client.get(reverse("inventory:current_loans"))
        self.assertNotContains(loans, "secret-contact@example.com")

    def test_supervisor_sees_borrower_contact(self):
        self.client.login(username="writer", password="x")
        detail = self.client.get(reverse("inventory:item_detail", args=[self.item.pk]))
        self.assertContains(detail, "secret-contact@example.com")

    def test_student_cannot_open_inactive_or_export_it(self):
        self.client.login(username="reader", password="x")
        resp = self.client.get(reverse("inventory:item_detail", args=[self.inactive.pk]))
        self.assertEqual(resp.status_code, 404)
        export = self.client.get(reverse("inventory:export_csv") + "?inactive=1")
        self.assertEqual(export.status_code, 200)
        self.assertNotIn(b"Retired", export.content)

    def test_supervisor_can_open_inactive(self):
        self.client.login(username="writer", password="x")
        resp = self.client.get(reverse("inventory:item_detail", args=[self.inactive.pk]))
        self.assertEqual(resp.status_code, 200)


class CsvSecurityTests(TestCase):
    def test_formula_sanitizer(self):
        self.assertEqual(sanitize_csv_cell("=cmd"), "'=cmd")
        self.assertEqual(sanitize_csv_cell(" +hi"), "' +hi")
        self.assertEqual(sanitize_csv_cell("normal"), "normal")
        self.assertEqual(sanitize_csv_cell("@sum"), "'@sum")

    def test_row_limit(self):
        header = "name,location_path\n"
        body = "".join(f"n{i},Lab\n" for i in range(5))
        with override_settings(CSV_IMPORT_MAX_ROWS=3):
            with self.assertRaises(CommandError):
                parse_csv(StringIO(header + body))


class PhotoLimitTests(TestCase):
    def setUp(self):
        self.loc = Location.objects.create(name="Lab")
        User.objects.create_user(username="w", password="x", is_supervisor=True)

    def test_rejects_oversize_upload(self):
        from io import BytesIO
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), "red").save(buf, format="JPEG")
        data = {
            "name": "Scope",
            "room": self.loc.pk,
            "quantity": 1,
            "category_1": "Optics",
            "description": "",
            "comment": "",
        }
        photo = SimpleUploadedFile("big.jpg", buf.getvalue(), content_type="image/jpeg")
        with override_settings(PHOTO_MAX_BYTES=10):
            form = ItemForm(data=data, files={"photo": photo})
            self.assertFalse(form.is_valid())
            self.assertIn("photo", form.errors)


class LoginThrottleTests(TestCase):
    def setUp(self):
        User.objects.create_user(username="target", password="correct", is_student=True)
        self.client = Client()

    def test_lockout_after_failures(self):
        with override_settings(LOGIN_MAX_FAILURES=3, LOGIN_FAILURE_WINDOW=600, LOGIN_LOCKOUT_SECONDS=900):
            url = reverse("login")
            for _ in range(3):
                self.client.post(url, {"username": "target", "password": "wrong"})
            resp = self.client.post(url, {"username": "target", "password": "wrong"})
            self.assertEqual(resp.status_code, 429)


class ReminderTests(TestCase):
    def setUp(self):
        self.writer = User.objects.create_user(
            username="writer",
            password="x",
            is_supervisor=True,
            email="writer@example.com",
        )
        loc = Location.objects.create(name="Lab")
        self.item_ok = Item.objects.create(
            name="OkItem", location=loc, created_by=self.writer, updated_by=self.writer
        )
        self.item_bad = Item.objects.create(
            name="BadItem", location=loc, created_by=self.writer, updated_by=self.writer
        )
        yesterday = date.today() - timedelta(days=1)
        self.loan_ok = Loan.objects.create(
            item=self.item_ok,
            borrower_name="A",
            borrower_contact="a@example.com",
            due_date=yesterday,
            recorded_by=self.writer,
        )
        self.loan_bad = Loan.objects.create(
            item=self.item_bad,
            borrower_name="B",
            borrower_contact="b@example.com",
            due_date=yesterday,
            recorded_by=self.writer,
        )

    def test_dry_run_hides_addresses(self):
        out = StringIO()
        call_command("send_overdue_reminders", dry_run=True, stdout=out)
        text = out.getvalue()
        self.assertNotIn("@", text)
        self.assertIn(str(self.loan_ok.pk), text)

    @patch("inventory.management.commands.send_overdue_reminders.send_mail")
    def test_one_failure_does_not_stop_batch(self, mocked):
        def _send(*args, **kwargs):
            recipients = args[3] if len(args) > 3 else kwargs.get("recipient_list", [])
            if "b@example.com" in recipients:
                raise RuntimeError("smtp down")
            return 1

        mocked.side_effect = _send
        err = StringIO()
        out = StringIO()
        call_command("send_overdue_reminders", stdout=out, stderr=err)
        self.loan_ok.refresh_from_db()
        self.loan_bad.refresh_from_db()
        self.assertIsNotNone(self.loan_ok.last_reminder_sent_at)
        self.assertIsNone(self.loan_bad.last_reminder_sent_at)
        self.assertIn("failed", err.getvalue().lower())
