from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from inventory.models import Loan

ANONYMISED = "(anonymised)"


class Command(BaseCommand):
    help = (
        "Anonymise borrower data of loans returned more than LOAN_RETENTION_DAYS ago, "
        "including their admin log entries, and delete expired sessions (safe to run daily)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=settings.LOAN_RETENTION_DAYS)

        loans = Loan.objects.filter(returned_at__lt=cutoff).exclude(borrower_name=ANONYMISED)

        # Admin log rows repeat the borrower name in object_repr (Loan.__str__). Rewrite the
        # rows of anonymised loans and of loans that no longer exist (deleted, or removed with
        # their item) once they are older than the cutoff.
        loan_type = ContentType.objects.get_for_model(Loan)
        loan_logs = LogEntry.objects.filter(content_type=loan_type).exclude(object_repr=ANONYMISED)

        with transaction.atomic():
            target_ids = {str(pk) for pk in loans.values_list("pk", flat=True)}
            target_ids |= {
                str(pk)
                for pk in Loan.objects.filter(borrower_name=ANONYMISED).values_list("pk", flat=True)
            }
            existing_ids = {str(pk) for pk in Loan.objects.values_list("pk", flat=True)}
            stale_logs = loan_logs.filter(
                Q(object_id__in=target_ids)
                | (Q(action_time__lt=cutoff) & ~Q(object_id__in=existing_ids))
            )

            loan_count = loans.count() if dry_run else loans.update(
                borrower_name=ANONYMISED, borrower_contact="", note=""
            )
            log_count = stale_logs.count() if dry_run else stale_logs.update(object_repr=ANONYMISED)

        if not dry_run:
            engine = import_module(settings.SESSION_ENGINE)
            engine.SessionStore.clear_expired()

        prefix = "Would anonymise" if dry_run else "Anonymised"
        self.stdout.write(self.style.SUCCESS(
            f"{prefix} {loan_count} loan(s) and {log_count} admin log entr(y/ies) "
            f"(returned before {cutoff:%Y-%m-%d})."
        ))
        if not dry_run:
            self.stdout.write("Expired sessions cleared.")
