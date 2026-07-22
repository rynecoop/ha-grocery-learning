"""Pure, dependency-free logic for Local List Assist.

These helpers hold the string canonicalization, quantity accounting, contributor
metadata, and category-routing rules that have historically been the source of
recurring bugs (quantity drift, plural/possessive phrasing, list-id
normalization). They take plain data in and return plain data out — no Home
Assistant, no shared runtime state — so they can be unit tested directly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


# --- string canonicalization -------------------------------------------------

def strip_leading_item_articles(value: str) -> str:
    """Drop leading "a"/"an"/"the" articles from an item phrase."""
    words = [part for part in re.split(r"\s+", str(value).strip()) if part]
    while words and words[0].lower() in {"a", "an", "the"}:
        words.pop(0)
    return " ".join(words).strip()


def singularize_token(value: str) -> str:
    """Best-effort singular form of a single word (kept deliberately simple)."""
    token = str(value).strip().lower()
    if len(token) <= 3 or any(ch.isdigit() for ch in token):
        return token
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith(("ches", "shes", "xes", "zes")) and len(token) > 4:
        return token[:-2]
    if token.endswith("oes") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def canonical_item_phrase(value: str) -> str:
    """Normalized key form of an item: article-stripped, lowercased, singular."""
    stripped = strip_leading_item_articles(value)
    cleaned = re.sub(r"[^a-z0-9 ]", " ", stripped.lower())
    parts = [part for part in re.split(r"\s+", cleaned) if part]
    if not parts:
        return ""
    parts[-1] = singularize_token(parts[-1])
    return " ".join(parts).strip()


def display_item_summary(value: str) -> str:
    """Human-facing item text: article-stripped, whitespace-collapsed."""
    stripped = strip_leading_item_articles(value)
    return re.sub(r"\s+", " ", stripped).strip()


def normalize_category(value: str) -> str:
    """Slugify a category name to ``lower_snake`` with no leading/trailing ``_``."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def normalize_list_id(value: str) -> str:
    """Slugify a list id, falling back to ``"list"`` when empty."""
    cleaned = normalize_category(value)
    return cleaned or "list"


# --- quantity accounting -----------------------------------------------------

def coerce_quantity(value: Any) -> int:
    """Coerce arbitrary input to a quantity >= 1."""
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, quantity)


def meta_quantity(meta: Mapping[str, str]) -> int:
    """Read the current quantity from an item-metadata record."""
    return coerce_quantity(
        meta.get("current_quantity", meta.get("total_quantity", meta.get("add_count", "1")))
    )


# --- contributor metadata ----------------------------------------------------

def decode_contributors(meta: Mapping[str, str]) -> list[str]:
    """Return the de-duplicated contributor names stored on a meta record."""
    raw = str(meta.get("contributors_json", "")).strip()
    if not raw:
        fallback = str(meta.get("last_added_by_name", "")).strip()
        return [fallback] if fallback else []
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        fallback = str(meta.get("last_added_by_name", "")).strip()
        return [fallback] if fallback else []
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    names: list[str] = []
    for value in values:
        name = str(value).strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        names.append(name)
    return names


def format_contributors(names: Sequence[str]) -> str:
    """Render a list of names as "A", "A and B", or "A, B, and C"."""
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    if not cleaned:
        return "Unknown"
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def merge_meta_records(existing: Mapping[str, str], incoming: Mapping[str, str]) -> dict[str, str]:
    """Merge two item-metadata records, summing quantities and unioning names."""
    if not existing:
        return dict(incoming)
    if not incoming:
        return dict(existing)
    merged = dict(existing)
    merged["current_quantity"] = str(meta_quantity(existing) + meta_quantity(incoming))
    merged["add_count"] = str(
        int(existing.get("add_count", "0") or "0") + int(incoming.get("add_count", "0") or "0")
    )
    contributors = decode_contributors(existing)
    known = {name.lower() for name in contributors}
    for contributor in decode_contributors(incoming):
        lowered = contributor.lower()
        if lowered in known:
            continue
        known.add(lowered)
        contributors.append(contributor)
    merged["contributors_json"] = json.dumps(contributors)
    for field in (
        "last_added_at",
        "last_added_by_user_id",
        "last_added_by_name",
        "last_source",
        "last_item_text",
    ):
        merged[field] = str(incoming.get(field, existing.get(field, ""))).strip()
    return merged


