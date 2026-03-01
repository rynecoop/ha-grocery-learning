"""Local Grocery Assistant custom integration."""

from __future__ import annotations

import logging
import re
import asyncio
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTO_DASHBOARD,
    CONF_AUTO_PROVISION,
    CONF_AUTO_ROUTE_INBOX,
    CONF_CATEGORIES,
    CONF_INBOX_ENTITY,
    CONF_NOTIFY_SERVICE,
    DEFAULT_CATEGORIES,
    DEFAULT_KEYWORDS_BY_CATEGORY,
    DUPLICATE_PENDING_BY_HELPER,
    DUPLICATE_PENDING_HELPER,
    DUPLICATE_PENDING_ITEM_HELPER,
    DUPLICATE_PENDING_KEY_HELPER,
    DUPLICATE_PENDING_SOURCE_HELPER,
    DUPLICATE_PENDING_TARGET_HELPER,
    DUPLICATE_PENDING_WHEN_HELPER,
    DOMAIN,
    HELPER_BY_CATEGORY,
    REVIEW_CATEGORY_HELPER,
    REVIEW_ITEM_HELPER,
    REVIEW_PENDING_HELPER,
    REVIEW_SOURCE_HELPER,
    SERVICE_APPLY_REVIEW,
    SERVICE_CONFIRM_DUPLICATE,
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
        vol.Required("category"): cv.string,
        vol.Required("term"): cv.string,
    }
)

FORGET_SCHEMA = vol.Schema(
    {
        vol.Optional("category"): cv.string,
        vol.Required("term"): cv.string,
    }
)

ROUTE_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("item"): cv.string,
        vol.Optional("source_list", default=""): cv.string,
        vol.Optional("remove_from_source", default=False): cv.boolean,
        vol.Optional("review_on_other", default=True): cv.boolean,
        vol.Optional("allow_duplicate", default=False): cv.boolean,
        vol.Optional("source", default=""): cv.string,
    }
)

APPLY_REVIEW_SCHEMA = vol.Schema(
    {
        vol.Optional("category"): cv.string,
        vol.Optional("learn", default=True): cv.boolean,
    }
)

CONFIRM_DUPLICATE_SCHEMA = vol.Schema(
    {
        vol.Required("decision"): vol.In(["add", "skip"]),
    }
)


