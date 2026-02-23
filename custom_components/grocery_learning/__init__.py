"""Grocery Learning custom integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CATEGORIES,
    CONF_AUTO_ROUTE_INBOX,
    CONF_INBOX_ENTITY,
    CONF_NOTIFY_SERVICE,
    DOMAIN,
    HELPER_BY_CATEGORY,
    REVIEW_CATEGORY_HELPER,
    REVIEW_ITEM_HELPER,
    REVIEW_PENDING_HELPER,
    REVIEW_SOURCE_HELPER,
    SERVICE_APPLY_REVIEW,
    SERVICE_FORGET_TERM,
    SERVICE_LEARN_TERM,
    SERVICE_ROUTE_ITEM,
    SERVICE_SYNC_HELPERS,
    TARGET_LIST_BY_CATEGORY,
)
from .storage import GroceryLearningStore, LearnedTerms

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []

LEARN_SCHEMA = vol.Schema(
    {
        vol.Required("category"): vol.In(CATEGORIES),
        vol.Required("term"): cv.string,
    }
)

FORGET_SCHEMA = vol.Schema(
    {
        vol.Optional("category"): vol.In(CATEGORIES),
        vol.Required("term"): cv.string,
    }
)

ROUTE_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("item"): cv.string,
        vol.Optional("source_list", default=""): cv.string,
        vol.Optional("remove_from_source", default=False): cv.boolean,
        vol.Optional("review_on_other", default=True): cv.boolean,
    }
)

APPLY_REVIEW_SCHEMA = vol.Schema(
    {
        vol.Optional("category"): cv.string,
        vol.Optional("learn", default=True): cv.boolean,
    }
)

KEYWORDS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "dairy": ("milk", "egg", "eggs", "cheese", "butter", "yogurt", "cream", "sour cream"),
    "meat": ("chicken", "beef", "steak", "pork", "turkey", "sausage", "bacon", "ham", "fish", "salmon", "tuna", "shrimp"),
    "bakery": ("bread", "bagel", "bun", "roll", "tortilla", "muffin", "croissant", "donut", "donuts"),
    "produce": ("apple", "banana", "orange", "grape", "berry", "berries", "lettuce", "spinach", "kale", "tomato", "cucumber", "onion", "potato", "avocado", "pepper", "carrot"),
    "frozen": ("frozen", "ice cream", "frozen pizza", "hash brown", "waffles"),
    "household": ("paper towel", "toilet paper", "tissue", "trash bag", "detergent", "dish soap", "hand soap", "sponge", "foil", "ziplock", "ziploc", "cloth"),
    "pantry": ("soda", "pop", "coke", "juice", "coffee", "tea", "pasta", "alfredo", "sauce", "pickle", "pickles", "rice", "cereal", "chips", "cracker", "crackers", "snack", "soup", "flour", "sugar", "oil", "vinegar", "spice", "seasoning", "peanut butter", "jam"),
}


def _normalize_term(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up integration and register services."""
    await _async_setup_runtime(hass)
    return True


