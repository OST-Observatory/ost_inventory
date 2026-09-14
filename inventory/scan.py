"""Resolve a scanned QR URL or Code 128 payload to an item or location."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from django.urls import reverse

from inventory.models import Item, Location
from inventory.policy import visible_items

_SHORT = re.compile(r"/([il])/(\d+)/?$")
_LOCATION_CODE = re.compile(r"^L(\d+)$", re.IGNORECASE)


def _normalize_scan_text(raw: str) -> str:
    text = (raw or "").strip()
    # AIM symbology identifiers such as ]C1 (Code 128) or ]Q3 (QR).
    if len(text) >= 3 and text[0] == "]" and text[1].isalpha() and text[2].isdigit():
        text = text[3:].strip()
    return text


def resolve_scan_target(raw: str, user) -> dict | None:
    """Return JSON-ready dict with urls, or None if nothing matches."""
    text = _normalize_scan_text(raw)
    if not text or len(text) > 400:
        return None
    parsed = urlparse(text)
    path = parsed.path or text
    short = _SHORT.search(path)
    if short:
        kind, pk = short.group(1), int(short.group(2))
        if kind == "i":
            return _item_payload(user, pk)
        return _location_payload(pk)
    loc_code = _LOCATION_CODE.fullmatch(text)
    if loc_code:
        return _location_payload(int(loc_code.group(1)))
    item = Item.lookup_by_ref(text)
    if item:
        return _item_payload(user, item.pk)
    return None


def _item_payload(user, pk: int) -> dict | None:
    item = visible_items(user, Item.objects.filter(pk=pk)).first()
    if item is None:
        return None
    return {
        "kind": "item",
        "label": f"{item.inventory_number} {item.name}",
        "url": reverse("inventory:item_detail", args=[item.pk]),
        "short_url": reverse("item_short", args=[item.pk]),
    }


def _location_payload(pk: int) -> dict | None:
    loc = Location.objects.filter(pk=pk).first()
    if loc is None:
        return None
    return {
        "kind": "location",
        "label": loc.path_display(),
        "url": reverse("inventory:location_detail", args=[loc.pk]),
        "short_url": reverse("location_short", args=[loc.pk]),
    }
