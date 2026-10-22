from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from inventory.container_migration import apply_plan, read_plan

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Apply a reviewed container plan (from container_plan). Without --commit nothing "
        "is saved; the output shows every change."
    )

    def add_arguments(self, parser):
        parser.add_argument("plan", help="CSV written by container_plan, after review")
        parser.add_argument("--commit", action="store_true", help="Save the changes")
        parser.add_argument(
            "--user",
            default="",
            help="Username recorded as creator/editor (default: first superuser)",
        )

    def handle(self, *args, **options):
        username = options["user"]
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User not found: {username}")
        else:
            user = User.objects.filter(is_superuser=True).first() or User.objects.first()
            if not user:
                raise CommandError("No user available; create a user first.")
        with open(options["plan"], newline="", encoding="utf-8-sig") as fh:
            rows = read_plan(fh)
        result = apply_plan(rows, user, commit=options["commit"])
        for line in result.changes:
            self.stdout.write(f"  {line}")
        for line in result.warnings:
            self.stdout.write(self.style.WARNING(f"warning: {line}"))
        for line in result.errors:
            self.stdout.write(self.style.ERROR(f"error: {line}"))
        self.stdout.write(
            f"{result.containers_linked} items become containers, "
            f"{result.containers_created} new containers, "
            f"{result.items_changed} items change, {result.moved} of them change place."
        )
        if result.errors:
            raise CommandError("Nothing was saved; fix the errors above.")
        if options["commit"]:
            self.stdout.write(self.style.SUCCESS("Saved."))
        else:
            self.stdout.write(
                "Dry run: nothing saved (numbers of new containers will differ). "
                "Add --commit to apply."
            )
