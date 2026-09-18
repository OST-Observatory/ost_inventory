import base64
import csv
import io
import zipfile

from django.conf import settings
from django.contrib import messages
from django.core.management.base import CommandError
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from accounts.permissions import import_required, labels_required, read_required, user_can_see_inactive
from inventory.csv_utils import sanitize_csv_cell
from inventory.labels import (
    LABEL_CODE_SESSION_KEY,
    LABEL_SIZE_LIST,
    LABEL_SIZE_SESSION_KEY,
    get_label_code,
    get_label_size,
    png_filename,
    render_label_png,
)
from inventory.models import Item, Location
from inventory.ods import spreadsheet_bytes
from inventory.printing import PWG_RASTER_FORMAT, PrintError, ipp_print_job, png_to_pwg_raster
from inventory.policy import visible_items
from inventory.scan import resolve_scan_target
from inventory.search import filter_items


def _absolute_url(request, path: str) -> str:
    return request.build_absolute_uri(path)


def _selected_label_jobs(request):
    size = get_label_size(request.POST.get("label_size") or request.GET.get("size"))
    code = get_label_code(request.POST.get("label_code") or request.GET.get("code"), size)
    request.session[LABEL_SIZE_SESSION_KEY] = size.key
    request.session[LABEL_CODE_SESSION_KEY] = code
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
            url,
            item.name,
            item.inventory_number,
            item.location.path_display(),
            size,
            code=code,
            barcode_data=item.inventory_number,
        )
        jobs.append(
            {
                "kind": "item",
                "pk": item.pk,
                "title": item.name,
                "subtitle": item.inventory_number,
                "extra": item.location.path_display(),
                "url": url,
                "filename": png_filename(f"item-{item.pk:04d}", size, code),
                "png": png,
            }
        )
    for loc in locations:
        url = _absolute_url(request, reverse("location_short", kwargs={"pk": loc.pk}))
        path = loc.path_display()
        png = render_label_png(
            url,
            loc.name,
            path,
            "",
            size,
            code=code,
            barcode_data=f"L{loc.pk}",
        )
        jobs.append(
            {
                "kind": "location",
                "pk": loc.pk,
                "title": loc.name,
                "subtitle": path,
                "extra": "",
                "url": url,
                "filename": png_filename(f"loc-{loc.pk}", size, code),
                "png": png,
            }
        )
    return size, code, jobs


def _labels_form_context(request, extra=None):
    ctx = {
        "items": Item.objects.filter(is_active=True).order_by("name"),
        "locations": Location.objects.select_related("parent").order_by("name"),
        "label_sizes": LABEL_SIZE_LIST,
        "selected_size": request.session.get(LABEL_SIZE_SESSION_KEY, "40x30"),
        "selected_code": request.session.get(LABEL_CODE_SESSION_KEY)
        or get_label_size(request.session.get(LABEL_SIZE_SESSION_KEY, "40x30")).default_code,
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
    size, code, jobs = _selected_label_jobs(request)
    if not jobs:
        messages.error(request, "Select at least one item or location.")
        return render(request, "inventory/labels.html", _labels_form_context(request))
    return _render_preview(request, size, code, jobs)


def _render_preview(request, size, code, jobs):
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
            "code": code,
            "labels": previews,
            "item_ids": request.POST.getlist("items"),
            "location_ids": request.POST.getlist("locations"),
        },
    )


MAX_LABEL_COPIES = 10


@labels_required
@require_http_methods(["POST"])
def labels_print(request):
    """Send the selected labels straight to the configured IPP label printer."""
    printer_uri = getattr(settings, "LABEL_PRINTER_URI", "")
    if not printer_uri:
        raise Http404("No label printer configured.")
    try:
        copies = int(request.POST.get("copies") or 1)
    except ValueError:
        return HttpResponseBadRequest("Invalid copies.")
    if not 1 <= copies <= MAX_LABEL_COPIES:
        return HttpResponseBadRequest(f"Copies must be between 1 and {MAX_LABEL_COPIES}.")
    size, code, jobs = _selected_label_jobs(request)
    if not jobs:
        messages.error(request, "Select at least one item or location.")
        return render(request, "inventory/labels.html", _labels_form_context(request))
    printer_name = getattr(settings, "LABEL_PRINTER_NAME", "") or "Label printer"
    try:
        document = png_to_pwg_raster([job["png"] for job in jobs], copies=copies)
        result = ipp_print_job(
            printer_uri,
            document,
            document_format=PWG_RASTER_FORMAT,
            job_name=f"OST labels {size.key} x{len(jobs)}",
            user_name=request.user.get_username(),
            copies=copies,
            timeout=getattr(settings, "LABEL_PRINTER_TIMEOUT", 30),
        )
    except PrintError as exc:
        messages.error(request, f"Printing failed: {exc}")
    else:
        count = len(jobs)
        noun = "label" if count == 1 else "labels"
        copies_note = f" ({copies} copies each)" if copies > 1 else ""
        job_note = f", job #{result.job_id}" if result.job_id is not None else ""
        messages.success(
            request,
            f"Sent {count} {noun}{copies_note} to {printer_name}{job_note}. State: {result.job_state}.",
        )
    return _render_preview(request, size, code, jobs)


@labels_required
@require_http_methods(["GET", "POST"])
def labels_zip(request):
    _size, _code, jobs = _selected_label_jobs(request)
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
    size, code, jobs = _selected_label_jobs(request)
    if not jobs:
        return HttpResponseBadRequest("Select at least one item or location.")
    rows = [
        [job["url"], job["title"], job["subtitle"], size.key, code] for job in jobs
    ]
    payload = spreadsheet_bytes(
        ["qr_url", "title", "subtitle", "label_size", "code"], rows
    )
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
    code = get_label_code(request.GET.get("code"), size)
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
            url,
            item.name,
            item.inventory_number,
            item.location.path_display(),
            size,
            code=code,
            barcode_data=item.inventory_number,
        )
        filename = png_filename(f"item-{item.pk:04d}", size, code)
    elif kind == "location":
        loc = get_object_or_404(Location, pk=pk)
        url = _absolute_url(request, reverse("location_short", kwargs={"pk": loc.pk}))
        png = render_label_png(
            url, loc.name, loc.path_display(), "", size, code=code, barcode_data=f"L{loc.pk}"
        )
        filename = png_filename(f"loc-{loc.pk}", size, code)
    else:
        return HttpResponseBadRequest("Invalid kind.")
    response = HttpResponse(png, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@read_required
@require_GET
def scan_lookup(request):
    found = resolve_scan_target(request.GET.get("q", ""), request.user)
    if not found:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(found)


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
