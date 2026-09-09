from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.permissions import write_required
from inventory.models import Location, Stocktake
from inventory.stocktake import (
    SESSION_KEY,
    classify_scans,
    expected_items,
    get_open_stocktake,
    items_at_current,
    set_active_stocktake,
)


@write_required
@require_http_methods(["GET", "POST"])
def stocktake_index(request):
    open_one = get_open_stocktake(request)
    if request.method == "POST":
        if open_one:
            messages.info(request, "You already have an open stocktake.")
            return redirect("inventory:stocktake_detail", pk=open_one.pk)
        scope_id = request.POST.get("scope_location") or None
        scope = None
        if scope_id:
            scope = get_object_or_404(Location, pk=scope_id, parent__isnull=True)
        stocktake = Stocktake.objects.create(started_by=request.user, scope_location=scope)
        set_active_stocktake(request, stocktake)
        if scope:
            messages.success(request, f"Stocktake started for {scope.name}.")
        else:
            messages.success(request, "Stocktake started for the whole inventory.")
        return redirect("inventory:stocktake_detail", pk=stocktake.pk)
    recent = (
        Stocktake.objects.filter(started_by=request.user)
        .select_related("scope_location")
        .order_by("-started_at")[:20]
    )
    rooms = Location.objects.filter(parent__isnull=True).order_by("name")
    return render(
        request,
        "inventory/stocktake.html",
        {"open_stocktake": open_one, "recent": recent, "rooms": rooms},
    )


@write_required
@require_GET
def stocktake_detail(request, pk):
    stocktake = get_object_or_404(
        Stocktake.objects.select_related("scope_location", "current_location", "started_by"),
        pk=pk,
        started_by=request.user,
    )
    report = classify_scans(stocktake)
    scanned_ids = set(
        stocktake.scans.values_list("item_id", flat=True)
    )
    here_items = []
    if stocktake.is_open and stocktake.current_location_id:
        here_items = [
            {"item": item, "scanned": item.pk in scanned_ids}
            for item in items_at_current(stocktake)
        ]
    return render(
        request,
        "inventory/stocktake_detail.html",
        {
            "stocktake": stocktake,
            "report": report,
            "here_items": here_items,
            "expected_total": expected_items(stocktake).count(),
        },
    )


@write_required
@require_POST
def stocktake_finish(request, pk):
    stocktake = get_object_or_404(Stocktake, pk=pk, started_by=request.user)
    if stocktake.finished_at:
        return redirect("inventory:stocktake_detail", pk=stocktake.pk)
    stocktake.finished_at = timezone.now()
    stocktake.save(update_fields=["finished_at"])
    if request.session.get(SESSION_KEY) == stocktake.pk:
        set_active_stocktake(request, None)
    messages.success(request, "Stocktake finished.")
    return redirect("inventory:stocktake_detail", pk=stocktake.pk)


@write_required
@require_POST
def stocktake_move_here(request, pk, scan_id):
    stocktake = get_object_or_404(Stocktake, pk=pk, started_by=request.user)
    scan = get_object_or_404(stocktake.scans.select_related("item"), pk=scan_id)
    if not scan.found_location_id:
        messages.error(request, "Scan a location first, then move the item there.")
        return redirect("inventory:stocktake_detail", pk=stocktake.pk)
    item = scan.item
    item.location = scan.found_location
    item.updated_by = request.user
    item.save(update_fields=["location", "updated_by", "updated_at"])
    scan.expected_location = scan.found_location
    scan.save(update_fields=["expected_location"])
    messages.success(
        request,
        f"{item.inventory_number} moved to {scan.found_location.path_display()}.",
    )
    return redirect("inventory:stocktake_detail", pk=stocktake.pk)
