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

    # Score keyword hits by specificity: a multi-word keyword like "tomato
    # sauce" (pantry) should beat a single-word "tomato" (produce) for the item
    # "tomato sauce". Ties fall to category order (first category listed wins).
    best_category = ""
    best_score = 0
    for category in categories:
        for keyword in keywords_by_category.get(category, ()):
            parts = [p for p in str(keyword).split(" ") if p]
            if parts and len(parts) > best_score and all(part in token_forms for part in parts):
                best_score = len(parts)
                best_category = category
    return best_category or "other"
