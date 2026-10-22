"""Turn the legacy free-text Item.container into container items (stored_in).

A person reviews the proposal before anything changes:

    manage.py container_plan --out containers.csv    # proposal, edit it in a spreadsheet
    manage.py container_apply containers.csv         # dry run: what would change
    manage.py container_apply containers.csv --commit --user NAME

Plan rows (one CSV, columns PLAN_COLUMNS):

kind=text  one per legacy text and room; `action` is
    link   target "#0537": that item becomes the container
    new    target = name of a new container item (default: the text)
    merge  target = another container_text in the same room (typo, variant)
    mount  target "#0693": the items get mounted on that item instead
    clear  the text is just dropped
kind=item  overrides for one item (`items` = "#0518"); `action` is
    keep    leave mount/storage as is (only the text is dropped)
    store   target "#0536", or a container_text of the same room
    mount   target "#0677"
    unmount take it off its host

Every processed item loses its legacy text, so a plan can be applied once.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction

from inventory.models import Item

PLAN_COLUMNS = ["kind", "container_text", "room", "action", "target", "items", "places", "note"]
TEXT_ACTIONS = {"link", "new", "merge", "mount", "clear"}
ITEM_ACTIONS = {"keep", "store", "mount", "unmount"}

CONTAINER_WORDS = {
    "bag", "bags", "box", "case", "crate", "tin", "pouch", "cabinet", "drawer",
    "koffer", "kiste", "tasche",
}
STOP_WORDS = {"the", "and", "for", "with", "of", "a", "etc"}


def _tokens(text: str) -> set[str]:
    words = re.split(r"[^0-9a-zäöüß]+", (text or "").lower())
    return {w.rstrip("s") if len(w) > 3 else w for w in words if w and w not in STOP_WORDS}


def _looks_like_container(name: str) -> bool:
    # "Keys (OMS and dome cabinet)" is keys, not a cabinet: ignore parentheses.
    head = re.sub(r"\([^)]*\)", " ", name.lower())
    return bool(set(re.split(r"[^0-9a-zäöüß]+", head)) & CONTAINER_WORDS)


def _looks_like_model_name(text: str) -> bool:
    """C11, CDK20, RASA, DADOS: one instrument name rather than a box label.

    An earlier import used such names for "belongs to"; they become mounts.
    """
    words = text.split()
    return len(words) == 1 and bool(re.search(r"\d", text) or (len(text) >= 2 and text.isupper()))


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


NUMBERING = re.compile(r"^(\d+|[ivx]+)$")


def _is_variant(a: str, b: str) -> bool:
    x, y = a.lower().strip(), b.lower().strip()
    if x == y or _tokens(x) == _tokens(y):
        return True
    # "Lamps I" and "Lamps II" are two boxes, not a typo.
    if any(NUMBERING.match(t) for t in _tokens(x) ^ _tokens(y)):
        return False
    return min(len(x), len(y)) >= 6 and _distance(x, y) <= 2


def _room(item):
    loc = item.location
    return loc.parent if loc.parent_id else loc


def _ref(item) -> str:
    return item.inventory_number


def _label(item) -> str:
    return f"{item.inventory_number} {item.name}"


def _places(items) -> str:
    counts = Counter(i.location.path_display() for i in items)
    return "; ".join(f"{p} ({n})" for p, n in counts.most_common())


def legacy_groups(items):
    """(text, room name) -> items carrying that legacy text in that room."""
    groups = defaultdict(list)
    for item in items:
        text = item.container.strip()
        if text:
            groups[(text, _room(item).name)].append(item)
    return groups


def _all_items():
    return list(
        Item.objects.select_related("location", "location__parent", "installed_in").order_by("pk")
    )


def build_plan() -> list[dict]:
    items = _all_items()
    active = [i for i in items if i.is_active]
    groups = legacy_groups(items)
    rows = []
    item_rows = []
    mounted_members = []
    planned_links = {}

    # Spelling variants in one room join the most used spelling.
    canonical = {}
    by_room = defaultdict(list)
    for text, room in groups:
        by_room[room].append(text)
    for room, texts in by_room.items():
        # Most used spelling wins; on a tie the capitalised, fuller one.
        texts.sort(key=lambda t: (-len(groups[(t, room)]), not t[:1].isupper(), -len(t), t.lower()))
        for i, text in enumerate(texts):
            for main in texts[:i]:
                if canonical.get((main, room), main) == main and _is_variant(text, main):
                    canonical[(text, room)] = main
                    break

    for (text, room), members in sorted(groups.items(), key=lambda g: (g[0][1], -len(g[1]), g[0][0].lower())):
        row = {
            "kind": "text",
            "container_text": text,
            "room": room,
            "items": len(members),
            "places": _places(members),
        }
        notes = []
        self_refs = [m for m in members if m.name.strip().lower() == text.lower()]
        for m in self_refs:
            item_rows.append(_item_row(m, "keep", "", "the item names itself as its container; text dropped"))
        others = [m for m in members if m not in self_refs]
        member_pks = {m.pk for m in members}

        if (text, room) in canonical:
            row.update(action="merge", target=canonical[(text, room)], note="spelling variant")
            rows.append(row)
            continue
        if not others:
            row.update(action="clear", target="", note="only items naming themselves")
            rows.append(row)
            continue

        wanted = _tokens(text)
        place = Counter(m.location_id for m in others).most_common(1)[0][0]
        same_room, other_room = _container_candidates(text, room, place, active, member_pks)
        mounted_on_it = any(m.installed_in and wanted <= _tokens(m.installed_in.name) for m in others)
        # "UVEX" holding the UVEX spectrograph is its case; "C11" holding a clamp is not.
        holds_instrument = any(
            wanted <= _tokens(m.name) and not m.installed_in_id for m in others
        )
        belongs_to = _looks_like_model_name(text) and (mounted_on_it or not holds_instrument)
        if same_room and same_room[1] == "same name":
            target, how = same_room
            row.update(action="link", target=_ref(target), note=f"{how}: {_label(target)}")
            planned_links[target.pk] = target
        elif belongs_to:
            host, alternatives = _mount_candidate(text, room, place, active, items, members)
            if host:
                row.update(
                    action="mount",
                    target=_ref(host),
                    note=f"old 'belongs to' text: mount on {_label(host)}",
                )
                if _room(host).name != room:
                    notes.append(f"{_label(host)} is in {host.location.path_display()}; the items move there")
            elif same_room:
                target, how = same_room
                row.update(action="link", target=_ref(target), note=f"{how}: {_label(target)}")
                planned_links[target.pk] = target
            else:
                row.update(action="clear", target="", note="old 'belongs to' text; no clear match")
            if same_room and row["action"] == "mount":
                notes.append(f"or store in {_label(same_room[0])}")
            if alternatives:
                notes.append("other candidates: " + ", ".join(_label(a) for a in alternatives))
        elif same_room:
            target, how = same_room
            row.update(action="link", target=_ref(target), note=f"{how}: {_label(target)}")
            planned_links[target.pk] = target
        elif other_room and other_room[1] == "same name":
            target = other_room[0]
            row.update(action="link", target=_ref(target), note=f"same name: {_label(target)}")
            planned_links[target.pk] = target
            notes.append(f"container is in {target.location.path_display()}; the items move there")
        else:
            row.update(action="new", target=text, note="new container item")
            if other_room:
                notes.append(f"similar container in another room: {_label(other_room[0])}")
        boxes_inside = [m for m in others if _looks_like_container(m.name)]
        if boxes_inside:
            notes.append(
                "contains container-like item(s) "
                + ", ".join(_label(b) for b in boxes_inside)
                + " (is one of them the box itself?)"
            )
        if len({m.location_id for m in others}) > 1 and row["action"] in {"link", "new"}:
            notes.append("items sit in several places; they move to the container's place")
        if notes:
            row["note"] = "; ".join([row.get("note", ""), *notes]).strip("; ")
        rows.append(row)

        mounted_members.extend((m, text, room) for m in others if m.installed_in_id)

    # Mounted, yet a container text: in practice it lies loose in that box.
    by_key = {(r["container_text"], r["room"]): r for r in rows}

    def final_row(key):
        row = by_key[key]
        while row["action"] == "merge" and (row["target"], key[1]) in by_key:
            row = by_key[(row["target"], key[1])]
        return row

    for m, text, room in mounted_members:
        decided = final_row((text, room))
        if decided["action"] == "mount" and decided["target"] == _ref(m.installed_in):
            continue
        if decided["action"] in {"link", "new"}:
            item_rows.append(
                _item_row(
                    m,
                    "store",
                    text,
                    f"was mounted on {_label(m.installed_in)}, but the text says it is kept in "
                    f"{text!r}: stored there, no longer mounted (keep = leave it mounted)",
                )
            )
        else:
            item_rows.append(
                _item_row(m, "keep", "", f"stays mounted on {_label(m.installed_in)}")
            )

    # Cases mounted on their main item: the main item goes into the case instead.
    for case in planned_links.values():
        if case.installed_in_id:
            host = case.installed_in
            item_rows.append(_item_row(case, "unmount", "", f"case was mounted on {_label(host)}"))
            item_rows.append(_item_row(host, "store", _ref(case), f"main item goes into {_label(case)}"))

    seen = set()
    unique_item_rows = []
    for r in item_rows:
        key = (r["items"], r["action"], r["target"])
        if key not in seen:
            seen.add(key)
            unique_item_rows.append(r)
    return rows + unique_item_rows


def _item_row(item, action, target, note):
    return {
        "kind": "item",
        "container_text": item.container.strip(),
        "room": _room(item).name,
        "action": action,
        "target": target,
        "items": _ref(item),
        "places": item.location.path_display(),
        "note": f"{item.name}: {note}",
    }


def _container_candidates(text, room, place_id, active, member_pks):
    """Best existing container for a text: ((item, how) in this room, (item, how) elsewhere)."""
    exact = [i for i in active if i.name.strip().lower() == text.lower() and i.pk not in member_pks]
    for i in exact:
        if _room(i).name == room:
            return (i, "same name"), None
    wanted = _tokens(text) - CONTAINER_WORDS
    # A lone generic word ("Cables") only matches a box at the items' own place.
    generic = (
        len(wanted) == 1
        and not _looks_like_model_name(text)
        and not _tokens(text) & CONTAINER_WORDS
    )
    fuzzy = []
    for i in active:
        if i.pk in member_pks or not wanted or not _looks_like_container(i.name):
            continue
        if generic and i.location_id != place_id:
            continue
        score = len(wanted & _tokens(i.name)) / len(wanted)
        if score >= 0.75:
            fuzzy.append((_room(i).name != room, -score, len(i.name), i))
    fuzzy.sort(key=lambda f: f[:3])
    same = next((f[3] for f in fuzzy if not f[0]), None)
    if same:
        return (same, "similar container in this room"), None
    if exact:
        return None, (exact[0], "same name")
    if fuzzy:
        return None, (fuzzy[0][3], "similar container")
    return None, None


def _mount_candidate(text, room, place_id, active, items, members):
    """For old 'belongs to' texts such as RASA: the instrument the items go with."""
    wanted = _tokens(text)
    for member in members:
        host = member.installed_in
        if host and wanted <= _tokens(host.name):
            return host, []
    member_pks = {m.pk for m in members}
    hosts_with_parts = {i.installed_in_id for i in items if i.installed_in_id}
    candidates = [
        i
        for i in active
        if i.pk not in member_pks and not _looks_like_container(i.name) and wanted <= _tokens(i.name)
    ]
    candidates.sort(
        key=lambda i: (
            i.pk not in hosts_with_parts,
            i.location_id != place_id,
            _room(i).name != room,
            len(_tokens(i.name)),
            i.pk,
        )
    )
    if not candidates:
        return None, []
    best = candidates[0]
    # Only something that carries parts, or sits right there, is a believable host.
    if best.pk in hosts_with_parts or best.location_id == place_id:
        return best, candidates[1:4]
    return None, candidates[:3]


def write_plan(rows, fh):
    writer = csv.DictWriter(fh, fieldnames=PLAN_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in PLAN_COLUMNS})


def read_plan(fh) -> list[dict]:
    rows = []
    for line, row in enumerate(csv.DictReader(fh), start=2):
        row = {k: (v or "").strip() for k, v in row.items() if k}
        row["line"] = line
        rows.append(row)
    return rows


@dataclass
class ApplyResult:
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    containers_linked: int = 0
    containers_created: int = 0
    items_changed: int = 0
    moved: int = 0


def apply_plan(rows, user, *, commit=False) -> ApplyResult:
    result = ApplyResult()
    with transaction.atomic():
        _apply(rows, user, result)
        if result.errors or not commit:
            transaction.set_rollback(True)
    return result


def _lookup(ref):
    item = Item.lookup_by_ref(ref)
    if item is None:
        raise ValueError(f"item {ref or '(empty)'} not found")
    return item


def _apply(rows, user, result):
    items = _all_items()
    groups = legacy_groups(items)
    text_rows = {}
    item_rows = {}
    for row in rows:
        kind, action = row.get("kind"), row.get("action")
        if kind == "text":
            if action not in TEXT_ACTIONS:
                result.errors.append(f"line {row['line']}: unknown action {action!r}")
                continue
            text_rows[(row["container_text"], row["room"])] = row
        elif kind == "item":
            if action not in ITEM_ACTIONS:
                result.errors.append(f"line {row['line']}: unknown action {action!r}")
                continue
            try:
                item_rows[_lookup(row["items"]).pk] = row
            except ValueError as exc:
                result.errors.append(f"line {row['line']}: {exc}")
        else:
            result.errors.append(f"line {row['line']}: kind must be text or item")
    for key in text_rows.keys() - groups.keys():
        result.warnings.append(f"no items carry {key[0]!r} in {key[1]} any more; row ignored")
    for key in groups.keys() - text_rows.keys():
        result.warnings.append(f"{key[0]!r} in {key[1]} is not in the plan; left unchanged")

    # Follow merges to the row that decides.
    def final(key, depth=0):
        row = text_rows[key]
        if row["action"] != "merge":
            return key
        target = (row["target"], key[1])
        if target not in text_rows or depth > 10:
            raise ValueError(f"merge target {row['target']!r} is not a container_text in {key[1]}")
        return final(target, depth + 1)

    members = defaultdict(list)
    for key in groups.keys() & text_rows.keys():
        try:
            members[final(key)].extend(groups[key])
        except ValueError as exc:
            result.errors.append(f"line {text_rows[key]['line']}: {exc}")
    if result.errors:
        return

    # 1. Containers and hosts per deciding row.
    resolved = {}
    for key, group in members.items():
        row = text_rows[key]
        action = row["action"]
        try:
            if action == "link":
                box = _lookup(row["target"])
                if not box.is_container:
                    box.is_container = True
                    box.save(update_fields=["is_container", "updated_at"])
                    result.containers_linked += 1
                    result.changes.append(f"{_label(box)} becomes a container")
                resolved[key] = ("store", box)
            elif action == "new":
                place = Counter(i.location for i in group).most_common(1)[0][0]
                box = Item.create_container(row["target"] or key[0], place, user)
                result.containers_created += 1
                result.changes.append(
                    f"new container {_label(box)} at {place.path_display()} (from {key[0]!r})"
                )
                resolved[key] = ("store", box)
            elif action == "mount":
                resolved[key] = ("mount", _lookup(row["target"]))
            else:
                resolved[key] = ("clear", None)
        except ValueError as exc:
            result.errors.append(f"line {row['line']}: {exc}")
    if result.errors:
        return

    def container_for(target, room):
        if target.startswith("#") or target.isdigit():
            return _lookup(target)
        key = (target, room)
        if key in text_rows:
            how, box = resolved.get(final(key), (None, None))
            if how == "store":
                return box
        raise ValueError(f"{target!r} is neither an item number nor a container of {room}")

    # 2. Unmount first, so a case can take the item it was mounted on.
    for pk, row in item_rows.items():
        if row["action"] == "unmount":
            item = Item.objects.get(pk=pk)
            _change(item, user, result, row, installed_in=None)

    # 3. The text groups, except items with their own row.
    for key, group in members.items():
        how, target = resolved[key]
        for member in group:
            item = Item.objects.get(pk=member.pk)
            if item.pk in item_rows or how == "clear" or item.pk == target.pk:
                _change(item, user, result, text_rows[key])
            elif how == "store" and item.installed_in_id:
                result.changes.append(
                    f"{_label(item)} stays mounted on {_label(item.installed_in)}"
                )
                _change(item, user, result, text_rows[key])
            elif how == "store":
                _change(item, user, result, text_rows[key], stored_in=target, installed_in=None)
            else:
                _change(item, user, result, text_rows[key], installed_in=target, stored_in=None)

    # 4. The remaining item rows.
    for pk, row in item_rows.items():
        item = Item.objects.get(pk=pk)
        try:
            if row["action"] == "store":
                _change(item, user, result, row, stored_in=container_for(row["target"], row["room"]), installed_in=None)
            elif row["action"] == "mount":
                _change(item, user, result, row, installed_in=_lookup(row["target"]), stored_in=None)
            else:
                _change(item, user, result, row)
        except ValueError as exc:
            result.errors.append(f"line {row['line']}: {exc}")


def _describe(item):
    if item.installed_in_id:
        return f"mounted on {_label(item.installed_in)}"
    if item.stored_in_id:
        return f"in {_label(item.stored_in)}"
    return "loose"


_UNSET = object()


def _change(item, user, result, row, *, stored_in=_UNSET, installed_in=_UNSET):
    before = _describe(item)
    old_location = item.location
    if installed_in is not _UNSET:
        item.installed_in = installed_in
    if stored_in is not _UNSET:
        item.stored_in = stored_in
    item.container = ""
    item.updated_by = user
    try:
        item.full_clean()
    except ValidationError as exc:
        result.errors.append(f"line {row['line']}: {_label(item)}: {'; '.join(exc.messages)}")
        return
    item.save()
    item.refresh_from_db()
    after = _describe(item)
    if after != before:
        result.items_changed += 1
        line = f"{_label(item)}: {before} -> {after}"
        if item.location_id != old_location.pk:
            result.moved += 1
            line += f" (place {old_location.path_display()} -> {item.location.path_display()})"
        result.changes.append(line)
