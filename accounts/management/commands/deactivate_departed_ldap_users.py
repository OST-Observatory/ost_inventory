from django.core.management.base import BaseCommand, CommandError

from accounts.departed import (
    LdapUnavailable,
    SafetyStop,
    deactivate_departed_users,
    ldap_configured,
    ldap_entry_lookup,
)


class Command(BaseCommand):
    help = (
        "Deactivate accounts whose LDAP entry is gone and clear their name and e-mail "
        "(safe to run daily; any LDAP error aborts without changes)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Apply even if more than half of the LDAP accounts would be deactivated.",
        )

    def handle(self, *args, **options):
        if not ldap_configured():
            self.stdout.write("LDAP is not configured; nothing to check.")
            return
        try:
            with ldap_entry_lookup() as exists:
                result = deactivate_departed_users(
                    exists, dry_run=options["dry_run"], force=options["force"]
                )
        except (LdapUnavailable, SafetyStop) as exc:
            raise CommandError(f"{exc} — no accounts were changed.") from exc

        verb = "Would deactivate" if options["dry_run"] else "Deactivated"
        names = ", ".join(result.departed) or "none"
        self.stdout.write(self.style.SUCCESS(
            f"Checked {result.checked} LDAP account(s). {verb} {len(result.departed)}: {names}"
        ))
