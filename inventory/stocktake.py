"""Helpers for physical stocktake sessions."""

from __future__ import annotations

from django.db.models import QuerySet
from django.utils import timezone

from inventory.models import Item, Location, Stocktake, StocktakeScan

SESSION_KEY = "active_stocktake_id"


def get_open_stocktake(request) -> Stocktake | None:
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    pk = request.session.get(SESSION_KEY)
    if not pk:
        return (
            Stocktake.objects.filter(started_by=user, finished_at__isnull=True)
            .select_related("scope_location", "current_location")
            .first()
        )
    stocktake = (
        Stocktake.objects.filter(pk=pk, started_by=user, finished_at__isnull=True)
        .select_related("scope_location", "current_location")
        .first()
    )
    if stocktake is None:
        request.session.pop(SESSION_KEY, None)
    return stocktake


def set_active_stocktake(request, stocktake: Stocktake | None) -> None:
    if stocktake is None:
        request.session.pop(SESSION_KEY, None)
        return
    request.session[SESSION_KEY] = stocktake.pk


def scope_location_ids(stocktake: Stocktake) -> list[int] | None:
    if stocktake.scope_location_id is None:
        return None
    return stocktake.scope_location.get_descendant_ids()


def expected_items(stocktake: Stocktake) -> QuerySet[Item]:
    qs = Item.objects.filter(is_active=True).select_related(
        "location", "location__parent"
    )
    ids = scope_location_ids(stocktake)
    if ids is not None:
        qs = qs.filter(location_id__in=ids)
    return qs.order_by("name")


def items_at_current(stocktake: Stocktake) -> QuerySet[Item]:
    if not stocktake.current_location_id:
        return Item.objects.none()
    ids = stocktake.current_location.get_descendant_ids()
    return (
        Item.objects.filter(is_active=True, location_id__in=ids)
        .select_related("location", "location__parent")
        .order_by("name")
    )


def record_item_scan(stocktake: Stocktake, item: Item, user) -> StocktakeScan:
    now = timezone.now()
    item.last_seen_at = now
    item.updated_by = user
    item.save(update_fields=["last_seen_at", "updated_by", "updated_at"])
    scan, _created = StocktakeScan.objects.update_or_create(
        stocktake=stocktake,
        item=item,
        defaults={
            "scanned_at": now,
            "scanned_by": user,
            "expected_location": item.location,
            "found_location": stocktake.current_location,
        },
    )
    return scan


def classify_scans(stocktake: Stocktake) -> dict:
    scans = list(
        stocktake.scans.select_related(
            "item",
            "expected_location",
            "expected_location__parent",
            "found_location",
            "found_location__parent",
        ).order_by("item__name")
    )
    scanned_ids = {scan.item_id for scan in scans}
    missing = list(expected_items(stocktake).exclude(pk__in=scanned_ids))
    scope_ids = scope_location_ids(stocktake)
    found_here = []
    found_elsewhere = []
    found_unlocated = []
    unexpected = []
    for scan in scans:
        in_scope = scope_ids is None or scan.expected_location_id in scope_ids
        if not in_scope:
            unexpected.append(scan)
        if scan.found_location_id is None:
            found_unlocated.append(scan)
        elif scan.found_location_id == scan.expected_location_id:
            found_here.append(scan)
        else:
            found_elsewhere.append(scan)
    return {
        "found_here": found_here,
        "found_elsewhere": found_elsewhere,
        "found_unlocated": found_unlocated,
        "unexpected": unexpected,
        "missing": missing,
        "scan_count": len(scans),
        "expected_count": expected_items(stocktake).count(),
    }


def location_in_scope(stocktake: Stocktake, location: Location) -> bool:
    ids = scope_location_ids(stocktake)
    if ids is None:
        return True
    return location.pk in ids
