"""Storage helpers for Local Grocery Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.helpers.storage import Store

from .const import DEFAULT_CATEGORIES, STORAGE_KEY, STORAGE_VERSION


@dataclass
class LearnedTerms:
    """In-memory representation of learned terms by category."""

    data: dict[str, list[str]] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)

    @classmethod
    def empty(cls, categories: list[str] | None = None) -> "LearnedTerms":
        """Return empty terms map with all known categories."""
        categories = categories or list(DEFAULT_CATEGORIES)
        return cls({category: [] for category in categories}, categories)

    @classmethod
    def from_raw(cls, raw: dict | None, categories: list[str] | None = None) -> "LearnedTerms":
        """Build a validated model from storage."""
        categories = categories or list(DEFAULT_CATEGORIES)
        model = cls.empty(categories)
        if not isinstance(raw, dict):
            return model
        for category in categories:
            values = raw.get(category, [])
            if isinstance(values, list):
                model.data[category] = [str(v).strip().lower() for v in values if str(v).strip()]
        return model


class GroceryLearningStore:
    """Persistent storage wrapper."""

    def __init__(self, hass) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def load(self, categories: list[str] | None = None) -> LearnedTerms:
        """Load data from storage."""
        data = await self._store.async_load()
        if isinstance(data, dict) and "terms" in data:
            return LearnedTerms.from_raw(data.get("terms"), categories)
        return LearnedTerms.from_raw(data, categories)

    async def load_item_meta(self) -> dict[str, dict[str, str]]:
        """Load item metadata map from storage."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return {}
        raw_meta = data.get("item_meta", {})
        if not isinstance(raw_meta, dict):
            return {}

        cleaned: dict[str, dict[str, str]] = {}
        for key, value in raw_meta.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            cleaned[key] = {}
            for field, field_value in value.items():
                if isinstance(field, str) and isinstance(field_value, str):
                    cleaned[key][field] = field_value
        return cleaned

    async def load_multilist(self, categories: list[str] | None = None) -> dict:
        """Load experimental internal multilist model."""
        data = await self._store.async_load()
        categories = categories or list(DEFAULT_CATEGORIES)
        if not isinstance(data, dict):
            data = {}

        raw = data.get("multilist", {})
        if not isinstance(raw, dict):
            raw = {}

        active_list_id = str(raw.get("active_list_id", "default")).strip() or "default"
        lists_raw = raw.get("lists", {})
        if not isinstance(lists_raw, dict):
            lists_raw = {}

        cleaned_lists: dict[str, dict] = {}
        for list_id, list_obj in lists_raw.items():
            if not isinstance(list_id, str) or not isinstance(list_obj, dict):
                continue
            normalized_id = list_id.strip()
            if not normalized_id:
                continue
            name = str(list_obj.get("name", normalized_id.title())).strip() or normalized_id.title()
            categories_raw = list_obj.get("categories", [])
            categories_clean = [str(c).strip().lower() for c in categories_raw if str(c).strip()] if isinstance(categories_raw, list) else []
            category_order = [c for c in categories_clean if c != "completed"] or list(categories)
            if "other" not in category_order:
                category_order.append("other")
            items_raw = list_obj.get("items", [])
            items_clean: list[dict] = []
            if isinstance(items_raw, list):
                for item in items_raw:
                    if not isinstance(item, dict):
                        continue
                    item_id = str(item.get("id", "")).strip()
                    summary = str(item.get("summary", "")).strip()
                    if not item_id or not summary:
                        continue
                    category = str(item.get("category", "other")).strip().lower() or "other"
                    if category not in category_order and category != "other":
                        category = "other"
                    status = str(item.get("status", "needs_action")).strip().lower()
                    if status not in {"needs_action", "completed"}:
                        status = "needs_action"
                    items_clean.append(
                        {
                            "id": item_id,
                            "summary": summary,
                            "category": category,
                            "status": status,
                            "description": str(item.get("description", "")).strip(),
                        }
                    )
            cleaned_lists[normalized_id] = {
                "name": name,
                "categories": category_order,
                "items": items_clean,
            }

        if "default" not in cleaned_lists:
            cleaned_lists["default"] = {
                "name": "Grocery List",
                "categories": list(categories) + ["other"],
                "items": [],
            }

        if active_list_id not in cleaned_lists:
            active_list_id = "default"

        return {
            "active_list_id": active_list_id,
            "lists": cleaned_lists,
        }

    async def save(
        self,
        terms: LearnedTerms,
        item_meta: dict[str, dict[str, str]] | None = None,
        multilist: dict | None = None,
    ) -> None:
        """Persist data to storage."""
        payload = {
            "terms": terms.data,
            "item_meta": item_meta or {},
        }
        if multilist is not None:
            payload["multilist"] = multilist
        await self._store.async_save(
            payload
        )
