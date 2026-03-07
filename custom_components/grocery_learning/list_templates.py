"""List template helpers for Local List Assist."""

from __future__ import annotations

from .const import DEFAULT_CATEGORIES


LIST_TEMPLATE_PRESETS: dict[str, list[str]] = {
    "flat": [],
    "grocery": list(DEFAULT_CATEGORIES),
    "todo": [],
    "camping": ["gear", "food", "clothes", "camp", "other"],
    "travel": ["packing", "documents", "booking", "errands", "other"],
}


def template_presets(fallback_grocery_categories: list[str] | None = None) -> dict[str, list[str]]:
    return {
        template_id: categories_for_template(template_id, fallback_grocery_categories)
        for template_id in LIST_TEMPLATE_PRESETS
    }


def categories_for_template(template_id: str, fallback_grocery_categories: list[str] | None = None) -> list[str]:
    normalized = str(template_id or "").strip().lower()
    if normalized == "grocery":
        return list(fallback_grocery_categories or DEFAULT_CATEGORIES)
    categories = LIST_TEMPLATE_PRESETS.get(normalized, [])
    return [str(category).strip().lower() for category in categories if str(category).strip()]