async def _async_setup_runtime(hass: HomeAssistant) -> None:
    """Set up runtime state/services once."""
    hass.data.setdefault(DOMAIN, {})
    if hass.data[DOMAIN].get("runtime_ready"):
        return
    store = GroceryLearningStore(hass)
    terms = await store.load()
    hass.data[DOMAIN]["store"] = store
    hass.data[DOMAIN]["terms"] = terms
    hass.data[DOMAIN]["runtime_ready"] = True

    async def _save() -> None:
        await store.save(hass.data[DOMAIN]["terms"])

    async def _learn_term(call: ServiceCall) -> None:
        category = call.data["category"]
        term = _normalize_term(call.data["term"])
        if not term:
            return
        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        existing = set(terms_obj.data.get(category, []))
        if term in existing:
            return
        terms_obj.data.setdefault(category, []).append(term)
        await _save()
        _LOGGER.debug("Learned grocery term '%s' -> %s", term, category)

    async def _forget_term(call: ServiceCall) -> None:
        term = _normalize_term(call.data["term"])
        if not term:
            return
        selected = call.data.get("category")
        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        changed = False
        for category, values in terms_obj.data.items():
            if selected and category != selected:
                continue
            if term in values:
                terms_obj.data[category] = [v for v in values if v != term]
                changed = True
        if changed:
            await _save()

    async def _sync_helpers_internal() -> None:
        """Sync learned terms to input_text helpers used by YAML router."""
        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        for category in CATEGORIES:
            helper = HELPER_BY_CATEGORY.get(category)
            if not helper or hass.states.get(helper) is None:
                continue
            merged = "|".join(sorted(set(terms_obj.data.get(category, []))))
            if len(merged) > 255:
                # Keep latest terms if helper max length is hit.
                clipped = merged[-255:]
                if "|" in clipped:
                    clipped = clipped.split("|", 1)[1]
                merged = clipped
            await hass.services.async_call(
                "input_text",
                "set_value",
                {"entity_id": helper, "value": merged},
                blocking=True,
            )

    async def _sync_helpers(_call: ServiceCall) -> None:
        """Service wrapper for helper sync."""
        await _sync_helpers_internal()

    async def _set_helper_if_exists(entity_id: str, value: str) -> None:
        if hass.states.get(entity_id) is None:
            return
        domain, _ = entity_id.split(".", 1)
        service = "set_value" if domain == "input_text" else ("turn_on" if value == "on" else "turn_off")
        payload: dict[str, Any] = {"entity_id": entity_id}
        if domain == "input_text":
            payload["value"] = value
        await hass.services.async_call(domain, service, payload, blocking=True)

    async def _remove_from_list(list_entity: str, item_summary: str) -> None:
        if not list_entity or hass.states.get(list_entity) is None:
            return
        response = await hass.services.async_call(
            "todo",
            "get_items",
            {"status": "needs_action"},
            target={"entity_id": list_entity},
            blocking=True,
            return_response=True,
        )
        resp = response.get(list_entity, response) if isinstance(response, dict) else {}
        items = resp.get("items", []) if isinstance(resp, dict) else []
        match = next((i for i in items if str(i.get("summary", "")).strip() == item_summary), None)
        if not match:
            return
        remove_id = str(match.get("uid", "")).strip() or str(match.get("summary", "")).strip()
        if remove_id:
            await hass.services.async_call(
                "todo",
                "remove_item",
                {"item": remove_id},
                target={"entity_id": list_entity},
                blocking=True,
            )

    def _get_category_for_term(terms_obj: LearnedTerms, normalized: str) -> str:
        if normalized:
            for category in CATEGORIES:
                if normalized in set(terms_obj.data.get(category, [])):
                    return category
        text = f" {normalized} "
        for category, words in KEYWORDS_BY_CATEGORY.items():
            if any(f" {word} " in text for word in words):
                return category
        return "other"

    async def _route_item(call: ServiceCall) -> None:
        raw_item = call.data["item"]
        source_list = call.data["source_list"].strip()
        remove_from_source = bool(call.data["remove_from_source"])
        review_on_other = bool(call.data["review_on_other"])
        normalized = _normalize_term(raw_item)
        if not normalized:
            return

        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        category = _get_category_for_term(terms_obj, normalized)
        target_list = TARGET_LIST_BY_CATEGORY[category]

        await hass.services.async_call(
            "todo",
            "add_item",
            {"item": raw_item},
            target={"entity_id": target_list},
            blocking=True,
        )

        if remove_from_source:
            await _remove_from_list(source_list, raw_item)

        if category == "other" and review_on_other:
            await _set_helper_if_exists(REVIEW_ITEM_HELPER, raw_item)
            await _set_helper_if_exists(REVIEW_SOURCE_HELPER, target_list)
            await _set_helper_if_exists(REVIEW_PENDING_HELPER, "on")
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Grocery needs category review",
                    "message": f"'{raw_item}' was added to Other. Open Grocery dashboard Review & Learn.",
                    "notification_id": "grocery_uncategorized",
                },
                blocking=True,
            )
            entry = hass.data.get(DOMAIN, {}).get("entry")
            notify_service = str(entry.data.get(CONF_NOTIFY_SERVICE, "")).strip() if entry else ""
            if notify_service and "." in notify_service:
                n_domain, n_service = notify_service.split(".", 1)
                await hass.services.async_call(
                    n_domain,
                    n_service,
                    {
                        "title": "Grocery review needed",
                        "message": f"'{raw_item}' was added to Other.",
                    },
                    blocking=True,
                )

    async def _apply_review(call: ServiceCall) -> None:
        category_in = str(call.data.get("category", "")).strip().lower()
        learn = bool(call.data.get("learn", True))
        if not category_in and hass.states.get(REVIEW_CATEGORY_HELPER):
            category_in = str(hass.states.get(REVIEW_CATEGORY_HELPER).state).strip().lower()

        label_map = {
            "produce": "produce",
            "bakery": "bakery",
            "meat": "meat",
            "dairy": "dairy",
            "frozen": "frozen",
            "pantry": "pantry",
            "household": "household",
            "keep other": "other",
            "other": "other",
        }
        target_category = label_map.get(category_in, "other")

        review_item_state = hass.states.get(REVIEW_ITEM_HELPER)
        source_list_state = hass.states.get(REVIEW_SOURCE_HELPER)
        review_item = str(review_item_state.state).strip() if review_item_state else ""
        source_list = str(source_list_state.state).strip() if source_list_state else TARGET_LIST_BY_CATEGORY["other"]
        target_list = TARGET_LIST_BY_CATEGORY[target_category]
        if not review_item:
            return

        if source_list != target_list:
            await _remove_from_list(source_list, review_item)
            await hass.services.async_call(
                "todo",
                "add_item",
                {"item": review_item},
                target={"entity_id": target_list},
                blocking=True,
            )

        if learn and target_category in CATEGORIES:
            norm = _normalize_term(review_item)
            terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
            existing = set(terms_obj.data.get(target_category, []))
            if norm and norm not in existing:
                terms_obj.data.setdefault(target_category, []).append(norm)
                await _save()
                await _sync_helpers_internal()

        await _set_helper_if_exists(REVIEW_PENDING_HELPER, "off")
        await _set_helper_if_exists(REVIEW_ITEM_HELPER, "")
        await _set_helper_if_exists(REVIEW_SOURCE_HELPER, "")
        await hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": "grocery_uncategorized"},
            blocking=True,
        )

    hass.services.async_register(DOMAIN, SERVICE_LEARN_TERM, _learn_term, schema=LEARN_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FORGET_TERM, _forget_term, schema=FORGET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SYNC_HELPERS, _sync_helpers)
    hass.services.async_register(DOMAIN, SERVICE_ROUTE_ITEM, _route_item, schema=ROUTE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_APPLY_REVIEW, _apply_review, schema=APPLY_REVIEW_SCHEMA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Grocery Learning from config entry."""
    await _async_setup_runtime(hass)
    hass.data[DOMAIN]["entry"] = entry

    async def _handle_call_service(event) -> None:
        if not entry.data.get(CONF_AUTO_ROUTE_INBOX, True):
            return
        data = event.data.get("service_data", {})
        if event.data.get("domain") != "todo" or event.data.get("service") != "add_item":
            return
        eid = data.get("entity_id", "")
        list_id = eid[0] if isinstance(eid, list) and eid else eid
        inbox_entity = entry.data.get(CONF_INBOX_ENTITY, "todo.grocery_inbox")
        item_text = str(data.get("item", "")).strip()
        if list_id != inbox_entity or not item_text:
            return
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ROUTE_ITEM,
            {
                "item": item_text,
                "source_list": inbox_entity,
                "remove_from_source": True,
                "review_on_other": True,
            },
            blocking=True,
        )

    remove_listener = hass.bus.async_listen("call_service", _handle_call_service)
    hass.data[DOMAIN]["remove_listener"] = remove_listener
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    remove_listener = hass.data.get(DOMAIN, {}).pop("remove_listener", None)
    if remove_listener:
        remove_listener()
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True
