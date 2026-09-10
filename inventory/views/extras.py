import base64
import csv
import io
import zipfile

from django.conf import settings
from django.contrib import messages
from django.core.management.base import CommandError
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from accounts.permissions import import_required, labels_required, read_required, user_can_see_inactive
from inventory.csv_utils import sanitize_csv_cell
from inventory.labels import (
    LABEL_SIZE_LIST,
    LABEL_SIZE_SESSION_KEY,
    get_label_size,
    png_filename,
    render_label_png,
)
from inventory.models import Item, Location
from inventory.ods import spreadsheet_bytes
from inventory.policy import visible_items
from inventory.search import filter_items


def _absolute_url(request, path: str) -> str:
    return request.build_absolute_uri(path)


def _selected_label_jobs(request):
    size = get_label_size(request.POST.get("label_size") or request.GET.get("size"))
    request.session[LABEL_SIZE_SESSION_KEY] = size.key
    item_ids = request.POST.getlist("items") or request.GET.getlist("items")
    loc_ids = request.POST.getlist("locations") or request.GET.getlist("locations")
    items = list(
        Item.objects.filter(pk__in=item_ids, is_active=True).select_related(
            "location", "location__parent"
        )
    )
    locations = list(Location.objects.filter(pk__in=loc_ids).select_related("parent"))
    jobs = []
    for item in items:
        url = _absolute_url(request, reverse("item_short", kwargs={"pk": item.pk}))
        png = render_label_png(
            url, item.name, item.inventory_number, item.location.path_display(), size
        )
        jobs.append(
            {
                "kind": "item",
                "pk": item.pk,
                "title": item.name,
                "subtitle": item.inventory_number,
                "extra": item.location.path_display(),
                "url": url,
                "filename": png_filename(f"item-{item.pk:04d}", size),
                "png": png,
            }
        )
    for loc in locations:
        url = _absolute_url(request, reverse("location_short", kwargs={"pk": loc.pk}))
        path = loc.path_display()
        png = render_label_png(url, loc.name, path, "", size)
        jobs.append(
            {
                "kind": "location",
                "pk": loc.pk,
                "title": loc.name,
                "subtitle": path,
                "extra": "",
                "url": url,
                "filename": png_filename(f"loc-{loc.pk}", size),
                "png": png,
            }
        )
    return size, jobs


def _labels_form_context(request, extra=None):
    ctx = {
        "items": Item.objects.filter(is_active=True).order_by("name"),
        "locations": Location.objects.select_related("parent").order_by("name"),
        "label_sizes": LABEL_SIZE_LIST,
        "selected_size": request.session.get(LABEL_SIZE_SESSION_KEY, "40x30"),
    }
    if extra:
        ctx.update(extra)
    return ctx


@read_required
@require_GET
def export_csv(request):
    qs = visible_items(
        request.user,
        Item.objects.select_related("location", "location__parent", "project", "installed_in").prefetch_related("categories"),
    )
    qs = filter_items(
        qs,
        q=request.GET.get("q", ""),
        category=request.GET.get("category", ""),
        location=request.GET.get("location", ""),
        project=request.GET.get("project", ""),
        container=request.GET.get("container", ""),
        on_loan=request.GET.get("on_loan") == "1",
        include_inactive=request.GET.get("inactive") == "1" and user_can_see_inactive(request.user),
    )
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="inventory_export.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "id",
            "inventory_number",
            "name",
            "description",
            "quantity",
            "quantity_approximate",
            "location_path",
            "container",
            "installed_in",
            "categories",
            "project",
            "comment",
            "is_active",
            "last_seen_at",
        ]
    )
    for item in qs.iterator(chunk_size=200):
        writer.writerow(
            [
                item.pk,
                sanitize_csv_cell(item.inventory_number),
                sanitize_csv_cell(item.name),
                sanitize_csv_cell(item.description),
                item.quantity,
                "yes" if item.quantity_is_approximate else "",
                sanitize_csv_cell(item.location.path_display()),
                sanitize_csv_cell(item.container),
                sanitize_csv_cell(item.installed_in.inventory_number if item.installed_in_id else ""),
                sanitize_csv_cell(";".join(c.name for c in item.categories.all())),
                sanitize_csv_cell(item.project.name if item.project else ""),
                sanitize_csv_cell(item.comment),
                item.is_active,
                item.last_seen_at.isoformat() if item.last_seen_at else "",
            ]
        )
    return response


