"""Storage helpers for Local Grocery Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.helpers.storage import Store

from .const import DEFAULT_CATEGORIES, STORAGE_KEY, STORAGE_VERSION


def _default_list_color(list_id: str) -> str:
    palette = [
        "#2c78ba",
        "#1f8a70",
        "#b26b00",
        "#8f3f71",
        "#5b6ee1",
        "#7a8b00",
        "#b04d3c",
        "#3d6f8f",
    ]
    if list_id == "default":
        return "#2c78ba"
    index = sum(ord(char) for char in list_id) % len(palette)
    return palette[index]


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
        list_order_raw = raw.get("list_order", [])
        if not isinstance(list_order_raw, list):
            list_order_raw = []

        def _clean_list_map(raw_lists: dict, *, use_default_categories_for_default: bool) -> dict[str, dict]:
            cleaned_lists: dict[str, dict] = {}
            for list_id, list_obj in raw_lists.items():
                if not isinstance(list_id, str) or not isinstance(list_obj, dict):
                    continue
                normalized_id = list_id.strip()
                if not normalized_id:
                    continue
                name = str(list_obj.get("name", normalized_id.title())).strip() or normalized_id.title()
                voice_entity = str(list_obj.get("voice_entity", f"todo.lla_{normalized_id}")).strip() or f"todo.lla_{normalized_id}"
                categories_raw = list_obj.get("categories", [])
                categories_clean = [str(c).strip().lower() for c in categories_raw if str(c).strip()] if isinstance(categories_raw, list) else []
                category_order = [c for c in categories_clean if c != "completed"]
                if not category_order and normalized_id == "default" and use_default_categories_for_default:
                    category_order = list(categories)
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
                        try:
                            quantity = max(1, int(item.get("quantity", 1) or 1))
                        except (TypeError, ValueError):
                            quantity = 1
                        items_clean.append(
                            {
                                "id": item_id,
                                "summary": summary,
                                "category": category,
                                "status": status,
                                "description": str(item.get("description", "")).strip(),
                                "quantity": quantity,
                            }
                        )
                cleaned_lists[normalized_id] = {
                    "name": name,
                    "voice_entity": voice_entity,
                    "voice_alias_entities": [
                        str(candidate).strip()
                        for candidate in list_obj.get("voice_alias_entities", [])
                        if isinstance(candidate, str) and str(candidate).strip()
                    ],
                    "voice_aliases": [
                        str(candidate).strip()
                        for candidate in list_obj.get("voice_aliases", [])
                        if isinstance(candidate, str) and str(candidate).strip()
                    ],
                    "color": str(list_obj.get("color", _default_list_color(normalized_id))).strip() or _default_list_color(normalized_id),
                    "categories": category_order,
                    "items": items_clean,
                }
            return cleaned_lists

        cleaned_lists = _clean_list_map(lists_raw, use_default_categories_for_default=True)
        archived_raw = raw.get("archived_lists", {})
        if not isinstance(archived_raw, dict):
            archived_raw = {}
        cleaned_archived_lists = _clean_list_map(archived_raw, use_default_categories_for_default=False)

        if "default" not in cleaned_lists:
            cleaned_lists["default"] = {
                "name": "Grocery List",
                "voice_entity": "todo.lla_default",
                "color": _default_list_color("default"),
                "categories": list(categories) + ["other"],
                "items": [],
            }

        if active_list_id not in cleaned_lists:
            active_list_id = "default"

        list_order: list[str] = []
        for candidate in list_order_raw:
            if isinstance(candidate, str):
                normalized = candidate.strip()
                if normalized and normalized in cleaned_lists and normalized not in list_order:
                    list_order.append(normalized)
        for list_id in cleaned_lists:
            if list_id not in list_order:
                list_order.append(list_id)
        if "default" in list_order:
            list_order.remove("default")
        list_order.insert(0, "default")

        return {
            "active_list_id": active_list_id,
            "list_order": list_order,
            "lists": cleaned_lists,
            "archived_lists": cleaned_archived_lists,
        }

    async def load_activity(self) -> list[dict[str, str]]:
        """Load recent activity feed."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return []
        raw = data.get("activity", [])
        if not isinstance(raw, list):
            return []

        cleaned: list[dict[str, str]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            cleaned.append(
                {
                    "timestamp": str(entry.get("timestamp", "")).strip(),
                    "title": str(entry.get("title", "")).strip(),
                    "detail": str(entry.get("detail", "")).strip(),
                    "list_name": str(entry.get("list_name", "")).strip(),
                    "source": str(entry.get("source", "")).strip(),
                }
            )
        return cleaned

    async def save(
        self,
        terms: LearnedTerms,
        item_meta: dict[str, dict[str, str]] | None = None,
        multilist: dict | None = None,
        activity: list[dict[str, str]] | None = None,
    ) -> None:
        """Persist data to storage."""
        payload = {
            "terms": terms.data,
            "item_meta": item_meta or {},
        }
        if multilist is not None:
            payload["multilist"] = multilist
        if activity is not None:
            payload["activity"] = activity
        await self._store.async_save(
            payload
        )
