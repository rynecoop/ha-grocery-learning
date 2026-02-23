"""Storage helpers for Grocery Learning."""

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
        return LearnedTerms.from_raw(await self._store.async_load(), categories)

    async def save(self, terms: LearnedTerms) -> None:
        """Persist data to storage."""
        await self._store.async_save(terms.data)