# --- quick-add autocomplete --------------------------------------------------

_QUANTITY_SUFFIX_RE = re.compile(r"\s*[x×]\s*\d+\s*$", re.IGNORECASE)


def clean_suggestion_display(value: str) -> str:
    """Tidy an item's display text for the quick-add suggestion dropdown.

    Collapses whitespace, drops a trailing quantity suffix (``x 3``, ``x3``,
    ``×2``), and standardizes capitalization to Title Case so variants like
    ``apples``/``Apples``/``APPLES`` all render as one consistent ``Apples``.
    """
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = _QUANTITY_SUFFIX_RE.sub("", text).strip()
    if not text:
        return ""
    return " ".join(
        (word[:1].upper() + word[1:].lower()) if word else word
        for word in text.split(" ")
    )


def dedupe_rank_suggestions(entries: Sequence[Mapping[str, Any]], limit: int = 250) -> list[dict[str, Any]]:
    """Merge candidate quick-add suggestions from several sources into one list.

    Each entry is a mapping with ``normalized`` (the canonical key used for
    de-duplication), ``item`` (the display text), ``count`` (how often it has
    been added), ``last`` (an ISO timestamp string), and ``source``. Entries with
    the same ``normalized`` key collapse into one — the highest count and most
    recent timestamp win, and the first non-empty display text is kept. The
    result is ranked by count then recency, capped at ``limit``.
    """
    by_norm: dict[str, dict[str, Any]] = {}
    for entry in entries or ():
        normalized = str(entry.get("normalized", "")).strip()
        if not normalized:
            continue
        item = str(entry.get("item", "")).strip()
        try:
            count = int(entry.get("count", 0) or 0)
        except (TypeError, ValueError):
            count = 0
        last = str(entry.get("last", "")).strip()
        existing = by_norm.get(normalized)
        if existing is None:
            by_norm[normalized] = {
                "normalized": normalized,
                "item": item or normalized,
                "count": count,
                "last": last,
                "source": str(entry.get("source", "")).strip(),
            }
            continue
        if count > existing["count"]:
            existing["count"] = count
        if last > existing["last"]:
            existing["last"] = last
        if not existing["item"] and item:
            existing["item"] = item
    ranked = sorted(by_norm.values(), key=lambda s: (s["count"], s["last"]), reverse=True)
    return ranked[: max(0, int(limit))]


# --- category routing --------------------------------------------------------

