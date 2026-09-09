from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
import logging

from inventory.models import Loan

logger = logging.getLogger(__name__)


def _looks_like_email(value: str) -> bool:
    value = (value or "").strip()
    return "@" in value and "." in value.split("@")[-1]


class Command(BaseCommand):
    help = "Send overdue loan reminder emails (safe to run daily)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        today = timezone.localdate()
        overdue = Loan.objects.filter(
            returned_at__isnull=True,
            due_date__lt=today,
        ).select_related("item", "recorded_by")

        sent = 0
        failed = 0
        for loan in overdue:
            try:
                if loan.last_reminder_sent_at and loan.last_reminder_sent_at.date() == today:
                    continue
                recipients = set()
                if loan.recorded_by and loan.recorded_by.email:
                    recipients.add(loan.recorded_by.email)
                if _looks_like_email(loan.borrower_contact):
                    recipients.add(loan.borrower_contact.strip())
                if not recipients:
                    self.stdout.write(f"Skip loan {loan.pk}: no email recipients")
                    continue

                subject = f"[Inventory] Overdue: {loan.item.inventory_number} {loan.item.name}"
                body = (
                    f"Item {loan.item.inventory_number} ({loan.item.name}) is overdue.\n"
                    f"Borrower: {loan.borrower_name}\n"
                    f"Due date: {loan.due_date}\n"
                    f"Contact: {loan.borrower_contact}\n"
                )
                if options["dry_run"]:
                    self.stdout.write(
                        f"DRY RUN would mail {len(recipients)} recipient(s) for loan {loan.pk}"
                    )
                    continue

                send_mail(
                    subject,
                    body,
                    settings.DEFAULT_FROM_EMAIL,
                    list(recipients),
                    fail_silently=False,
                )
                loan.last_reminder_sent_at = timezone.now()
                loan.save(update_fields=["last_reminder_sent_at"])
                sent += 1
            except Exception:
                failed += 1
                logger.exception("Reminder failed for loan %s", loan.pk)
                self.stderr.write(f"Loan {loan.pk}: send failed")

        self.stdout.write(self.style.SUCCESS(f"Reminders sent: {sent}"))
        if failed:
            self.stderr.write(f"Reminders failed: {failed}")
