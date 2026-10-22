import sys

from django.core.management.base import BaseCommand

from inventory.container_migration import build_plan, write_plan


class Command(BaseCommand):
    help = (
        "Propose how the old free-text containers become container items. Writes a CSV "
        "to review and edit; apply it with container_apply (see inventory/container_migration.py)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--out", default="", help="CSV file to write (default: stdout)")

    def handle(self, *args, **options):
        rows = build_plan()
        if options["out"]:
            with open(options["out"], "w", newline="", encoding="utf-8") as fh:
                write_plan(rows, fh)
            texts = sum(1 for r in rows if r["kind"] == "text")
            self.stdout.write(
                f"Wrote {texts} container texts and {len(rows) - texts} item rows to {options['out']}."
            )
        else:
            write_plan(rows, sys.stdout)