def _normalize_term(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_category(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _display_name_for_category(category: str) -> str:
    return category.replace("_", " ").title()


def _target_list_for_category(category: str) -> str:
    if category in TARGET_LIST_BY_CATEGORY:
        return TARGET_LIST_BY_CATEGORY[category]
    return f"todo.grocery_{category}"


def _helper_for_category(category: str) -> str:
    if category in HELPER_BY_CATEGORY:
        return HELPER_BY_CATEGORY[category]
    return f"input_text.grocery_learned_{category}"


def _entry_value(entry: ConfigEntry | None, key: str, default: Any) -> Any:
    if entry is None:
        return default
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _item_meta_key(list_entity: str, normalized_item: str) -> str:
    return f"{list_entity}|{normalized_item}"


def _friendly_source(source: str) -> str:
    lookup = {
        "typed": "Typed",
        "voice_assistant": "Voice Assistant",
        "automation": "Automation",
        "service_call": "Service Call",
        "duplicate_confirmation": "Duplicate Confirmation",
        "unknown": "Unknown",
    }
    return lookup.get(source, source.replace("_", " ").title())


def _relative_time(iso_value: str) -> str:
    if not iso_value:
        return "Unknown"
    try:
        when = dt_util.parse_datetime(iso_value)
    except (TypeError, ValueError):
        return "Unknown"
    if when is None:
        return "Unknown"
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt_util.UTC)

    delta = dt_util.utcnow() - when
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def _categories_from_entry(entry: ConfigEntry | None) -> list[str]:
    raw = _entry_value(entry, CONF_CATEGORIES, list(DEFAULT_CATEGORIES))
    if isinstance(raw, str):
        values = [_normalize_category(v) for v in raw.replace("\n", ",").split(",")]
    elif isinstance(raw, list):
        values = [_normalize_category(str(v)) for v in raw]
    else:
        values = []

    cleaned: list[str] = []
    for value in values:
        if not value or value == "other":
            continue
        if value not in cleaned:
            cleaned.append(value)
    return cleaned or list(DEFAULT_CATEGORIES)


async def _async_setup_runtime(hass: HomeAssistant) -> None:
    """Set up runtime state/services once."""
    hass.data.setdefault(DOMAIN, {})
    data = hass.data[DOMAIN]
    if data.get("runtime_ready"):
        return

    store = GroceryLearningStore(hass)
    terms = await store.load(list(DEFAULT_CATEGORIES))
    item_meta = await store.load_item_meta()

    data["store"] = store
    data["terms"] = terms
    data["item_meta"] = item_meta
    data["pending_duplicate"] = {}
    data["categories"] = list(DEFAULT_CATEGORIES)

    async def _save() -> None:
        await store.save(hass.data[DOMAIN]["terms"], hass.data[DOMAIN].get("item_meta", {}))

    def _active_categories() -> list[str]:
        return list(hass.data[DOMAIN].get("categories", list(DEFAULT_CATEGORIES)))

    async def _learn_term(call: ServiceCall) -> None:
        category = _normalize_category(call.data["category"])
        term = _normalize_term(call.data["term"])
        categories = _active_categories()
        if category not in categories:
            raise vol.Invalid(f"Unknown category '{category}'")
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

        category_input = str(call.data.get("category", "")).strip()
        selected = _normalize_category(category_input) if category_input else ""
        categories = _active_categories()
        if selected and selected not in categories:
            raise vol.Invalid(f"Unknown category '{selected}'")

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
        """Sync learned terms to optional input_text helpers used by legacy YAML router."""
        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        for category in _active_categories():
            helper = _helper_for_category(category)
            if hass.states.get(helper) is None:
                continue
            merged = "|".join(sorted(set(terms_obj.data.get(category, []))))
            if len(merged) > 255:
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
        needle = _normalize_term(item_summary)
        for attempt in range(4):
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
            match = next(
                (
                    i
                    for i in items
                    if _normalize_term(str(i.get("summary", "")).strip()) == needle
                ),
                None,
            )
            if match:
                remove_id = str(match.get("uid", "")).strip() or str(match.get("summary", "")).strip()
                if remove_id:
                    await hass.services.async_call(
                        "todo",
                        "remove_item",
                        {"item": remove_id},
                        target={"entity_id": list_entity},
                        blocking=True,
                    )
                return
            if attempt < 3:
                await asyncio.sleep(0.25)

    async def _user_name_from_context(call: ServiceCall) -> tuple[str, str]:
        user_id = call.context.user_id or ""
        if not user_id:
            return "", "Voice Assistant"
        user = await hass.auth.async_get_user(user_id)
        if user and user.name:
            return user_id, user.name
        return user_id, "User"

    def _source_from_call(call: ServiceCall) -> str:
        explicit = str(call.data.get("source", "")).strip().lower()
        if explicit:
            return explicit
        if call.context.user_id:
            return "typed"
        if call.context.parent_id:
            return "automation"
        return "voice_assistant"

    def _meta_for_item(list_entity: str, normalized_item: str) -> dict[str, str]:
        meta_map: dict[str, dict[str, str]] = hass.data[DOMAIN].get("item_meta", {})
        return dict(meta_map.get(_item_meta_key(list_entity, normalized_item), {}))

    async def _record_item_meta(
        list_entity: str,
        item_summary: str,
        call: ServiceCall,
        source_override: str | None = None,
    ) -> None:
        normalized_item = _normalize_term(item_summary)
        if not normalized_item:
            return

        user_id, user_name = await _user_name_from_context(call)
        source = source_override or _source_from_call(call)
        meta_map: dict[str, dict[str, str]] = hass.data[DOMAIN].setdefault("item_meta", {})
        key = _item_meta_key(list_entity, normalized_item)
        now_iso = dt_util.utcnow().isoformat()
        previous = meta_map.get(key, {})
        count = int(previous.get("add_count", "0") or "0") + 1
        meta_map[key] = {
            "last_added_at": now_iso,
            "last_added_by_user_id": user_id,
            "last_added_by_name": user_name,
            "last_source": source,
            "last_item_text": item_summary.strip(),
            "add_count": str(count),
        }
        await _save()

    async def _find_open_duplicate(list_entity: str, item_summary: str) -> dict[str, Any] | None:
        if not list_entity or hass.states.get(list_entity) is None:
            return None
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
        needle = _normalize_term(item_summary)
        for item in items:
            existing = _normalize_term(str(item.get("summary", "")))
            if existing and existing == needle:
                return item
        return None

    async def _clear_pending_duplicate() -> None:
        hass.data[DOMAIN]["pending_duplicate"] = {}
        await _set_helper_if_exists(DUPLICATE_PENDING_ITEM_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_TARGET_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_KEY_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_BY_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_WHEN_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_SOURCE_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_HELPER, "off")

    async def _set_pending_duplicate(
        *,
        item: str,
        target_list: str,
        normalized: str,
        existing_by: str,
        existing_source: str,
        existing_when: str,
    ) -> None:
        hass.data[DOMAIN]["pending_duplicate"] = {
            "item": item,
            "target_list": target_list,
            "normalized": normalized,
            "existing_by": existing_by,
            "existing_source": existing_source,
            "existing_when": existing_when,
        }
        await _set_helper_if_exists(DUPLICATE_PENDING_ITEM_HELPER, item)
        await _set_helper_if_exists(DUPLICATE_PENDING_TARGET_HELPER, target_list)
        await _set_helper_if_exists(DUPLICATE_PENDING_KEY_HELPER, normalized)
        await _set_helper_if_exists(DUPLICATE_PENDING_BY_HELPER, existing_by)
        await _set_helper_if_exists(DUPLICATE_PENDING_WHEN_HELPER, existing_when)
        await _set_helper_if_exists(DUPLICATE_PENDING_SOURCE_HELPER, existing_source)
        await _set_helper_if_exists(DUPLICATE_PENDING_HELPER, "on")

    async def _ensure_local_todo_list(entity_id: str, title: str) -> None:
        if hass.states.get(entity_id) is not None:
            return

        slug = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
        payloads = (
            {"storage_key": slug, "todo_list_name": title},
            {"todo_list_name": title},
        )

        for payload in payloads:
            try:
                result = await hass.config_entries.flow.async_init(
                    "local_todo",
                    context={"source": "user"},
                    data=payload,
                )
            except Exception as err:  # pragma: no cover
                _LOGGER.debug("local_todo async_init failed (%s): %s", payload, err)
                continue

            for _ in range(4):
                if not isinstance(result, Mapping):
                    break
                if result.get("type") in {"create_entry", "abort"}:
                    break
                if result.get("type") != "form" or "flow_id" not in result:
                    break

                next_input = dict(payload)
                data_schema = result.get("data_schema")
                schema_map = getattr(data_schema, "schema", {}) if data_schema else {}
                if isinstance(schema_map, dict):
                    next_input = {}
                    for marker, validator in schema_map.items():
                        key = getattr(marker, "schema", marker)
                        key_name = str(key)
                        if key_name in payload:
                            next_input[key_name] = payload[key_name]
                        elif "storage" in key_name:
                            next_input[key_name] = slug
                        elif "todo" in key_name or "name" in key_name or "title" in key_name:
                            next_input[key_name] = title
                        elif validator is bool:
                            next_input[key_name] = True
                result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=next_input)

            if hass.states.get(entity_id) is not None:
                return

    async def _ensure_required_lists(entry: ConfigEntry | None) -> None:
        if not bool(_entry_value(entry, CONF_AUTO_PROVISION, True)):
            return

        categories = _active_categories()
        inbox_entity = str(_entry_value(entry, CONF_INBOX_ENTITY, "todo.grocery_inbox"))
        await _ensure_local_todo_list(inbox_entity, "Grocery Inbox")

        for category in categories:
            await _ensure_local_todo_list(
                _target_list_for_category(category),
                f"Grocery {_display_name_for_category(category)}",
            )
        await _ensure_local_todo_list(_target_list_for_category("other"), "Grocery Other")

    async def _upsert_storage_dashboard_meta(
        dashboard_id: str,
        title: str,
        icon: str,
        require_admin: bool,
        url_path: str,
    ) -> None:
        dashboards_store = Store(hass, 1, "lovelace_dashboards")
        dashboards = await dashboards_store.async_load() or {}
        items = dashboards.get("items", [])
        if not isinstance(items, list):
            items = []

        updated = False
        for idx, item in enumerate(items):
            if isinstance(item, dict) and item.get("id") == dashboard_id:
                items[idx] = {
                    **item,
                    "id": dashboard_id,
                    "title": title,
                    "icon": icon,
                    "show_in_sidebar": True,
                    "require_admin": require_admin,
                    "mode": "storage",
                    "url_path": url_path,
                }
                updated = True
                break

        if not updated:
            items.append(
                {
                    "id": dashboard_id,
                    "title": title,
                    "icon": icon,
                    "show_in_sidebar": True,
                    "require_admin": require_admin,
                    "mode": "storage",
                    "url_path": url_path,
                }
            )

        dashboards["items"] = items
        await dashboards_store.async_save(dashboards)

    def _empty_card_for(category: str) -> dict[str, Any]:
        name = _display_name_for_category(category)
        entity = _target_list_for_category(category)
        return {
            "type": "conditional",
            "conditions": [{"entity": entity, "state": "0"}],
            "card": {"type": "markdown", "content": f"No items in {name}.", "title": name},
        }

    def _todo_card_for(category: str) -> dict[str, Any]:
        name = _display_name_for_category(category)
        entity = _target_list_for_category(category)
        return {
            "type": "conditional",
            "conditions": [{"entity": entity, "state_not": "0"}],
            "card": {
                "type": "todo-list",
                "title": name,
                "entity": entity,
                "show_completed": False,
                "hide_create": True,
                "hide_section_headers": True,
            },
        }

    def _build_main_dashboard_config(entry: ConfigEntry | None) -> dict[str, Any]:
        categories = _active_categories()
        inbox_entity = str(_entry_value(entry, CONF_INBOX_ENTITY, "todo.grocery_inbox"))
        quick_add_card: dict[str, Any] = {
            "display_order": "none",
            "item_tap_action": "toggle",
            "type": "todo-list",
            "entity": inbox_entity,
            "hide_completed": True,
            "hide_section_headers": True,
            "title": "Quick Add",
            "hide_create": False,
            "card_mod": {
                "style": (
                    "ha-card $ h1.card-header {\n"
                    "  padding: 16px 16px 4px 16px !important;\n"
                    "}\n"
                    "ha-card $ .card-content {\n"
                    "  padding-top: 0 !important;\n"
                    "}\n"
                    "ha-empty-state,\n"
                    "ha-md-empty-state,\n"
                    ".empty,\n"
                    ".empty-state,\n"
                    ".placeholder {\n"
                    "  display: none !important;\n"
                    "}\n"
                )
            },
        }

        cards: list[dict[str, Any]] = [quick_add_card]

        for category in categories:
            cards.append(_empty_card_for(category))
            cards.append(_todo_card_for(category))

        cards.append(_empty_card_for("other"))
        cards.append(_todo_card_for("other"))
        has_duplicate_helpers = all(
            hass.states.get(entity_id) is not None
            for entity_id in (
                DUPLICATE_PENDING_HELPER,
                DUPLICATE_PENDING_ITEM_HELPER,
                DUPLICATE_PENDING_TARGET_HELPER,
                DUPLICATE_PENDING_BY_HELPER,
                DUPLICATE_PENDING_WHEN_HELPER,
                DUPLICATE_PENDING_SOURCE_HELPER,
            )
        )
        if has_duplicate_helpers:
            cards.append(
                {
                    "type": "conditional",
                    "conditions": [{"entity": DUPLICATE_PENDING_HELPER, "state": "on"}],
                    "card": {
                        "type": "vertical-stack",
                        "cards": [
                            {
                                "type": "entities",
                                "title": "Duplicate Found",
                                "show_header_toggle": False,
                                "entities": [
                                    {"entity": DUPLICATE_PENDING_ITEM_HELPER, "name": "Item"},
                                    {"entity": DUPLICATE_PENDING_TARGET_HELPER, "name": "List"},
                                    {"entity": DUPLICATE_PENDING_BY_HELPER, "name": "Added by"},
                                    {"entity": DUPLICATE_PENDING_WHEN_HELPER, "name": "Added"},
                                    {"entity": DUPLICATE_PENDING_SOURCE_HELPER, "name": "Source"},
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {
                                        "type": "button",
                                        "name": "Add Anyway",
                                        "icon": "mdi:cart-plus",
                                        "tap_action": {
                                            "action": "call-service",
                                            "service": f"{DOMAIN}.{SERVICE_CONFIRM_DUPLICATE}",
                                            "service_data": {"decision": "add"},
                                        },
                                    },
                                    {
                                        "type": "button",
                                        "name": "Skip",
                                        "icon": "mdi:close-circle-outline",
                                        "tap_action": {
                                            "action": "call-service",
                                            "service": f"{DOMAIN}.{SERVICE_CONFIRM_DUPLICATE}",
                                            "service_data": {"decision": "skip"},
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                }
            )

        has_review_helpers = all(
            hass.states.get(entity_id) is not None
            for entity_id in (
                REVIEW_PENDING_HELPER,
                REVIEW_ITEM_HELPER,
                REVIEW_CATEGORY_HELPER,
                "input_button.grocery_review_apply",
            )
        )
        if has_review_helpers:
            cards.append(
                {
                    "type": "conditional",
                    "conditions": [{"entity": REVIEW_PENDING_HELPER, "state": "on"}],
                    "card": {
                        "type": "entities",
                        "title": "Review & Learn",
                        "show_header_toggle": False,
                        "entities": [
                            {"entity": REVIEW_ITEM_HELPER, "name": "Item to review"},
                            {"entity": REVIEW_CATEGORY_HELPER, "name": "Move to category"},
                            {"entity": "input_button.grocery_review_apply", "name": "Apply Category + Learn"},
                        ],
                    },
                }
            )

        return {
            "config": {
                "title": "Grocery",
                "views": [
                    {
                        "title": "Grocery",
                        "path": "grocery",
                        "icon": "mdi:cart-variant",
                        "type": "masonry",
                        "cards": cards,
                    }
                ],
            }
        }

    def _build_admin_dashboard_config() -> dict[str, Any]:
        categories = _active_categories()
        learned_entities = [
            {"entity": _helper_for_category(category), "name": f"{_display_name_for_category(category)} Learned Terms"}
            for category in categories
            if hass.states.get(_helper_for_category(category)) is not None
        ]
        cards: list[dict[str, Any]] = []

        order_text = " -> ".join([_display_name_for_category(c) for c in categories] + ["Other"])
        cards.append(
            {
                "type": "markdown",
                "title": "Admin Overview",
                "content": (
                    "Local Grocery Assistant is running in integration-managed mode.\n\n"
                    f"**Current category order:** {order_text}\n\n"
                    "To change routing order or categories, open the integration options in "
                    "`Settings -> Devices & Services`."
                ),
            }
        )

        inbox_entity = str(_entry_value(hass.data[DOMAIN].get("entry"), CONF_INBOX_ENTITY, "todo.grocery_inbox"))
        list_entities = [inbox_entity] + [_target_list_for_category(c) for c in categories] + [_target_list_for_category("other")]
        cards.append(
            {
                "type": "entities",
                "title": "List Status",
                "show_header_toggle": False,
                "entities": [{"entity": ent} for ent in list_entities if hass.states.get(ent) is not None],
            }
        )

        has_duplicate_helpers = all(
            hass.states.get(entity_id) is not None
            for entity_id in (
                DUPLICATE_PENDING_HELPER,
                DUPLICATE_PENDING_ITEM_HELPER,
                DUPLICATE_PENDING_TARGET_HELPER,
                DUPLICATE_PENDING_BY_HELPER,
                DUPLICATE_PENDING_WHEN_HELPER,
                DUPLICATE_PENDING_SOURCE_HELPER,
            )
        )
        if has_duplicate_helpers:
            cards.append(
                {
                    "type": "conditional",
                    "conditions": [{"entity": DUPLICATE_PENDING_HELPER, "state": "on"}],
                    "card": {
                        "type": "vertical-stack",
                        "cards": [
                            {
                                "type": "entities",
                                "title": "Duplicate Pending",
                                "show_header_toggle": False,
                                "entities": [
                                    {"entity": DUPLICATE_PENDING_ITEM_HELPER, "name": "Item"},
                                    {"entity": DUPLICATE_PENDING_TARGET_HELPER, "name": "Target List"},
                                    {"entity": DUPLICATE_PENDING_BY_HELPER, "name": "Added by"},
                                    {"entity": DUPLICATE_PENDING_WHEN_HELPER, "name": "Added"},
                                    {"entity": DUPLICATE_PENDING_SOURCE_HELPER, "name": "Source"},
                                ],
                            },
                            {
                                "type": "grid",
                                "columns": 2,
                                "square": False,
                                "cards": [
                                    {
                                        "type": "button",
                                        "name": "Add Anyway",
                                        "icon": "mdi:cart-plus",
                                        "tap_action": {
                                            "action": "call-service",
                                            "service": f"{DOMAIN}.{SERVICE_CONFIRM_DUPLICATE}",
                                            "service_data": {"decision": "add"},
                                        },
                                    },
                                    {
                                        "type": "button",
                                        "name": "Skip",
                                        "icon": "mdi:close-circle-outline",
                                        "tap_action": {
                                            "action": "call-service",
                                            "service": f"{DOMAIN}.{SERVICE_CONFIRM_DUPLICATE}",
                                            "service_data": {"decision": "skip"},
                                        },
                                    },
                                ],
                            },
                        ],
                    },
                }
            )

        has_review_helpers = all(
            hass.states.get(entity_id) is not None
            for entity_id in (
                REVIEW_PENDING_HELPER,
                REVIEW_ITEM_HELPER,
                REVIEW_CATEGORY_HELPER,
                "input_button.grocery_review_apply",
            )
        )
        if has_review_helpers:
            cards.append(
                {
                    "type": "entities",
                    "title": "Review Status",
                    "show_header_toggle": False,
                    "entities": [
                        {"entity": REVIEW_PENDING_HELPER, "name": "Review Pending"},
                        {"entity": REVIEW_ITEM_HELPER, "name": "Pending Item"},
                        {"entity": REVIEW_CATEGORY_HELPER, "name": "Review Category"},
                        {"entity": "input_button.grocery_review_apply", "name": "Apply Category + Learn"},
                    ],
                }
            )

        if learned_entities:
            cards.append(
                {
                    "type": "entities",
                    "title": "Learned Terms (Admin)",
                    "show_header_toggle": False,
                    "entities": learned_entities,
                }
            )

        if not cards:
            cards.append(
                {
                    "type": "markdown",
                    "content": "No admin entities available yet. Reload integration after setup.",
                }
            )

        return {
            "config": {
                "title": "Grocery Admin",
                "views": [
                    {
                        "title": "Grocery Admin",
                        "path": "grocery-admin",
                        "icon": "mdi:shield-crown",
                        "type": "masonry",
                        "cards": cards,
                    }
                ],
            }
        }

    async def _ensure_dashboards(entry: ConfigEntry | None) -> None:
        if not bool(_entry_value(entry, CONF_AUTO_DASHBOARD, True)):
            return

        await _upsert_storage_dashboard_meta("grocery", "Grocery", "mdi:cart-variant", False, "grocery")
        await _upsert_storage_dashboard_meta("grocery_admin", "Grocery Admin", "mdi:shield-crown", True, "grocery-admin")

        main_store = Store(hass, 1, "lovelace.grocery")
        admin_store = Store(hass, 1, "lovelace.grocery_admin")
        await main_store.async_save(_build_main_dashboard_config(entry))
        await admin_store.async_save(_build_admin_dashboard_config())

    def _get_category_for_term(terms_obj: LearnedTerms, normalized: str) -> str:
        categories = _active_categories()
        if normalized:
            for category in categories:
                if normalized in set(terms_obj.data.get(category, [])):
                    return category

        tokens = [t for t in normalized.split(" ") if t]
        token_forms: set[str] = set(tokens)
        for token in tokens:
            if len(token) > 3 and token.endswith("s"):
                token_forms.add(token[:-1])
            if len(token) > 4 and token.endswith("es"):
                token_forms.add(token[:-2])

        def _keyword_match(keyword: str) -> bool:
            parts = [p for p in keyword.split(" ") if p]
            return bool(parts) and all(part in token_forms for part in parts)

        for category in categories:
            words = DEFAULT_KEYWORDS_BY_CATEGORY.get(category, ())
            if any(_keyword_match(word) for word in words):
                return category
        return "other"

    async def _route_item(call: ServiceCall) -> None:
        raw_item = call.data["item"]
        source_list = call.data["source_list"].strip()
        remove_from_source = bool(call.data["remove_from_source"])
        review_on_other = bool(call.data["review_on_other"])
        allow_duplicate = bool(call.data["allow_duplicate"])
        normalized = _normalize_term(raw_item)
        if not normalized:
            return

        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        category = _get_category_for_term(terms_obj, normalized)
        target_list = _target_list_for_category(category)

        entry = hass.data.get(DOMAIN, {}).get("entry")
        await _ensure_required_lists(entry)

        if hass.states.get(target_list) is None:
            _LOGGER.warning("Target list %s missing for category %s", target_list, category)
            target_list = _target_list_for_category("other")

        duplicate_item = await _find_open_duplicate(target_list, raw_item)
        if duplicate_item and not allow_duplicate:
            target_state = hass.states.get(target_list)
            target_name = (
                str(target_state.attributes.get("friendly_name", "")).strip()
                if target_state is not None
                else target_list
            )
            meta = _meta_for_item(target_list, normalized)
            existing_by = meta.get("last_added_by_name", "Unknown")
            existing_source = _friendly_source(meta.get("last_source", "unknown"))
            existing_when = _relative_time(meta.get("last_added_at", ""))
            await _set_pending_duplicate(
                item=raw_item,
                target_list=target_list,
                normalized=normalized,
                existing_by=existing_by,
                existing_source=existing_source,
                existing_when=existing_when,
            )
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Grocery duplicate",
                    "message": (
                        f"**{raw_item}** is already on **{target_name}**.\n\n"
                        f"- Added by: **{existing_by}**\n"
                        f"- Added: **{existing_when}**\n"
                        f"- Source: **{existing_source}**\n\n"
                        "Use the Grocery dashboard to **Add anyway** or **Skip**."
                    ),
                    "notification_id": "grocery_duplicate",
                },
                blocking=True,
            )
            if remove_from_source:
                await _remove_from_list(source_list, raw_item)
            return

        await hass.services.async_call(
            "todo",
            "add_item",
            {"item": raw_item},
            target={"entity_id": target_list},
            blocking=True,
        )
        await _record_item_meta(target_list, raw_item, call)

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
            notify_service = str(_entry_value(entry, CONF_NOTIFY_SERVICE, "")).strip()
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

        categories = _active_categories()
        normalized_category = _normalize_category(category_in)
        if category_in == "keep other":
            target_category = "other"
        elif normalized_category in categories:
            target_category = normalized_category
        else:
            target_category = "other"

        review_item_state = hass.states.get(REVIEW_ITEM_HELPER)
        source_list_state = hass.states.get(REVIEW_SOURCE_HELPER)
        review_item = str(review_item_state.state).strip() if review_item_state else ""
        source_list = str(source_list_state.state).strip() if source_list_state else _target_list_for_category("other")
        target_list = _target_list_for_category(target_category)
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

        if learn and target_category in categories:
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

    async def _confirm_duplicate(call: ServiceCall) -> None:
        decision = str(call.data.get("decision", "")).strip().lower()
        if decision not in {"add", "skip"}:
            raise vol.Invalid("decision must be 'add' or 'skip'")

        pending = dict(hass.data[DOMAIN].get("pending_duplicate", {}))
        item = str(pending.get("item", "")).strip()
        target_list = str(pending.get("target_list", "")).strip()

        if not item:
            item_state = hass.states.get(DUPLICATE_PENDING_ITEM_HELPER)
            item = str(item_state.state).strip() if item_state else ""
        if not target_list:
            target_state = hass.states.get(DUPLICATE_PENDING_TARGET_HELPER)
            target_list = str(target_state.state).strip() if target_state else ""

        if decision == "add" and item and target_list and hass.states.get(target_list) is not None:
            await hass.services.async_call(
                "todo",
                "add_item",
                {"item": item},
                target={"entity_id": target_list},
                blocking=True,
            )
            await _record_item_meta(target_list, item, call, source_override="duplicate_confirmation")

        await _clear_pending_duplicate()
        await hass.services.async_call(
            "persistent_notification",
            "dismiss",
            {"notification_id": "grocery_duplicate"},
            blocking=True,
        )

    hass.services.async_register(DOMAIN, SERVICE_LEARN_TERM, _learn_term, schema=LEARN_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FORGET_TERM, _forget_term, schema=FORGET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SYNC_HELPERS, _sync_helpers)
    hass.services.async_register(DOMAIN, SERVICE_ROUTE_ITEM, _route_item, schema=ROUTE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_APPLY_REVIEW, _apply_review, schema=APPLY_REVIEW_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIRM_DUPLICATE,
        _confirm_duplicate,
        schema=CONFIRM_DUPLICATE_SCHEMA,
    )

    data["ensure_required_lists"] = _ensure_required_lists
    data["ensure_dashboards"] = _ensure_dashboards
    data["runtime_ready"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Local Grocery Assistant from config entry."""
    await _async_setup_runtime(hass)
    data = hass.data[DOMAIN]
    data["entry"] = entry
    data["categories"] = _categories_from_entry(entry)

    store: GroceryLearningStore = data["store"]
    data["terms"] = await store.load(data["categories"])
    data["item_meta"] = await store.load_item_meta()

    ensure_required_lists = data.get("ensure_required_lists")
    if ensure_required_lists:
        await ensure_required_lists(entry)

    ensure_dashboards = data.get("ensure_dashboards")
    if ensure_dashboards:
        await ensure_dashboards(entry)

    async def _handle_call_service(event) -> None:
        if not _entry_value(entry, CONF_AUTO_ROUTE_INBOX, True):
            return
        data_event = event.data.get("service_data", {})
        if event.data.get("domain") != "todo" or event.data.get("service") != "add_item":
            return

        def _extract_entity_id() -> str:
            top_target = event.data.get("target", {})
            service_target = data_event.get("target", {})
            candidates: list[Any] = [
                data_event.get("entity_id", ""),
                service_target.get("entity_id", "") if isinstance(service_target, dict) else "",
                top_target.get("entity_id", "") if isinstance(top_target, dict) else "",
            ]
            for candidate in candidates:
                if isinstance(candidate, list) and candidate:
                    return str(candidate[0]).strip()
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            return ""

        list_id = _extract_entity_id()
        inbox_entity = _entry_value(entry, CONF_INBOX_ENTITY, "todo.grocery_inbox")
        item_text = str(data_event.get("item", "")).strip()
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
                "source": "typed",
            },
            blocking=True,
            context=event.context,
        )

    entry.async_on_unload(hass.bus.async_listen("call_service", _handle_call_service))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return True
