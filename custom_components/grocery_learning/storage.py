"""Storage helpers for Grocery Learning."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.helpers.storage import Store

from .const import CATEGORIES, STORAGE_KEY, STORAGE_VERSION


@dataclass
class LearnedTerms:
    """In-memory representation of learned terms by category."""

    data: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "LearnedTerms":
        """Return empty terms map with all known categories."""
        return cls({category: [] for category in CATEGORIES})

    @classmethod
    def from_raw(cls, raw: dict | None) -> "LearnedTerms":
        """Build a validated model from storage."""
        model = cls.empty()
        if not isinstance(raw, dict):
            return model
        for category in CATEGORIES:
            values = raw.get(category, [])
            if isinstance(values, list):
                model.data[category] = [str(v).strip().lower() for v in values if str(v).strip()]
        return model


class GroceryLearningStore:
    """Persistent storage wrapper."""

    def __init__(self, hass) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def load(self) -> LearnedTerms:
        """Load data from storage."""
        return LearnedTerms.from_raw(await self._store.async_load())

    async def save(self, terms: LearnedTerms) -> None:
        """Persist data to storage."""
        await self._store.async_save(terms.data)
