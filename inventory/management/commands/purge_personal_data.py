from datetime import timedelta
from importlib import import_module

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from inventory.models import Borrowing, Loan

ANONYMISED = "(anonymised)"


def _anonymise(model, name_field, clear_fields, cutoff, dry_run):
    """Blank the person in rows returned before cutoff. Returns (rows, admin log rows)."""
    rows = model.objects.filter(returned_at__lt=cutoff).exclude(**{name_field: ANONYMISED})

    # Admin log rows repeat the name in object_repr (__str__). Rewrite the rows of
    # anonymised records and of records that no longer exist (deleted, or removed with
    # their item) once they are older than the cutoff.
    content_type = ContentType.objects.get_for_model(model)
    logs = LogEntry.objects.filter(content_type=content_type).exclude(object_repr=ANONYMISED)
    target_ids = {str(pk) for pk in rows.values_list("pk", flat=True)}
    target_ids |= {
        str(pk)
        for pk in model.objects.filter(**{name_field: ANONYMISED}).values_list("pk", flat=True)
    }
    existing_ids = {str(pk) for pk in model.objects.values_list("pk", flat=True)}
    stale_logs = logs.filter(
        Q(object_id__in=target_ids) | (Q(action_time__lt=cutoff) & ~Q(object_id__in=existing_ids))
    )
    if dry_run:
        return rows.count(), stale_logs.count()
    count = rows.update(**{name_field: ANONYMISED}, **{f: "" for f in clear_fields})
    return count, stale_logs.update(object_repr=ANONYMISED)


class Command(BaseCommand):
    help = (
        "Anonymise borrower data of loans and lender data of borrowings returned more than "
        "LOAN_RETENTION_DAYS ago, including their admin log entries, and delete expired "
        "sessions (safe to run daily)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        cutoff = timezone.now() - timedelta(days=settings.LOAN_RETENTION_DAYS)

        with transaction.atomic():
            loan_count, loan_logs = _anonymise(
                Loan, "borrower_name", ("borrower_contact", "note"), cutoff, dry_run
            )
            borrowing_count, borrowing_logs = _anonymise(
                Borrowing, "lender_name", ("lender_contact", "note"), cutoff, dry_run
            )
        log_count = loan_logs + borrowing_logs

        if not dry_run:
            engine = import_module(settings.SESSION_ENGINE)
            engine.SessionStore.clear_expired()

        prefix = "Would anonymise" if dry_run else "Anonymised"
        self.stdout.write(self.style.SUCCESS(
            f"{prefix} {loan_count} loan(s), {borrowing_count} borrowing(s) and "
            f"{log_count} admin log entr(y/ies) "
            f"(returned before {cutoff:%Y-%m-%d})."
        ))
        if not dry_run:
            self.stdout.write("Expired sessions cleared.")