@labels_required
@require_http_methods(["GET", "POST"])
def labels_page(request):
    if request.method == "GET":
        return render(request, "inventory/labels.html", _labels_form_context(request))
    size, jobs = _selected_label_jobs(request)
    if not jobs:
        messages.error(request, "Select at least one item or location.")
        return render(request, "inventory/labels.html", _labels_form_context(request))
    previews = []
    for job in jobs:
        previews.append(
            {
                **{k: v for k, v in job.items() if k != "png"},
                "data_uri": "data:image/png;base64," + base64.b64encode(job["png"]).decode("ascii"),
            }
        )
    return render(
        request,
        "inventory/labels_preview.html",
        {
            "size": size,
            "labels": previews,
            "item_ids": request.POST.getlist("items"),
            "location_ids": request.POST.getlist("locations"),
        },
    )


@labels_required
@require_http_methods(["GET", "POST"])
def labels_zip(request):
    _size, jobs = _selected_label_jobs(request)
    if not jobs:
        return HttpResponseBadRequest("Select at least one item or location.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for job in jobs:
            zf.writestr(job["filename"], job["png"])
    buf.seek(0)
    response = HttpResponse(buf.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="qr-labels.zip"'
    return response


@labels_required
@require_http_methods(["GET", "POST"])
def labels_ods(request):
    size, jobs = _selected_label_jobs(request)
    if not jobs:
        return HttpResponseBadRequest("Select at least one item or location.")
    rows = [[job["url"], job["title"], job["subtitle"], size.key] for job in jobs]
    payload = spreadsheet_bytes(["qr_url", "title", "subtitle", "label_size"], rows)
    response = HttpResponse(
        payload,
        content_type="application/vnd.oasis.opendocument.spreadsheet",
    )
    response["Content-Disposition"] = 'attachment; filename="qr-labels.ods"'
    return response


@labels_required
@require_GET
def labels_png(request):
    size = get_label_size(request.GET.get("size"))
    kind = request.GET.get("kind")
    pk = request.GET.get("id")
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid id.")
    if kind == "item":
        item = get_object_or_404(Item, pk=pk, is_active=True)
        url = _absolute_url(request, reverse("item_short", kwargs={"pk": item.pk}))
        png = render_label_png(
            url, item.name, item.inventory_number, item.location.path_display(), size
        )
        filename = png_filename(f"item-{item.pk:04d}", size)
    elif kind == "location":
        loc = get_object_or_404(Location, pk=pk)
        url = _absolute_url(request, reverse("location_short", kwargs={"pk": loc.pk}))
        png = render_label_png(url, loc.name, loc.path_display(), "", size)
        filename = png_filename(f"loc-{loc.pk}", size)
    else:
        return HttpResponseBadRequest("Invalid kind.")
    response = HttpResponse(png, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _csv_text_from_request(request) -> str:
    max_bytes = getattr(settings, "CSV_IMPORT_MAX_BYTES", 2 * 1024 * 1024)
    upload = request.FILES.get("file")
    if upload:
        if upload.size is not None and upload.size > max_bytes:
            raise ValueError("CSV file is too large (max 2 MB).")
        return upload.read().decode("utf-8-sig")
    posted = request.POST.get("csv_text")
    if posted:
        if len(posted.encode("utf-8")) > max_bytes:
            raise ValueError("CSV file is too large (max 2 MB).")
        return posted
    raise ValueError("Please choose a CSV file.")


@import_required
@require_http_methods(["GET", "POST"])
def csv_import_preview(request):
    """Simple web CSV import with preview (django-import-export also via admin)."""
    from inventory.management.commands.import_inventory import import_rows, parse_csv

    if request.method == "GET":
        return render(request, "inventory/csv_import.html")

    try:
        text = _csv_text_from_request(request)
        rows = parse_csv(io.StringIO(text))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("inventory:csv_import")
    except (CommandError, UnicodeDecodeError) as exc:
        messages.error(request, str(exc))
        return redirect("inventory:csv_import")

    dry_run = request.POST.get("confirm") != "1"
    result = import_rows(rows, user=request.user, dry_run=dry_run)
    if dry_run:
        preview_rows = result["preview"]
        return render(
            request,
            "inventory/csv_import.html",
            {
                "preview": result,
                "csv_text": text,
                "create_count": sum(1 for row in preview_rows if row["action"] == "create"),
                "update_count": sum(1 for row in preview_rows if row["action"] == "update"),
            },
        )
    messages.success(
        request,
        f"Import done: {result['created']} created, {result['updated']} updated, "
        f"{len(result['errors'])} errors.",
    )
    return redirect("inventory:search")
