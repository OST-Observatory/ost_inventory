from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from inventory.images import delete_photo_file
from inventory.models import Item

PHOTO_DIR = "items"


def _walk(storage, path):
    dirs, files = storage.listdir(path)
    for name in files:
        yield f"{path}/{name}"
    for name in dirs:
        yield from _walk(storage, f"{path}/{name}")


class Command(BaseCommand):
    help = (
        "Delete photo files under media/items/ that no item refers to, together with "
        "their thumbnails (left over from deletions before inventory.signals existed)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        storage = default_storage
        if not storage.exists(PHOTO_DIR):
            self.stdout.write("No photo directory.")
            return
        referenced = set(Item.objects.exclude(photo="").values_list("photo", flat=True))

        orphans = []
        for name in _walk(storage, PHOTO_DIR):
            if name in referenced:
                continue
            # easy-thumbnails names variants "<source>.<options>.<ext>".
            if any(name.startswith(f"{ref}.") for ref in referenced):
                continue
            orphans.append(name)

        # Delete originals first; their thumbnails go with them (files and cache rows).
        for name in sorted(orphans, key=len):
            if not options["dry_run"] and storage.exists(name):
                delete_photo_file(name, storage)
            self.stdout.write(f"{'would delete' if options['dry_run'] else 'deleted'}: {name}")

        prefix = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {len(orphans)} orphaned file(s)."))
