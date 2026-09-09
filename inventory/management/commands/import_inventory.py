import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from inventory.models import MAX_CATEGORIES, Category, Item, Location, Project


REQUIRED = {"name", "location_path"}
_TRUE_VALUES = {"1", "true", "yes", "y", "approx", "approximate"}


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() in _TRUE_VALUES


def _limits():
    return {
        "max_rows": getattr(settings, "CSV_IMPORT_MAX_ROWS", 2000),
        "max_field": getattr(settings, "CSV_IMPORT_MAX_FIELD_LENGTH", 500),
        "max_depth": getattr(settings, "CSV_IMPORT_MAX_LOCATION_DEPTH", 2),
        "max_bytes": getattr(settings, "CSV_IMPORT_MAX_BYTES", 2 * 1024 * 1024),
    }


def parse_csv(stream):
    limits = _limits()
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise CommandError("CSV has no header row.")
    headers = {h.strip() for h in reader.fieldnames if h}
    missing = REQUIRED - headers
    if missing:
        raise CommandError(f"Missing required columns: {', '.join(sorted(missing))}")
    rows = []
    for i, row in enumerate(reader, start=2):
        if len(rows) >= limits["max_rows"]:
            raise CommandError(f"CSV exceeds {limits['max_rows']} data rows.")
        cleaned = {}
        for k, v in row.items():
            key = (k or "").strip()
            val = (v or "").strip()
            if len(val) > limits["max_field"]:
                raise CommandError(
                    f"Line {i}: field {key!r} exceeds {limits['max_field']} characters."
                )
            cleaned[key] = val
        cleaned["_line"] = i
        rows.append(cleaned)
    return rows


def get_or_create_location_path(path: str):
    limits = _limits()
    parts = [p.strip() for p in path.replace("\\", "/").split("/") if p.strip()]
    if not parts:
        raise ValueError("Empty location_path")
    if len(parts) > limits["max_depth"]:
        raise ValueError("location_path should be Room or Room/Place")
    room, _ = Location.get_or_create_room(parts[0])
    if len(parts) == 1:
        return room
    place, _ = Location.get_or_create_place(room, parts[1])
    return place


def import_rows(rows, *, user, dry_run=True):
    created = 0
    updated = 0
    errors = []
    preview = []

    def process():
        nonlocal created, updated
        for row in rows:
            line = row.get("_line", "?")
            name = row.get("name", "").strip()
            location_path = row.get("location_path", "").strip()
            if not name or not location_path:
                errors.append({"line": line, "error": "name and location_path are required"})
                continue
            try:
                location = get_or_create_location_path(location_path)
            except Exception as exc:
                errors.append({"line": line, "error": f"location: {exc}"})
                continue

            quantity_raw = row.get("quantity", "").strip() or "1"
            try:
                quantity = int(quantity_raw)
                if quantity < 1:
                    raise ValueError("quantity must be >= 1")
            except ValueError as exc:
                errors.append({"line": line, "error": str(exc)})
                continue

            project = None
            project_name = row.get("project", "").strip()
            if project_name:
                project, _ = Project.get_or_create_by_name(project_name)

            container = row.get("container", "").strip()
            approx_raw = row.get("quantity_approximate", "").strip()
            quantity_is_approximate = _as_bool(approx_raw) if approx_raw else None

            names = []
            seen = set()
            cats_raw = row.get("categories", "").strip()
            type_name = row.get("item_type", "").strip()
            for cname in [c.strip() for c in cats_raw.split(";") if c.strip()] + (
                [type_name] if type_name else []
            ):
                key = cname.lower()
                if key in seen:
                    continue
                seen.add(key)
                names.append(cname)
            if len(names) > MAX_CATEGORIES:
                errors.append(
                    {"line": line, "error": f"at most {MAX_CATEGORIES} categories"}
                )
                continue
            categories = []
            for cname in names:
                cat, _ = Category.get_or_create_by_name(cname)
                if cat:
                    categories.append(cat)

            existing = (
                Item.objects.filter(name=name, location=location, is_active=True)
                .order_by("pk")
                .first()
            )
            action = "update" if existing else "create"
            preview.append(
                {
                    "line": line,
                    "action": action,
                    "name": name,
                    "location": location.path_display(),
                }
            )
            if dry_run:
                continue

            if existing:
                existing.description = row.get("description", existing.description)
                existing.quantity = quantity
                if "project" in row:
                    existing.project = project
                if "container" in row:
                    existing.container = container
                if quantity_is_approximate is not None:
                    existing.quantity_is_approximate = quantity_is_approximate
                existing.comment = row.get("comment", existing.comment)
                existing.updated_by = user
                existing.save()
                if categories:
                    existing.categories.set(categories)
                updated += 1
            else:
                item = Item.objects.create(
                    name=name,
                    description=row.get("description", ""),
                    quantity=quantity,
                    quantity_is_approximate=bool(quantity_is_approximate),
                    project=project,
                    location=location,
                    container=container,
                    comment=row.get("comment", ""),
                    created_by=user,
                    updated_by=user,
                )
                if categories:
                    item.categories.set(categories)
                created += 1

    with transaction.atomic():
        process()
        if dry_run:
            transaction.set_rollback(True)

    return {
        "created": created,
        "updated": updated,
        "errors": errors,
        "preview": preview,
    }


class Command(BaseCommand):
    help = "Import inventory items from CSV (see plan section 3.1)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to CSV file")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--user",
            default="",
            help="Username for created_by/updated_by (default: first superuser)",
        )

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        limits = _limits()
        if path.stat().st_size > limits["max_bytes"]:
            raise CommandError(f"CSV exceeds {limits['max_bytes']} bytes.")

        username = options["user"]
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                raise CommandError(f"User not found: {username}")
        else:
            user = User.objects.filter(is_superuser=True).first() or User.objects.first()
            if not user:
                raise CommandError("No user available for created_by; create a user first.")

        with path.open(newline="", encoding="utf-8-sig") as fh:
            rows = parse_csv(fh)

        result = import_rows(rows, user=user, dry_run=options["dry_run"])
        self.stdout.write(
            f"{'DRY RUN — ' if options['dry_run'] else ''}"
            f"created={result['created']} updated={result['updated']} "
            f"errors={len(result['errors'])} rows={len(result['preview'])}"
        )
        for err in result["errors"]:
            self.stderr.write(f"Line {err['line']}: {err['error']}")
        if options["dry_run"]:
            for row in result["preview"][:20]:
                self.stdout.write(f"  L{row['line']} {row['action']}: {row['name']} @ {row['location']}")
            if len(result["preview"]) > 20:
                self.stdout.write(f"  … and {len(result['preview']) - 20} more")
