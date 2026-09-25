"""Data protection: loan anonymisation, session cleanup and photo file cleanup."""
from datetime import date, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from easy_thumbnails.files import get_thumbnailer
from PIL import Image

from accounts.models import User
from inventory.images import process_item_photo
from inventory.management.commands.purge_personal_data import ANONYMISED
from inventory.models import Item, Loan, Location


@override_settings(LOAN_RETENTION_DAYS=365)
class PurgePersonalDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="writer", password="x", is_supervisor=True)
        loc = Location.objects.create(name="Lab")
        self.now = timezone.now()

        def loan(name, returned_days_ago):
            item = Item.objects.create(
                name=f"Item {name}", location=loc, created_by=self.user, updated_by=self.user
            )
            returned = None if returned_days_ago is None else self.now - timedelta(days=returned_days_ago)
            return Loan.objects.create(
                item=item,
                borrower_name=name,
                borrower_contact=f"{name.lower()}@example.org",
                note="lab course",
                due_date=date.today(),
                returned_at=returned,
                recorded_by=self.user,
            )

        self.old = loan("Alice", 400)
        self.recent = loan("Bob", 30)
        self.open = loan("Carol", None)

        loan_type = ContentType.objects.get_for_model(Loan)

        def log(obj_id, repr_, days_ago):
            entry = LogEntry.objects.create(
                user=self.user, content_type=loan_type, object_id=str(obj_id),
                object_repr=repr_, action_flag=ADDITION,
            )
            LogEntry.objects.filter(pk=entry.pk).update(action_time=self.now - timedelta(days=days_ago))
            return entry

        self.old_log = log(self.old.pk, str(self.old), 420)
        self.recent_log = log(self.recent.pk, str(self.recent), 60)
        self.deleted_log = log(99999, "Gone → Dave", 500)  # loan deleted long ago

    def test_anonymises_old_returned_loans_and_their_log_entries(self):
        out = StringIO()
        call_command("purge_personal_data", stdout=out)

        self.old.refresh_from_db()
        self.assertEqual(self.old.borrower_name, ANONYMISED)
        self.assertEqual(self.old.borrower_contact, "")
        self.assertEqual(self.old.note, "")
        self.assertIsNotNone(self.old.returned_at)  # dates and item stay
        self.assertEqual(self.old.recorded_by, self.user)

        self.recent.refresh_from_db()
        self.open.refresh_from_db()
        self.assertEqual(self.recent.borrower_name, "Bob")
        self.assertEqual(self.open.borrower_name, "Carol")

        self.old_log.refresh_from_db()
        self.deleted_log.refresh_from_db()
        self.recent_log.refresh_from_db()
        self.assertEqual(self.old_log.object_repr, ANONYMISED)
        self.assertEqual(self.deleted_log.object_repr, ANONYMISED)
        self.assertIn("Bob", self.recent_log.object_repr)
        self.assertIn("Anonymised 1 loan(s) and 2 admin log", out.getvalue())

    def test_dry_run_counts_without_changing(self):
        out = StringIO()
        call_command("purge_personal_data", dry_run=True, stdout=out)
        self.assertIn("Would anonymise 1 loan(s) and 2 admin log", out.getvalue())
        self.old.refresh_from_db()
        self.assertEqual(self.old.borrower_name, "Alice")

    def test_second_run_changes_nothing(self):
        call_command("purge_personal_data", stdout=StringIO())
        out = StringIO()
        call_command("purge_personal_data", stdout=out)
        self.assertIn("Anonymised 0 loan(s) and 0 admin log", out.getvalue())

    def test_expired_sessions_cleared(self):
        expired = SessionStore()
        expired.create()
        Session.objects.filter(session_key=expired.session_key).update(
            expire_date=self.now - timedelta(hours=1)
        )
        call_command("purge_personal_data", stdout=StringIO())
        self.assertFalse(Session.objects.filter(session_key=expired.session_key).exists())


def _photo(color="red"):
    buf = BytesIO()
    Image.new("RGB", (40, 40), color).save(buf, format="JPEG")
    return process_item_photo(SimpleUploadedFile("p.jpg", buf.getvalue(), content_type="image/jpeg"))


class PhotoCleanupTests(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.media = Path(self.tmp.name)
        override = override_settings(MEDIA_ROOT=self.tmp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(self.tmp.cleanup)
        self.user = User.objects.create_user(username="writer", password="x")
        self.loc = Location.objects.create(name="Lab")

    def _item_with_thumbnail(self):
        item = Item.objects.create(
            name="Scope", location=self.loc, created_by=self.user, updated_by=self.user,
            photo=_photo(),
        )
        thumb = get_thumbnailer(item.photo)["list"]
        return item, self.media / item.photo.name, self.media / thumb.name

    def test_deleting_item_removes_photo_and_thumbnails(self):
        with self.captureOnCommitCallbacks(execute=True):
            item, photo, thumb = self._item_with_thumbnail()
        self.assertTrue(photo.exists() and thumb.exists())

        with self.captureOnCommitCallbacks(execute=True):
            item.delete()
        self.assertFalse(photo.exists())
        self.assertFalse(thumb.exists())

    def test_replacing_photo_removes_old_file_and_thumbnails(self):
        with self.captureOnCommitCallbacks(execute=True):
            item, photo, thumb = self._item_with_thumbnail()

        with self.captureOnCommitCallbacks(execute=True):
            item.photo = _photo("blue")
            item.save()
        self.assertFalse(photo.exists())
        self.assertFalse(thumb.exists())
        self.assertTrue((self.media / item.photo.name).exists())

    def test_cleanup_orphan_photos(self):
        with self.captureOnCommitCallbacks(execute=True):
            item, photo, thumb = self._item_with_thumbnail()
        orphan = self.media / "items" / "2020" / "01" / "orphan.jpg"
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"x")
        orphan_thumb = orphan.with_name("orphan.jpg.72x72_q85_crop.jpg")
        orphan_thumb.write_bytes(b"x")

        out = StringIO()
        call_command("cleanup_orphan_photos", dry_run=True, stdout=out)
        self.assertIn("Would delete 2 orphaned file(s)", out.getvalue())
        self.assertTrue(orphan.exists())

        call_command("cleanup_orphan_photos", stdout=StringIO())
        self.assertFalse(orphan.exists())
        self.assertFalse(orphan_thumb.exists())
        self.assertTrue(photo.exists() and thumb.exists())