def reorder_category_items(
    items: Sequence[Mapping[str, Any]],
    category: str,
    ordered_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """Return ``items`` with the active rows of ``category`` reordered.

    Only ``needs_action`` items in ``category`` move, and they are placed into
    the exact slots they already occupy in the flat list — so every other row
    (other categories, completed items) keeps its position. ``ordered_ids`` is
    the desired id order; any of the category's ids not mentioned keep their
    current relative order at the end.
    """
    items = list(items)
    category = str(category)
    slots = [
        index
        for index, item in enumerate(items)
        if str(item.get("status", "needs_action")) == "needs_action"
        and str(item.get("category", "other")) == category
    ]
    if len(slots) < 2:
        return items

    slot_ids = [str(items[index].get("id", "")) for index in slots]
    by_id = {str(item.get("id", "")): item for item in items}

    desired: list[str] = [str(oid) for oid in ordered_ids if str(oid) in slot_ids]
    seen = set(desired)
    for sid in slot_ids:
        if sid not in seen:
            desired.append(sid)
            seen.add(sid)

    for slot, oid in zip(slots, desired):
        items[slot] = by_id.get(oid, items[slot])
    return items


# --- saved meals & frequent suggestions -------------------------------------

def merge_meal_ingredients(entries: Sequence[Any]) -> list[dict[str, str]]:
    """Normalize a meal's ingredient input into a de-duplicated ``[{item}]`` list.

    Accepts a sequence of plain strings or ``{"item": ...}`` mappings, tidies each
    with :func:`display_item_summary`, drops blanks, and de-duplicates
    case-insensitively while preserving first-seen order.
    """
    ingredients: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries or ():
        raw = entry.get("item", "") if isinstance(entry, Mapping) else entry
        item = display_item_summary(str(raw).strip())
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ingredients.append({"item": item})
    return ingredients


def unique_meal_id(name: str, existing_ids: Sequence[str]) -> str:
    """Derive a stable, collision-free meal id from ``name``."""
    existing = set(existing_ids or ())
    base = normalize_list_id(name)
    meal_id = base
    suffix = 2
    while meal_id in existing:
        meal_id = f"{base}_{suffix}"
        suffix += 1
    return meal_id


def migrate_meal_categories(meals, meal_categories):
    """Fold the legacy single ``meal.category`` string into the managed set.

    Seeds the ordered ``{id, label}`` category set from any legacy category
    labels and rewrites each meal to a list of category ids, dropping the old
    ``category`` key. Mutates ``meals`` in place; returns the (possibly grown)
    category list. Idempotent: once meals carry ``categories`` and no legacy
    ``category``, re-running is a no-op.
    """
    order = [
        {"id": str(c["id"]).strip(), "label": str(c["label"]).strip()}
        for c in (meal_categories or [])
        if isinstance(c, dict)
        and str(c.get("id", "")).strip()
        and str(c.get("label", "")).strip()
    ]
    by_label = {c["label"].lower(): c["id"] for c in order}
    ids = {c["id"] for c in order}

    def _ensure(label: str) -> str:
        key = label.lower()
        if key in by_label:
            return by_label[key]
        cid = unique_meal_id(label, ids)
        ids.add(cid)
        order.append({"id": cid, "label": label})
        by_label[key] = cid
        return cid

    if isinstance(meals, dict):
        for meal in meals.values():
            if not isinstance(meal, dict):
                continue
            cats = meal.get("categories")
            if not isinstance(cats, list) or not cats:
                legacy = str(meal.get("category", "")).strip()
                meal["categories"] = [_ensure(legacy)] if legacy else []
            meal.pop("category", None)
    return order


def select_frequent(
    frequent: Mapping[str, Mapping[str, Any]],
    exclude_normalized: set[str],
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Pick the top frequent-item suggestions to offer as quick-add chips.

    Keeps entries added at least twice that are not dismissed and not already on
    the active list, ranked by count then recency, capped at ``limit``.
    """
    rows = [
        (key, value)
        for key, value in (frequent or {}).items()
        if isinstance(value, Mapping)
        and int(value.get("count", 0) or 0) >= 2
        and not value.get("dismissed")
        and key not in exclude_normalized
    ]
    rows.sort(key=lambda kv: (int(kv[1].get("count", 0) or 0), str(kv[1].get("last", ""))), reverse=True)
    return [
        {"item": str(value.get("display", key)).strip() or key, "count": int(value.get("count", 0) or 0)}
        for key, value in rows[:limit]
    ]


def category_for_term(
    terms_data: Mapping[str, Sequence[str]],
    normalized: str,
    categories: Sequence[str],
    keywords_by_category: Mapping[str, Sequence[str]],
) -> str:
    """Resolve a normalized item phrase to a category.

    Learned terms win over keyword heuristics. Keyword matching tolerates simple
    plurals by also considering singular token forms.
    """
    if normalized:
        for category in categories:
            if normalized in set(terms_data.get(category, [])):
                return category

    tokens = [t for t in normalized.split(" ") if t]
    token_forms: set[str] = set(tokens)
    for token in tokens:
        if len(token) > 3 and token.endswith("s"):
            token_forms.add(token[:-1])
        if len(token) > 4 and token.endswith("es"):
            token_forms.add(token[:-2])

    # Score keyword hits so the best match wins, not just the first category:
    #  * more matched words is more specific ("tomato sauce" > "tomato"), and
    #  * a keyword that matches the item's head noun (its last word) breaks ties
    #    toward what the item *is* — so "mushroom soup" routes to pantry ("soup")
    #    rather than produce ("mushroom"), and "green pepper" stays produce.
    # Equal scores fall to category order (first category listed wins).
    head = tokens[-1] if tokens else ""
    best_category = ""
    best_score = 0
    for category in categories:
        for keyword in keywords_by_category.get(category, ()):
            parts = [p for p in str(keyword).split(" ") if p]
            if not parts or not all(part in token_forms for part in parts):
                continue
            score = len(parts) * 2 + (1 if head in parts else 0)
            if score > best_score:
                best_score = score
                best_category = category
    return best_category or "other"
