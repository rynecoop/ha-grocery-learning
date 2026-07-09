"""Local List Assist custom integration."""

from __future__ import annotations

import json
import logging
import re
import asyncio
from collections.abc import Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from uuid import uuid4

import voluptuous as vol
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.frontend import async_remove_panel
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import callback, Context, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, intent as intent_helper
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AUTO_DASHBOARD,
    CONF_AUTO_PROVISION,
    CONF_AUTO_ROUTE_INBOX,
    CONF_CATEGORIES,
    CONF_DASHBOARD_NAME,
    CONF_DEBUG_MODE,
    CONF_DEFAULT_GROCERY_CATEGORIES,
    CONF_EXPERIMENTAL_MULTILIST,
    CONF_INBOX_ENTITY,
    COMPLETED_LIST_ENTITY,
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
    SERVICE_ADD_TO_LIST,
    SERVICE_INSTALL_VOICE_SENTENCES,
    SERVICE_APPLY_REVIEW,
    SERVICE_CONFIRM_DUPLICATE,
    SERVICE_FORGET_TERM,
    SERVICE_LEARN_TERM,
    SERVICE_ROUTE_ITEM,
    SERVICE_SYNC_HELPERS,
    TARGET_LIST_BY_CATEGORY,
)
from .matching import normalize_voice_list_name, resolve_list_id_from_voice_name
from .list_templates import categories_for_template, template_presets
from .multilist_ops import archive_list as apply_archive_list, delete_archived_list as apply_delete_archived_list, restore_archived_list as apply_restore_archived_list
from .item_logic import (
    canonical_item_phrase as _canonical_item_phrase,
    category_for_term as _category_for_term,
    coerce_quantity as _coerce_quantity,
    decode_contributors as _decode_contributors,
    display_item_summary as _display_item_summary,
    format_contributors as _format_contributors,
    merge_meta_records as _merge_meta_records,
    meta_quantity as _meta_quantity,
    normalize_category as _normalize_category,
    normalize_list_id as _normalize_list_id,
    reorder_category_items as _reorder_category_items,
)
from .storage import GroceryLearningStore, LearnedTerms

_LOGGER = logging.getLogger(__name__)
MAX_ACTIVITY_ITEMS = 40
INTENT_LOCAL_LIST_ASSIST_ADD_ITEM = "LocalListAssistAddItem"
LIVE_REVISION_ENTITY_ID = "sensor.local_list_assist_live_revision"

# Tracks whether the current asyncio task is already running inside a locked,
# state-mutating action. It is copied into child tasks that Home Assistant
# creates for nested service calls, so a locked action that dispatches one of
# our own services re-enters safely instead of deadlocking on the lock.
_IN_LOCKED_ACTION: ContextVar[bool] = ContextVar("lla_in_locked_action", default=False)

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
        vol.Optional("quantity", default=1): vol.Coerce(int),
        vol.Optional("list_id", default=""): cv.string,
        vol.Optional("source_list", default=""): cv.string,
        vol.Optional("source_list_name", default=""): cv.string,
        vol.Optional("remove_from_source", default=False): cv.boolean,
        vol.Optional("review_on_other", default=True): cv.boolean,
        vol.Optional("allow_duplicate", default=False): cv.boolean,
        vol.Optional("interactive_duplicate", default=False): cv.boolean,
        vol.Optional("source", default=""): cv.string,
        vol.Optional("actor_name", default=""): cv.string,
        vol.Optional("actor_user_id", default=""): cv.string,
    }
)

ADD_TO_LIST_SCHEMA = vol.Schema(
    {
        vol.Required("item"): cv.string,
        vol.Optional("quantity", default=1): vol.Coerce(int),
        vol.Optional("list_name", default=""): cv.string,
        vol.Optional("list_id", default=""): cv.string,
        vol.Optional("source", default="service_call"): cv.string,
        vol.Optional("actor_name", default=""): cv.string,
        vol.Optional("actor_user_id", default=""): cv.string,
        vol.Optional("allow_duplicate", default=False): cv.boolean,
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
        vol.Optional("actor_name", default=""): cv.string,
        vol.Optional("actor_user_id", default=""): cv.string,
    }
)

INSTALL_VOICE_SENTENCES_SCHEMA = vol.Schema(
    {
        vol.Optional("language", default="en"): cv.string,
    }
)

REVIEW_STATUS_PENDING_ENTITY = "sensor.grocery_review_pending_status"
REVIEW_STATUS_ITEM_ENTITY = "sensor.grocery_review_item"
REVIEW_STATUS_SOURCE_ENTITY = "sensor.grocery_review_source"

DUPLICATE_STATUS_PENDING_ENTITY = "sensor.grocery_duplicate_pending_status"
DUPLICATE_STATUS_ITEM_ENTITY = "sensor.grocery_duplicate_item"
DUPLICATE_STATUS_TARGET_ENTITY = "sensor.grocery_duplicate_target"
DUPLICATE_STATUS_BY_ENTITY = "sensor.grocery_duplicate_added_by"
DUPLICATE_STATUS_WHEN_ENTITY = "sensor.grocery_duplicate_added_when"
DUPLICATE_STATUS_SOURCE_ENTITY = "sensor.grocery_duplicate_source"
CONF_WIZARD_COMPLETED = "wizard_completed"


class GroceryLearningDashboardView(HomeAssistantView):
    """Return dashboard payload for Local List Assist app."""

    url = "/api/grocery_learning/dashboard"
    name = "api:grocery_learning:dashboard"
    requires_auth = True

    @staticmethod
    def _empty_payload(error: str = "") -> dict[str, Any]:
        return {
            "categories": ["other"],
            "groups": [
                {
                    "category": "other",
                    "title": "Other",
                    "items": [],
                }
            ],
            "completed": [],
            "lists": [],
            "pending_review": {"pending": False, "item": "", "source_list": ""},
            "pending_duplicate": {"pending": False, "item": "", "target": ""},
            "settings": {
                "categories": [],
                "inbox_entity": "todo.grocery_inbox",
                "auto_route_inbox": True,
                "auto_provision": True,
                "experimental_multilist": False,
                "default_grocery_categories": True,
                "debug_mode": False,
                "dashboard_name": "Local List Assist",
            },
            "system": {"missing_lists": [], "runtime_ready": False},
            "activity": [],
            "setup": {"completed": False},
            "error": error,
        }

    async def get(self, request):
        try:
            hass = request.app["hass"]
            domain_data = hass.data.get(DOMAIN, {})
            if not isinstance(domain_data, Mapping):
                return web.json_response(self._empty_payload("runtime_state_invalid"))

            builder = domain_data.get("build_dashboard_payload")
            if not callable(builder):
                await _async_setup_runtime(hass)
                domain_data = hass.data.get(DOMAIN, {})
                builder = domain_data.get("build_dashboard_payload") if isinstance(domain_data, Mapping) else None
                if not callable(builder):
                    return web.json_response(self._empty_payload("not_ready"))

            # Use the shared slug normalizer so the dashboard and the action
            # handlers agree on list-id canonicalization (empty stays empty here
            # so the builder falls back to the active list).
            requested_list_id = _normalize_category(str(request.query.get("list_id", "")))
            try:
                payload = await builder(requested_list_id or None)
            except TypeError:
                payload = await builder()
            if not isinstance(payload, dict):
                return web.json_response(self._empty_payload("invalid_payload"))

            payload.setdefault("categories", ["other"])
            payload.setdefault("groups", [])
            payload.setdefault("completed", [])
            payload.setdefault("lists", [])
            payload.setdefault("pending_review", {"pending": False, "item": "", "source_list": ""})
            payload.setdefault("pending_duplicate", {"pending": False, "item": "", "target": ""})
            payload.setdefault(
                "settings",
                {
                    "categories": [],
                    "inbox_entity": "todo.grocery_inbox",
                    "auto_route_inbox": True,
                    "auto_provision": True,
                    "experimental_multilist": False,
                    "default_grocery_categories": True,
                    "debug_mode": False,
                },
            )
            payload.setdefault("system", {"missing_lists": [], "runtime_ready": False})
            payload.setdefault("activity", [])
            payload.setdefault("setup", {"completed": False})
            payload.setdefault("error", "")
            return web.json_response(payload)
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Failed to build Grocery dashboard payload")
            try:
                return web.json_response(self._empty_payload(str(err)))
            except Exception:
                return web.Response(status=200, text='{"error":"unknown"}', content_type="application/json")


class GroceryLearningActionView(HomeAssistantView):
    """Handle custom app actions."""

    url = "/api/grocery_learning/action"
    name = "api:grocery_learning:action"
    requires_auth = True

    async def post(self, request):
        hass = request.app["hass"]
        handler = hass.data.get(DOMAIN, {}).get("handle_dashboard_action")
        if handler is None:
            await _async_setup_runtime(hass)
            handler = hass.data.get(DOMAIN, {}).get("handle_dashboard_action")
        if handler is None:
            return self.json({"ok": False, "error": "not_ready"})
        try:
            payload = await request.json()
            request_user = request.get("hass_user")
            if request_user is not None:
                payload["_request_user_id"] = str(getattr(request_user, "id", "") or "").strip()
            result = await handler(payload)
            return self.json(result)
        except Exception as err:  # pragma: no cover
            _LOGGER.exception("Failed Grocery dashboard action")
            return self.json({"ok": False, "error": str(err)})


def _normalize_term(value: str) -> str:
    return _canonical_item_phrase(value)


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


def _category_for_list_entity(list_entity: str) -> str:
    for category, entity_id in TARGET_LIST_BY_CATEGORY.items():
        if entity_id == list_entity:
            return category
    return "other"


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
        "review_move": "Review Move",
        "unknown": "Unknown",
    }
    return lookup.get(source, source.replace("_", " ").title())


def _dashboard_name(entry: ConfigEntry | None) -> str:
    value = str(_entry_value(entry, CONF_DASHBOARD_NAME, "Local List Assist")).strip()
    return value or "Local List Assist"


def _admin_dashboard_name(entry: ConfigEntry | None) -> str:
    return f"{_dashboard_name(entry)} Admin"


def _frontend_module_url() -> str:
    """Return the frontend module URL with a version query for cache busting."""
    version = "dev"
    try:
        manifest_path = Path(__file__).resolve().parent / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = str(manifest.get("version", version)).strip() or version
    except Exception:  # pragma: no cover - defensive fallback
        _LOGGER.debug("Could not read manifest version for frontend cache busting", exc_info=True)
    return f"/grocery_learning-panel/local-list-assist-panel.js?v={version}"


async def _register_sidebar_panel(hass: HomeAssistant, title: str, *, replace_existing: bool = False) -> None:
    """Register the Home Assistant sidebar panel with the requested title."""
    data = hass.data.setdefault(DOMAIN, {})
    if replace_existing and data.get("panel_registered"):
        try:
            async_remove_panel(hass, "grocery-app")
        except Exception:  # pragma: no cover - defensive against HA API changes
            _LOGGER.debug("Sidebar panel removal failed during refresh", exc_info=True)
        data["panel_registered"] = False

    if data.get("panel_registered"):
        data["panel_title"] = title
        return

    # Reading manifest.json touches the filesystem; keep it off the event loop.
    module_url = await hass.async_add_executor_job(_frontend_module_url)
    await async_register_panel(
        hass,
        frontend_url_path="grocery-app",
        webcomponent_name="local-list-assist-panel",
        sidebar_title=title,
        sidebar_icon="mdi:cart-variant",
        module_url=module_url,
        require_admin=False,
        config={"title": title},
    )
    data["panel_registered"] = True
    data["panel_title"] = title


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
    if seconds < 300:
        return "Just now"
    if seconds < 3600:
        minutes = max(5, (seconds // 300) * 5)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def _debug_enabled(hass: HomeAssistant) -> bool:
    entry = hass.data.get(DOMAIN, {}).get("entry")
    return bool(_entry_value(entry, CONF_DEBUG_MODE, False))


def _categories_from_entry(entry: ConfigEntry | None) -> list[str]:
    raw = _entry_value(entry, CONF_CATEGORIES, list(DEFAULT_CATEGORIES))
    return _categories_from_raw(raw)


def _categories_from_raw(raw: Any) -> list[str]:
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

    # Created up front so the (re)load below can serialize against in-flight
    # actions. On a config-entry reload this waits for a running action to
    # finish and persist first, then loads the latest store snapshot instead of
    # clobbering the action's just-committed writes.
    action_lock = data.setdefault("_action_lock", asyncio.Lock())
    store = GroceryLearningStore(hass)
    async with action_lock:
        try:
            terms = await store.load(list(DEFAULT_CATEGORIES))
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("Failed loading grocery terms storage, using defaults: %s", err)
            terms = LearnedTerms.empty(list(DEFAULT_CATEGORIES))
        try:
            item_meta = await store.load_item_meta()
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("Failed loading grocery item metadata, using empty map: %s", err)
            item_meta = {}
        try:
            multilist = await store.load_multilist(list(DEFAULT_CATEGORIES))
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("Failed loading grocery multilist storage, using defaults: %s", err)
            multilist = {
                "active_list_id": "default",
                "lists": {
                    "default": {
                        "name": "Grocery List",
                        "categories": list(DEFAULT_CATEGORIES) + ["other"],
                        "items": [],
                    }
                },
            }
        try:
            activity = await store.load_activity()
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("Failed loading grocery activity storage, using empty list: %s", err)
            activity = []

        data["store"] = store
        data["terms"] = terms
        data["item_meta"] = item_meta
        data["multilist"] = multilist
        data["activity"] = activity
        data.setdefault("pending_duplicate", {})
        data.setdefault("pending_review", {})
        data["categories"] = list(DEFAULT_CATEGORIES)
        data.setdefault("dashboard_revision", 0)

    def _mark_changed_list(list_id: str) -> None:
        # Record which list an action changed so the live-update push can be
        # scoped: panels viewing a different list can skip the reload. Two
        # different lists in one action, or an unmarked action, broadcast to
        # every panel ("*"), which is always safe.
        normalized = _normalize_list_id(str(list_id)) if list_id else ""
        target = normalized or "*"
        data = hass.data[DOMAIN]
        current = data.get("_change_list_id")
        if current is None:
            data["_change_list_id"] = target
        elif current != target:
            data["_change_list_id"] = "*"

    def _publish_dashboard_revision(changed_list_id: str = "*") -> None:
        revision = int(hass.data[DOMAIN].get("dashboard_revision", 0) or 0)
        # Legacy live-update channel: a state entity the panel diffs. Kept as a
        # fallback for panels whose WebSocket subscription isn't active.
        hass.states.async_set(
            LIVE_REVISION_ENTITY_ID,
            str(revision),
            {
                "friendly_name": "Local List Assist Live Revision",
                "revision": revision,
                "updated_at": dt_util.utcnow().isoformat(),
            },
        )
        # Primary live-update channel: push the new revision to subscribed panels.
        _notify_update_listeners(revision, changed_list_id)

    def _notify_update_listeners(revision: int, changed_list_id: str = "*") -> None:
        listeners = hass.data[DOMAIN].get("update_listeners")
        if not listeners:
            return
        for forward in list(listeners):
            try:
                forward(revision, changed_list_id)
            except Exception:  # pragma: no cover - defensive; never let one panel break others
                _LOGGER.debug("Live update push to a panel failed", exc_info=True)

    async def _flush_save() -> None:
        await store.save(
            hass.data[DOMAIN]["terms"],
            hass.data[DOMAIN].get("item_meta", {}),
            hass.data[DOMAIN].get("multilist"),
            hass.data[DOMAIN].get("activity", []),
        )
        hass.data[DOMAIN]["dashboard_revision"] = int(hass.data[DOMAIN].get("dashboard_revision", 0) or 0) + 1
        changed = hass.data[DOMAIN].get("_change_list_id") or "*"
        hass.data[DOMAIN]["_change_list_id"] = None
        _publish_dashboard_revision(changed)

    async def _save() -> None:
        # Inside a locked action, coalesce every persist into a single store
        # write + revision bump flushed when the action finishes. One user
        # action often touches the model, item metadata and the activity feed;
        # without coalescing each fires a live-revision change and forces other
        # devices to reload the dashboard several times for one logical change.
        if _IN_LOCKED_ACTION.get():
            hass.data[DOMAIN]["_save_dirty"] = True
            return
        await _flush_save()

    async def _run_locked(func):
        """Serialize state-mutating work and coalesce its saves.

        A single asyncio.Lock guarantees only one action mutates the shared
        in-memory model at a time (closing the read-modify-write races between
        devices). The _IN_LOCKED_ACTION context var is copied into child tasks
        that Home Assistant spawns for nested service calls, so an action that
        dispatches one of our own services re-enters without deadlocking.

        Invariant this relies on: any call from inside a locked action into one
        of our own wrapped services must be awaited (blocking=True) so the
        current context — and thus _IN_LOCKED_ACTION — propagates into the
        handler. A fire-and-forget self dispatch would run with the var False
        and block on the already-held lock. All current self dispatches are
        blocking.
        """
        if _IN_LOCKED_ACTION.get():
            return await func()
        async with hass.data[DOMAIN]["_action_lock"]:
            token = _IN_LOCKED_ACTION.set(True)
            hass.data[DOMAIN]["_save_dirty"] = False
            hass.data[DOMAIN]["_change_list_id"] = None
            try:
                return await func()
            finally:
                _IN_LOCKED_ACTION.reset(token)
                if hass.data[DOMAIN].get("_save_dirty"):
                    hass.data[DOMAIN]["_save_dirty"] = False
                    await _flush_save()

    _publish_dashboard_revision()

    async def _record_activity(title: str, detail: str, list_name: str = "", source: str = "") -> None:
        activity = hass.data[DOMAIN].setdefault("activity", [])
        if not isinstance(activity, list):
            activity = []
            hass.data[DOMAIN]["activity"] = activity
        activity.insert(
            0,
            {
                "timestamp": dt_util.utcnow().isoformat(),
                "title": title.strip(),
                "detail": detail.strip(),
                "list_name": list_name.strip(),
                "source": source.strip(),
            },
        )
        del activity[MAX_ACTIVITY_ITEMS:]
        if _debug_enabled(hass):
            _LOGGER.info("Local List Assist activity: %s | %s | %s | %s", title, detail, list_name, source)
        await _save()

    def _activity_payload() -> list[dict[str, str]]:
        activity = hass.data[DOMAIN].get("activity", [])
        if not isinstance(activity, list):
            return []
        out: list[dict[str, str]] = []
        for entry in activity[:10]:
            if not isinstance(entry, dict):
                continue
            out.append(
                {
                    "title": str(entry.get("title", "")).strip(),
                    "detail": str(entry.get("detail", "")).strip(),
                    "list_name": str(entry.get("list_name", "")).strip(),
                    "source": _friendly_source(str(entry.get("source", "")).strip() or "unknown"),
                    "when": _relative_time(str(entry.get("timestamp", "")).strip()),
                }
            )
        return out

    def _archived_list_catalog() -> list[dict[str, Any]]:
        _ensure_multilist_model()
        archived_lists = hass.data[DOMAIN]["multilist"].get("archived_lists", {})
        catalog: list[dict[str, Any]] = []
        for list_id, list_obj in archived_lists.items():
            if not isinstance(list_obj, dict):
                continue
            name = str(list_obj.get("name", list_id.title())).strip() or list_id.title()
            catalog.append(
                {
                    "id": str(list_id),
                    "name": name,
                    "color": str(list_obj.get("color", _default_list_color(str(list_id)))).strip() or _default_list_color(str(list_id)),
                }
            )
        catalog.sort(key=lambda entry: entry["name"].lower())
        return catalog

    def _normalize_list_order(model: dict[str, Any]) -> list[str]:
        lists = model.get("lists", {})
        raw_order = model.get("list_order", [])
        ordered: list[str] = []
        if isinstance(raw_order, list):
            for candidate in raw_order:
                if isinstance(candidate, str):
                    normalized = candidate.strip()
                    if normalized and normalized in lists and normalized not in ordered:
                        ordered.append(normalized)
        for list_id in lists:
            if list_id not in ordered:
                ordered.append(list_id)
        if "default" in ordered:
            ordered.remove("default")
        ordered.insert(0, "default")
        model["list_order"] = ordered
        return ordered

    def _ordered_list_ids() -> list[str]:
        model = hass.data[DOMAIN].get("multilist", {})
        if not isinstance(model, dict):
            model = {}
            hass.data[DOMAIN]["multilist"] = model
        return _normalize_list_order(model)

    def _active_categories() -> list[str]:
        return list(hass.data[DOMAIN].get("categories", list(DEFAULT_CATEGORIES)))

    def _multilist_enabled() -> bool:
        return True

    def _ensure_multilist_model() -> None:
        model = hass.data[DOMAIN].setdefault("multilist", {})
        if not isinstance(model, dict):
            model = {}
            hass.data[DOMAIN]["multilist"] = model
        active_list_id = str(model.get("active_list_id", "default")).strip() or "default"
        lists = model.get("lists")
        if not isinstance(lists, dict):
            lists = {}
            model["lists"] = lists
        archived_lists = model.get("archived_lists")
        if not isinstance(archived_lists, dict):
            archived_lists = {}
            model["archived_lists"] = archived_lists
        list_order = model.get("list_order")
        if not isinstance(list_order, list):
            list_order = []
            model["list_order"] = list_order
        if "default" not in lists or not isinstance(lists.get("default"), dict):
            lists["default"] = {
                "name": "Grocery List",
                "voice_entity": "todo.lla_default",
                "categories": _active_categories() + ["other"],
                "items": [],
            }
        default_list = lists["default"]
        default_voice_entity = str(default_list.get("voice_entity", "todo.lla_default")).strip() or "todo.lla_default"
        default_list["voice_entity"] = default_voice_entity
        categories = default_list.get("categories")
        if not isinstance(categories, list):
            categories = _active_categories() + ["other"]
        cleaned_categories = [str(c).strip().lower() for c in categories if str(c).strip()]
        if not cleaned_categories:
            cleaned_categories = _active_categories()
        if "other" not in cleaned_categories:
            cleaned_categories.append("other")
        default_list["categories"] = cleaned_categories
        items = default_list.get("items")
        if not isinstance(items, list):
            default_list["items"] = []
        for list_id, list_obj in lists.items():
            if not isinstance(list_obj, dict):
                continue
            voice_entity = str(list_obj.get("voice_entity", _internal_voice_bridge_entity(str(list_id)))).strip()
            list_obj["voice_entity"] = voice_entity or _internal_voice_bridge_entity(str(list_id))
            alias_entities = [
                str(candidate).strip()
                for candidate in list_obj.get("voice_alias_entities", [])
                if isinstance(candidate, str) and str(candidate).strip()
            ]
            list_obj["voice_alias_entities"] = alias_entities
            list_obj["voice_aliases"] = _voice_aliases_from_input(list_obj.get("voice_aliases", []))
        for list_id, list_obj in archived_lists.items():
            if not isinstance(list_obj, dict):
                continue
            list_obj["voice_aliases"] = _voice_aliases_from_input(list_obj.get("voice_aliases", []))
        model["active_list_id"] = active_list_id if active_list_id in lists else "default"
        _normalize_list_order(model)

    def _active_internal_list() -> tuple[str, dict[str, Any]]:
        _ensure_multilist_model()
        model = hass.data[DOMAIN]["multilist"]
        active_list_id = str(model.get("active_list_id", "default")).strip() or "default"
        lists = model.get("lists", {})
        list_obj = lists.get(active_list_id)
        if not isinstance(list_obj, dict):
            active_list_id = "default"
            list_obj = lists.get("default", {})
        return active_list_id, list_obj

    def _internal_list_entity(category: str) -> str:
        return f"internal:{_normalize_category(category)}"

    def _internal_voice_bridge_entity(list_id: str) -> str:
        return f"todo.lla_{_normalize_list_id(list_id)}"

    def _internal_voice_alias_entity(list_id: str) -> str:
        return f"todo.lla_alias_{_normalize_list_id(list_id)}"

    def _voice_bridge_title(name: str) -> str:
        clean = str(name).strip() or "List"
        normalized = _normalize_term(clean)
        if normalized.endswith(" list"):
            return clean
        return f"{clean} list"

    def _internal_list_by_id(list_id: str) -> tuple[str, dict[str, Any]]:
        _ensure_multilist_model()
        model = hass.data[DOMAIN]["multilist"]
        lists = model.get("lists", {})
        normalized = _normalize_list_id(list_id)
        list_obj = lists.get(normalized)
        if isinstance(list_obj, dict):
            return normalized, list_obj
        return _active_internal_list()

    def _internal_list_id_from_voice_entity(entity_id: str) -> str:
        if not entity_id:
            return ""
        _ensure_multilist_model()
        model = hass.data[DOMAIN]["multilist"]
        lists = model.get("lists", {})
        for list_id, list_obj in lists.items():
            if not isinstance(list_obj, dict):
                continue
            voice_entity = str(list_obj.get("voice_entity", _internal_voice_bridge_entity(str(list_id)))).strip()
            alias_entity = _internal_voice_alias_entity(str(list_id))
            alias_entities = [
                str(candidate).strip()
                for candidate in list_obj.get("voice_alias_entities", [])
                if isinstance(candidate, str) and str(candidate).strip()
            ]
            if entity_id == voice_entity or entity_id == alias_entity or entity_id in alias_entities:
                return str(list_id)
        return ""

    def _internal_list_id_from_voice_name(list_name: str) -> str:
        if not list_name:
            return ""
        if "." in list_name:
            by_entity = _internal_list_id_from_voice_entity(str(list_name).strip())
            if by_entity:
                return by_entity
        _ensure_multilist_model()
        model = hass.data[DOMAIN]["multilist"]
        lists = model.get("lists", {})
        return resolve_list_id_from_voice_name(list_name, lists)

    def _categories_from_list_input(raw: Any) -> list[str]:
        if isinstance(raw, str):
            values = [_normalize_category(v) for v in raw.replace("\n", ",").split(",")]
        elif isinstance(raw, list):
            values = [_normalize_category(str(v)) for v in raw]
        else:
            values = []
        out: list[str] = []
        for value in values:
            if not value or value == "other":
                continue
            if value not in out:
                out.append(value)
        return out

    def _voice_aliases_from_input(raw: Any) -> list[str]:
        if isinstance(raw, str):
            values = [str(v).strip() for v in raw.replace("\n", ",").split(",")]
        elif isinstance(raw, list):
            values = [str(v).strip() for v in raw]
        else:
            values = []
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value:
                continue
            normalized = normalize_voice_list_name(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            out.append(value)
        return out

    def _looks_like_grocery_list(name: str) -> bool:
        normalized = _normalize_term(name)
        return "grocery" in normalized or "shopping" in normalized

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

    def _internal_list_catalog(selected_list_id: str | None = None) -> list[dict[str, Any]]:
        _ensure_multilist_model()
        model = hass.data[DOMAIN]["multilist"]
        active_id = _normalize_list_id(selected_list_id or str(model.get("active_list_id", "default")).strip()) or "default"
        lists = model.get("lists", {})
        catalog: list[dict[str, Any]] = []
        for position, list_id in enumerate(_ordered_list_ids()):
            list_obj = lists.get(list_id)
            if not isinstance(list_obj, dict):
                continue
            name = str(list_obj.get("name", list_id.title())).strip() or list_id.title()
            catalog.append(
                {
                    "id": str(list_id),
                    "name": name,
                    "color": str(list_obj.get("color", _default_list_color(str(list_id)))).strip() or _default_list_color(str(list_id)),
                    "voice_aliases": [
                        str(alias).strip()
                        for alias in list_obj.get("voice_aliases", [])
                        if isinstance(alias, str) and str(alias).strip()
                    ],
                    "active": str(list_id) == active_id,
                    "position": position,
                }
            )
        return catalog

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
                # input_text state is capped at 255 chars, so the legacy YAML
                # mirror can only hold a subset. Keep the most recent whole
                # terms and note the drop instead of clipping silently.
                clipped = merged[-255:]
                if "|" in clipped:
                    clipped = clipped.split("|", 1)[1]
                _LOGGER.debug(
                    "Learned-term helper %s truncated to fit 255 chars; the internal store keeps the full set",
                    helper,
                )
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

    def _set_status_entity(entity_id: str, state: str, *, icon: str, friendly_name: str) -> None:
        hass.states.async_set(
            entity_id,
            state,
            {"icon": icon, "friendly_name": friendly_name},
        )

    def _update_review_status_entities(*, pending: bool, item: str = "", source_list: str = "") -> None:
        _set_status_entity(
            REVIEW_STATUS_PENDING_ENTITY,
            "on" if pending else "off",
            icon="mdi:clipboard-text-clock-outline",
            friendly_name="Local List Review Pending",
        )
        _set_status_entity(
            REVIEW_STATUS_ITEM_ENTITY,
            item or "none",
            icon="mdi:cart-outline",
            friendly_name="Local List Review Item",
        )
        _set_status_entity(
            REVIEW_STATUS_SOURCE_ENTITY,
            source_list or "none",
            icon="mdi:playlist-check",
            friendly_name="Local List Review Source List",
        )

    def _update_duplicate_status_entities(
        *,
        pending: bool,
        item: str = "",
        target: str = "",
        added_by: str = "",
        added_when: str = "",
        source: str = "",
    ) -> None:
        _set_status_entity(
            DUPLICATE_STATUS_PENDING_ENTITY,
            "on" if pending else "off",
            icon="mdi:content-duplicate",
            friendly_name="Duplicate Pending",
        )
        _set_status_entity(
            DUPLICATE_STATUS_ITEM_ENTITY,
            item or "none",
            icon="mdi:cart-outline",
            friendly_name="Duplicate Item",
        )
        _set_status_entity(
            DUPLICATE_STATUS_TARGET_ENTITY,
            target or "none",
            icon="mdi:format-list-bulleted",
            friendly_name="Duplicate Target List",
        )
        _set_status_entity(
            DUPLICATE_STATUS_BY_ENTITY,
            added_by or "unknown",
            icon="mdi:account",
            friendly_name="Local List Duplicate Added By",
        )
        _set_status_entity(
            DUPLICATE_STATUS_WHEN_ENTITY,
            added_when or "unknown",
            icon="mdi:clock-outline",
            friendly_name="Local List Duplicate Added When",
        )
        _set_status_entity(
            DUPLICATE_STATUS_SOURCE_ENTITY,
            source or "unknown",
            icon="mdi:source-branch",
            friendly_name="Local List Duplicate Source",
        )

    async def _remove_from_list(list_entity: str, item_summary: str) -> None:
        if not list_entity or hass.states.get(list_entity) is None:
            return
        needle = _normalize_term(item_summary)
        try:
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
        except Exception as err:  # pragma: no cover
            _LOGGER.debug("Ignoring bridge source removal failure for %s: %s", list_entity, err)

    def _display_name_from_user(user: Any) -> str:
        if user is None:
            return ""
        return str(
            getattr(user, "display_name", "")
            or getattr(user, "name", "")
            or getattr(user, "username", "")
            or ""
        ).strip()

    async def _user_name_from_context(call: ServiceCall) -> tuple[str, str]:
        user_id = call.context.user_id or ""
        if not user_id:
            actor_id = str(call.data.get("actor_user_id", "")).strip()
            actor_name = str(call.data.get("actor_name", "")).strip()
            if actor_id:
                actor_user = await hass.auth.async_get_user(actor_id)
                display_name = _display_name_from_user(actor_user)
                if display_name:
                    return actor_id, display_name
                if actor_name:
                    return actor_id, actor_name
            if actor_name:
                return "", actor_name
            return "", ""
        user = await hass.auth.async_get_user(user_id)
        display_name = _display_name_from_user(user)
        if display_name:
            return user_id, display_name
        actor_name = str(call.data.get("actor_name", "")).strip()
        if actor_name:
            return user_id, actor_name
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

    def _quantity_for_item(item: Mapping[str, Any]) -> int:
        return _coerce_quantity(item.get("quantity", 1))

    def _build_description_from_meta(meta: Mapping[str, str], fallback: str) -> str:
        if not meta:
            return fallback
        contributors = _format_contributors(_decode_contributors(meta))
        source = _friendly_source(str(meta.get("last_source", "")).strip() or "unknown")
        when = _relative_time(str(meta.get("last_added_at", "")).strip())
        return f"Added by {contributors} · {when} · {source}"
    def _display_description(list_entity: str, summary: str, fallback: str) -> str:
        normalized_item = _normalize_term(summary)
        if normalized_item:
            meta = _meta_for_item(list_entity, normalized_item)
            if meta:
                return _build_description_from_meta(meta, fallback)
        marker = "GLMETA|"
        if marker in fallback:
            match = re.search(r"GLMETA\|([^|]+)\|([^|]*)\|([^\r\n|]+)", fallback)
            if match:
                added_at, added_by, source_key = match.groups()
                added_by = added_by.strip() or "Unknown"
                source = _friendly_source(source_key.strip() or "unknown")
                when = _relative_time(added_at.strip())
                return f"Added by {added_by} · {when} · {source}"
        return fallback

    def _description_with_existing_meta(list_entity: str, summary: str, fallback: str) -> str:
        normalized_item = _normalize_term(summary)
        if not normalized_item:
            return fallback
        meta = _meta_for_item(list_entity, normalized_item)
        if not meta:
            return fallback
        added_at = str(meta.get("last_added_at", "")).strip()
        added_by = _format_contributors(_decode_contributors(meta))
        source_key = str(meta.get("last_source", "")).strip() or "unknown"
        source = _friendly_source(source_key)
        when = _relative_time(added_at)
        safe_name = added_by.replace("|", "/")
        safe_source = source_key.replace("|", "_")
        return f"Added by {added_by} · {when} · {source}\nGLMETA|{added_at}|{safe_name}|{safe_source}"
    def _clean_helper_state_value(value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() in {"", "unknown", "unavailable", "none", "null"}:
            return ""
        return cleaned

    async def _build_item_description(
        call: ServiceCall,
        source_override: str | None = None,
    ) -> str:
        resolved_source = source_override or _source_from_call(call)
        _, user_name = await _user_name_from_context(call)
        if not user_name:
            if resolved_source == "typed":
                user_name = "User"
            elif resolved_source == "voice_assistant":
                user_name = "Voice Assistant"
            elif resolved_source == "automation":
                user_name = "Automation"
            else:
                user_name = "Unknown"
        source = _friendly_source(resolved_source)
        now_iso = dt_util.utcnow().isoformat()
        safe_name = user_name.replace("|", "/")
        safe_source = resolved_source.replace("|", "_")
        return f"Added by {user_name} · just now · {source}\nGLMETA|{now_iso}|{safe_name}|{safe_source}"

    async def _record_item_meta(
        list_entity: str,
        item_summary: str,
        call: ServiceCall,
        source_override: str | None = None,
        quantity: int = 1,
    ) -> None:
        normalized_item = _normalize_term(item_summary)
        if not normalized_item:
            return

        user_id, user_name = await _user_name_from_context(call)
        source = source_override or _source_from_call(call)
        if not user_id:
            user_id = str(call.data.get("actor_user_id", "")).strip()
        if not user_name:
            if source == "typed":
                user_name = str(call.data.get("actor_name", "")).strip() or "User"
            elif source == "voice_assistant":
                user_name = "Voice Assistant"
            elif source == "automation":
                user_name = "Automation"
            else:
                user_name = "Unknown"
        meta_map: dict[str, dict[str, str]] = hass.data[DOMAIN].setdefault("item_meta", {})
        key = _item_meta_key(list_entity, normalized_item)
        now_iso = dt_util.utcnow().isoformat()
        previous = meta_map.get(key, {})
        count = int(previous.get("add_count", "0") or "0") + 1
        current_quantity = _meta_quantity(previous) + _coerce_quantity(quantity)
        contributors = _decode_contributors(previous)
        if user_name and user_name.lower() not in {name.lower() for name in contributors}:
            contributors.append(user_name)
        meta_map[key] = {
            "last_added_at": now_iso,
            "last_added_by_user_id": user_id,
            "last_added_by_name": user_name,
            "last_source": source,
            "last_item_text": item_summary.strip(),
            "add_count": str(count),
            "current_quantity": str(current_quantity),
            "contributors_json": json.dumps(contributors),
        }
        await _save()

    async def _set_item_meta_quantity(list_entity: str, item_summary: str, quantity: int) -> None:
        normalized_item = _normalize_term(item_summary)
        if not normalized_item:
            return
        meta_map: dict[str, dict[str, str]] = hass.data[DOMAIN].setdefault("item_meta", {})
        key = _item_meta_key(list_entity, normalized_item)
        existing = dict(meta_map.get(key, {}))
        if not existing:
            return
        existing["current_quantity"] = str(_coerce_quantity(quantity))
        meta_map[key] = existing
        await _save()

    async def _remove_item_meta_entry(list_entity: str, item_summary: str) -> None:
        normalized_item = _normalize_term(item_summary)
        if not normalized_item:
            return
        meta_map: dict[str, dict[str, str]] = hass.data[DOMAIN].setdefault("item_meta", {})
        key = _item_meta_key(list_entity, normalized_item)
        if key in meta_map:
            meta_map.pop(key, None)
            await _save()

    def _move_item_meta_entry(
        old_list_entity: str,
        old_summary: str,
        new_list_entity: str,
        new_summary: str,
    ) -> None:
        old_normalized = _normalize_term(old_summary)
        new_normalized = _normalize_term(new_summary)
        if not old_normalized or not new_normalized:
            return
        old_key = _item_meta_key(old_list_entity, old_normalized)
        new_key = _item_meta_key(new_list_entity, new_normalized)
        if old_key == new_key:
            return
        meta_map: dict[str, dict[str, str]] = hass.data[DOMAIN].setdefault("item_meta", {})
        existing = meta_map.pop(old_key, None)
        if existing:
            target_existing = meta_map.get(new_key, {})
            meta_map[new_key] = _merge_meta_records(target_existing, existing)


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

    async def _first_open_item(list_entity: str) -> dict[str, Any] | None:
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
        if not isinstance(items, list) or not items:
            return None
        return items[0] if isinstance(items[0], dict) else None

    async def _find_open_item(list_entity: str, item_summary: str) -> dict[str, Any] | None:
        normalized = _normalize_term(item_summary)
        if not normalized:
            return None
        for item in await _list_items(list_entity, "needs_action"):
            existing = _normalize_term(str(item.get("summary", "")).strip())
            if existing == normalized:
                return item
        return None

    async def _list_items(list_entity: str, status: str) -> list[dict[str, Any]]:
        if not list_entity or hass.states.get(list_entity) is None:
            return []
        try:
            response = await hass.services.async_call(
                "todo",
                "get_items",
                {"status": status},
                target={"entity_id": list_entity},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # pragma: no cover
            _LOGGER.warning("Failed to fetch todo items for %s (%s): %s", list_entity, status, err)
            return []

        resp = response.get(list_entity, response) if isinstance(response, dict) else {}
        items = resp.get("items", []) if isinstance(resp, dict) else []
        return [item for item in items if isinstance(item, dict)]

    async def _resolve_item_ref(list_entity: str, item_ref: str) -> dict[str, Any] | None:
        statuses = ["needs_action", "completed"]
        normalized_ref = _normalize_term(item_ref)
        for status in statuses:
            items = await _list_items(list_entity, status)
            for item in items:
                uid = str(item.get("uid", "")).strip()
                summary = str(item.get("summary", "")).strip()
                if uid and uid == item_ref:
                    return item
                if summary and (summary == item_ref or _normalize_term(summary) == normalized_ref):
                    return item
        return None

    def _internal_find_item(items: list[dict[str, Any]], item_ref: str) -> dict[str, Any] | None:
        normalized_ref = _normalize_term(item_ref)
        for item in items:
            item_id = str(item.get("id", "")).strip()
            summary = str(item.get("summary", "")).strip()
            if item_id and item_ref == item_id:
                return item
            if summary and (item_ref == summary or _normalize_term(summary) == normalized_ref):
                return item
        return None

    async def _build_dashboard_payload_internal(selected_list_id: str | None = None) -> dict[str, Any]:
        active_entry = hass.data.get(DOMAIN, {}).get("entry")
        list_id, list_obj = _internal_list_by_id(selected_list_id) if selected_list_id else _active_internal_list()
        categories = [c for c in list_obj.get("categories", []) if c != "other"]
        has_custom_categories = len(categories) > 0
        default_list = hass.data[DOMAIN].get("multilist", {}).get("lists", {}).get("default", {})
        default_categories = [c for c in default_list.get("categories", []) if c != "other"] if isinstance(default_list, dict) else _active_categories()
        items = list_obj.get("items", [])
        grouped: list[dict[str, Any]] = []
        for category in categories + ["other"]:
            grouped_items = []
            for item in items:
                if str(item.get("status", "")).strip() != "needs_action":
                    continue
                if str(item.get("category", "other")).strip() != category:
                    continue
                summary = str(item.get("summary", "")).strip()
                description = str(item.get("description", "")).strip()
                grouped_items.append(
                    {
                        "item_ref": str(item.get("id", "")).strip() or summary,
                        "summary": summary,
                        "quantity": _quantity_for_item(item),
                        "description": _display_description(_internal_list_entity(category), summary, description),
                        "list_entity": _internal_list_entity(category),
                        "category": category,
                        "category_display": _display_name_for_category(category),
                    }
                )
            grouped.append(
                {
                    "category": category,
                    "title": _display_name_for_category(category) if (category != "other" or has_custom_categories) else "Items",
                    "items": grouped_items,
                }
            )

        completed = []
        for item in items:
            if str(item.get("status", "")).strip() != "completed":
                continue
            category = str(item.get("category", "other")).strip() or "other"
            summary = str(item.get("summary", "")).strip()
            description = str(item.get("description", "")).strip()
            completed.append(
                {
                    "item_ref": str(item.get("id", "")).strip() or summary,
                    "summary": summary,
                    "quantity": _quantity_for_item(item),
                    "description": _display_description(_internal_list_entity(category), summary, description),
                    "list_entity": "internal:completed",
                }
            )

        pending_review = dict(hass.data[DOMAIN].get("pending_review", {}))
        pending_duplicate = dict(hass.data[DOMAIN].get("pending_duplicate", {}))
        if pending_duplicate and not bool(pending_duplicate.get("interactive", False)):
            await _clear_pending_duplicate()
            pending_duplicate = {}

        return {
            "categories": categories + ["other"],
            "groups": grouped,
            "completed": completed,
            "lists": _internal_list_catalog(list_id),
            "pending_review": {
                "pending": bool(pending_review.get("item")),
                "item": str(pending_review.get("item", "")),
                "source_list": str(pending_review.get("source_list", "")),
            },
            "pending_duplicate": {
                "pending": bool(pending_duplicate.get("item")),
                "item": str(pending_duplicate.get("item", "")),
                "target": str(pending_duplicate.get("target_list", "")),
            },
            "archived_lists": _archived_list_catalog(),
            "settings": {
                "categories": default_categories,
                "experimental_multilist": True,
                "default_grocery_categories": bool(_entry_value(active_entry, CONF_DEFAULT_GROCERY_CATEGORIES, True)),
                "debug_mode": bool(_entry_value(active_entry, CONF_DEBUG_MODE, False)),
                "dashboard_name": _dashboard_name(active_entry),
            },
            "system": {
                "missing_lists": [],
                "runtime_ready": bool(hass.data.get(DOMAIN, {}).get("runtime_ready")),
                "active_list_id": list_id,
                "active_list_name": str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
                "active_list_color": str(list_obj.get("color", _default_list_color(list_id))).strip() or _default_list_color(list_id),
                "active_list_categories": categories,
                "active_list_voice_aliases": [
                    str(alias).strip()
                    for alias in list_obj.get("voice_aliases", [])
                    if isinstance(alias, str) and str(alias).strip()
                ],
                "template_presets": template_presets(default_categories),
            },
            "activity": _activity_payload(),
            "setup": {
                "completed": bool(_entry_value(active_entry, CONF_WIZARD_COMPLETED, False)),
            },
            # Lets a panel recognize live-update pushes triggered by its own
            # action and skip the redundant self-reload.
            "revision": int(hass.data.get(DOMAIN, {}).get("dashboard_revision", 0) or 0),
        }

    async def _build_dashboard_payload(selected_list_id: str | None = None) -> dict[str, Any]:
        return await _build_dashboard_payload_internal(selected_list_id)

    async def _route_item_internal(call: ServiceCall) -> None:
        raw_item = str(call.data.get("item", "")).strip()
        if not raw_item:
            return
        display_item = _display_item_summary(raw_item) or raw_item
        source_list = str(call.data.get("source_list", "")).strip()
        source_list_name = str(call.data.get("source_list_name", "")).strip()
        remove_from_source = bool(call.data.get("remove_from_source", False))
        review_on_other = bool(call.data.get("review_on_other", True))
        allow_duplicate = bool(call.data.get("allow_duplicate", False))
        interactive_duplicate = bool(call.data.get("interactive_duplicate", False))
        source = _source_from_call(call)
        should_prompt_duplicate = interactive_duplicate and source == "typed" and not source_list and not remove_from_source
        if not should_prompt_duplicate:
            await _clear_pending_duplicate()

        normalized = _normalize_term(display_item)
        if not normalized:
            return
        quantity = _coerce_quantity(call.data.get("quantity", 1))

        source_target_list_id = _normalize_list_id(str(call.data.get("list_id", "")).strip())
        intake_like_source = source in {"voice_assistant", "automation"}
        if not source_target_list_id and intake_like_source:
            # Prefer explicit spoken/list-name context over raw entity targets.
            if source_list_name:
                source_target_list_id = _internal_list_id_from_voice_name(source_list_name)
                if not source_target_list_id:
                    normalized_list_name = _normalize_term(source_list_name)
                    if "grocery" in normalized_list_name or "shopping" in normalized_list_name:
                        source_target_list_id = "default"
            if not source_target_list_id and source_list:
                source_target_list_id = _internal_list_id_from_voice_entity(source_list)
            # Do not trust source_list alone for voice; when name is unavailable, route to default.
        elif not source_target_list_id:
            source_target_list_id = _internal_list_id_from_voice_entity(source_list) if source_list else ""
            if not source_target_list_id and source_list_name:
                source_target_list_id = _internal_list_id_from_voice_name(source_list_name)
        if source_target_list_id:
            active_list_id, list_obj = _internal_list_by_id(source_target_list_id)
        elif intake_like_source or source_list:
            active_list_id, list_obj = _internal_list_by_id("default")
        else:
            active_list_id, list_obj = _active_internal_list()
        items: list[dict[str, Any]] = list_obj.setdefault("items", [])
        categories = [c for c in list_obj.get("categories", []) if c != "other"]
        list_name = str(list_obj.get("name", "")).strip()
        smart_grocery_mode = active_list_id == "default" or _looks_like_grocery_list(list_name)

        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
        category = _get_category_for_term(terms_obj, normalized) if (categories and smart_grocery_mode) else "other"
        if categories and category not in categories:
            category = "other"

        duplicate_item = next(
            (
                item
                for item in items
                if str(item.get("status", "")).strip() == "needs_action"
                and str(item.get("category", "")).strip() == category
                and _normalize_term(str(item.get("summary", "")).strip()) == normalized
            ),
            None,
        )
        target_entity = _internal_list_entity(category)
        if duplicate_item and not allow_duplicate:
            duplicate_item["quantity"] = _quantity_for_item(duplicate_item) + quantity
            await _record_item_meta(target_entity, display_item, call, quantity=quantity)
            duplicate_item["description"] = _description_with_existing_meta(
                target_entity,
                str(duplicate_item.get("summary", "")).strip(),
                str(duplicate_item.get("description", "")).strip(),
            )
            await _save()
            await _record_activity(
                "Updated quantity",
                f"{str(duplicate_item.get('summary', '')).strip() or display_item} x{duplicate_item['quantity']}",
                str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
                source,
            )
            if remove_from_source:
                await _remove_from_list(source_list, raw_item)
            return

        description = await _build_item_description(call)
        items.append(
            {
                "id": uuid4().hex,
                "summary": display_item,
                "category": category,
                "status": "needs_action",
                "description": description,
                "quantity": quantity,
            }
        )
        await _record_item_meta(target_entity, display_item, call, quantity=quantity)
        await _save()
        await _record_activity(
            "Item added",
            f"{display_item} x{quantity}" if quantity > 1 else display_item,
            str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
            source,
        )

        if remove_from_source:
            await _remove_from_list(source_list, raw_item)

        if category == "other" and review_on_other and smart_grocery_mode and categories:
            await _set_pending_review(raw_item, target_entity)

    async def _apply_review_internal(call: ServiceCall) -> None:
        category_in = str(call.data.get("category", "")).strip().lower()
        learn = bool(call.data.get("learn", True))
        _, list_obj = _active_internal_list()
        categories = [c for c in list_obj.get("categories", []) if c != "other"]
        normalized_category = _normalize_category(category_in)
        if category_in == "keep other":
            target_category = "other"
        elif normalized_category in categories:
            target_category = normalized_category
        else:
            target_category = "other"

        pending_review = dict(hass.data[DOMAIN].get("pending_review", {}))
        review_item = str(pending_review.get("item", "")).strip()
        source_list = str(pending_review.get("source_list", "")).strip() or _internal_list_entity("other")
        if not review_item:
            return

        items: list[dict[str, Any]] = list_obj.setdefault("items", [])
        item = _internal_find_item(items, review_item)
        if item is None:
            await _clear_pending_review()
            return

        summary = str(item.get("summary", "")).strip()
        source_entity = source_list
        target_entity = _internal_list_entity(target_category)
        item["description"] = _description_with_existing_meta(
            source_entity,
            summary,
            str(item.get("description", "")).strip(),
        )
        item["category"] = target_category
        _move_item_meta_entry(source_entity, summary, target_entity, summary)
        if learn and target_category in categories:
            norm = _normalize_term(summary)
            terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
            existing = set(terms_obj.data.get(target_category, []))
            if norm and norm not in existing:
                terms_obj.data.setdefault(target_category, []).append(norm)
        await _clear_pending_review()
        await _save()

    async def _confirm_duplicate_internal(call: ServiceCall) -> None:
        decision = str(call.data.get("decision", "")).strip().lower()
        if decision not in {"add", "skip"}:
            raise vol.Invalid("decision must be 'add' or 'skip'")
        pending = dict(hass.data[DOMAIN].get("pending_duplicate", {}))
        item = str(pending.get("item", "")).strip()
        target_list = str(pending.get("target_list", "")).strip() or _internal_list_entity("other")
        target_category = _normalize_category(target_list.replace("internal:", "")) if target_list.startswith("internal:") else "other"

        if decision == "add" and item:
            _, list_obj = _active_internal_list()
            items: list[dict[str, Any]] = list_obj.setdefault("items", [])
            description = await _build_item_description(call, source_override="duplicate_confirmation")
            items.append(
                {
                    "id": uuid4().hex,
                    "summary": item,
                    "category": target_category if target_category else "other",
                    "status": "needs_action",
                    "description": description,
                }
            )
            await _record_item_meta(_internal_list_entity(target_category or "other"), item, call, source_override="duplicate_confirmation")
            await _save()

        await _clear_pending_duplicate()

    async def _handle_dashboard_action(payload: dict[str, Any]) -> dict[str, Any]:
        # Every dashboard action runs under the shared action lock so concurrent
        # requests from multiple devices/users cannot interleave and lose writes.
        return await _run_locked(lambda: _handle_dashboard_action_impl(payload))

    async def _handle_dashboard_action_impl(payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "")).strip()
        multilist_mode = _multilist_enabled()
        if action == "add_item":
            item = str(payload.get("item", "")).strip()
            if item:
                quantity = _coerce_quantity(payload.get("quantity", 1))
                target_list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
                _mark_changed_list(target_list_id)
                request_user_id = str(payload.get("_request_user_id", "")).strip() or str(payload.get("actor_user_id", "")).strip()
                actor_name = str(payload.get("actor_name", "")).strip()
                if request_user_id and not actor_name:
                    req_user = await hass.auth.async_get_user(request_user_id)
                    actor_name = _display_name_from_user(req_user)
                request_context = Context(user_id=request_user_id) if request_user_id else None
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_ROUTE_ITEM,
                    {
                        "item": item,
                        "review_on_other": True,
                        "source": "typed",
                        "interactive_duplicate": True,
                        "allow_duplicate": False,
                        "quantity": quantity,
                        "list_id": target_list_id,
                        "actor_user_id": request_user_id,
                        "actor_name": actor_name,
                    },
                    blocking=True,
                    context=request_context,
                )
            return {"ok": True}

        if action == "create_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            name = str(payload.get("name", "")).strip()
            if not name:
                return {"ok": False, "error": "missing_name"}
            list_id_raw = str(payload.get("list_id", "")).strip() or name
            list_id = _normalize_list_id(list_id_raw)
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            if list_id in lists:
                return {"ok": False, "error": "list_exists"}
            custom_categories = _categories_from_list_input(payload.get("categories", ""))
            template_id = str(payload.get("template", "")).strip().lower()
            use_default_grocery_categories = bool(
                _entry_value(hass.data.get(DOMAIN, {}).get("entry"), CONF_DEFAULT_GROCERY_CATEGORIES, True)
            )
            if custom_categories:
                base_categories = custom_categories
            elif template_id:
                base_categories = categories_for_template(template_id, _active_categories())
            elif use_default_grocery_categories and _looks_like_grocery_list(name):
                base_categories = _active_categories()
            else:
                base_categories = []
            lists[list_id] = {
                "name": name,
                "voice_entity": _internal_voice_bridge_entity(list_id),
                "voice_alias_entities": [],
                "voice_aliases": _voice_aliases_from_input(payload.get("voice_aliases", "")),
                "color": str(payload.get("color", _default_list_color(list_id))).strip() or _default_list_color(list_id),
                "categories": base_categories + ["other"],
                "items": [],
            }
            resolved_voice = await _ensure_local_todo_list(_internal_voice_bridge_entity(list_id), name)
            if resolved_voice:
                lists[list_id]["voice_entity"] = resolved_voice
            alias_title = _voice_bridge_title(name)
            if alias_title.strip().lower() != name.strip().lower():
                resolved_alias = await _ensure_local_todo_list(_internal_voice_alias_entity(list_id), alias_title)
                if resolved_alias and resolved_alias != lists[list_id]["voice_entity"]:
                    lists[list_id]["voice_alias_entities"] = [resolved_alias]
            list_order = model.setdefault("list_order", [])
            if list_id not in list_order:
                list_order.append(list_id)
            await _save()
            await _record_activity("List created", name, name, "service_call")
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "save_list_categories":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            list_obj = lists.get(list_id)
            if not isinstance(list_obj, dict):
                return {"ok": False, "error": "list_not_found"}
            categories = _categories_from_list_input(payload.get("categories", ""))
            list_obj["categories"] = categories + ["other"]
            items: list[dict[str, Any]] = list_obj.setdefault("items", [])
            allowed_categories = set(categories) | {"other"}
            for item in items:
                if str(item.get("category", "other")).strip() not in allowed_categories:
                    item["category"] = "other"
            await _save()
            return {"ok": True}

        if action == "save_list_voice_aliases":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            list_obj = lists.get(list_id)
            if not isinstance(list_obj, dict):
                return {"ok": False, "error": "list_not_found"}
            aliases = _voice_aliases_from_input(payload.get("voice_aliases", ""))
            list_obj["voice_aliases"] = aliases
            await _save()
            await _record_activity(
                "Updated voice aliases",
                ", ".join(aliases) if aliases else "No aliases",
                str(list_obj.get("name", list_id)).strip() or list_id,
                "typed",
            )
            return {"ok": True}

        if action == "save_active_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            list_obj = lists.get(list_id)
            if not isinstance(list_obj, dict):
                return {"ok": False, "error": "list_not_found"}

            next_name = str(payload.get("name", "")).strip()
            next_categories = _categories_from_list_input(payload.get("categories", ""))
            raw_renamed_categories = payload.get("renamed_categories", {})
            renamed_categories = {
                _normalize_category(str(source).strip()): _normalize_category(str(target).strip())
                for source, target in raw_renamed_categories.items()
                if _normalize_category(str(source).strip()) and _normalize_category(str(target).strip())
            } if isinstance(raw_renamed_categories, dict) else {}
            next_aliases = _voice_aliases_from_input(payload.get("voice_aliases", ""))
            next_color = str(payload.get("color", "")).strip()

            if next_name:
                previous_name = str(list_obj.get("name", list_id)).strip()
                list_obj["name"] = next_name
                if previous_name != next_name:
                    await _record_activity("Renamed list", f"{previous_name} -> {next_name}", next_name, "typed")

            if next_color:
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", next_color):
                    return {"ok": False, "error": "invalid_color"}
                list_obj["color"] = next_color

            list_obj["voice_aliases"] = next_aliases
            list_obj["categories"] = next_categories + ["other"]
            allowed_categories = set(next_categories) | {"other"}
            items: list[dict[str, Any]] = list_obj.setdefault("items", [])
            for item in items:
                current_category = _normalize_category(str(item.get("category", "other")).strip()) or "other"
                if current_category in renamed_categories:
                    item["category"] = renamed_categories[current_category]
                if str(item.get("category", "other")).strip() not in allowed_categories:
                    item["category"] = "other"

            await _save()
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "switch_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            if list_id not in lists:
                return {"ok": False, "error": "list_not_found"}
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "reorder_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            direction = str(payload.get("direction", "")).strip().lower()
            if list_id == "default":
                return {"ok": False, "error": "cannot_move_default"}
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            ordered = _ordered_list_ids()
            if list_id not in ordered:
                return {"ok": False, "error": "list_not_found"}
            index = ordered.index(list_id)
            if direction == "pin":
                ordered.pop(index)
                ordered.insert(1, list_id)
            elif direction == "left" and index > 1:
                ordered[index], ordered[index - 1] = ordered[index - 1], ordered[index]
            elif direction == "right" and index < len(ordered) - 1:
                ordered[index], ordered[index + 1] = ordered[index + 1], ordered[index]
            model["list_order"] = ordered
            await _save()
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "set_list_order":
            requested = payload.get("order", [])
            if not isinstance(requested, list):
                return {"ok": False, "error": "invalid_order"}
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            cleaned: list[str] = []
            for candidate in requested:
                normalized = _normalize_list_id(str(candidate))
                if normalized in lists and normalized not in cleaned:
                    cleaned.append(normalized)
            for existing_id in lists:
                if existing_id not in cleaned:
                    cleaned.append(existing_id)
            model["list_order"] = cleaned
            # Keeps "default" pinned first and drops unknown/duplicate ids.
            _normalize_list_order(model)
            await _save()
            active_id = _active_internal_list()[0]
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(active_id)}

        if action == "set_item_order":
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            category = _normalize_category(str(payload.get("category", "")).strip()) or "other"
            requested = payload.get("order", [])
            if not isinstance(requested, list):
                return {"ok": False, "error": "invalid_order"}
            order_ids = [str(candidate).strip() for candidate in requested if str(candidate).strip()]
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            list_obj = model.get("lists", {}).get(list_id)
            if not isinstance(list_obj, dict):
                return {"ok": False, "error": "list_not_found"}
            items = list_obj.get("items", [])
            if isinstance(items, list):
                list_obj["items"] = _reorder_category_items(items, category, order_ids)
            _mark_changed_list(list_id)
            await _save()
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "rename_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            new_name = str(payload.get("name", "")).strip()
            if not new_name:
                return {"ok": False, "error": "missing_name"}
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            list_obj = lists.get(list_id)
            if not isinstance(list_obj, dict):
                return {"ok": False, "error": "list_not_found"}
            previous_name = str(list_obj.get("name", list_id)).strip()
            list_obj["name"] = new_name
            await _save()
            await _record_activity("Renamed list", f"{previous_name} -> {new_name}", new_name, "typed")
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "set_list_color":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            color = str(payload.get("color", "")).strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                return {"ok": False, "error": "invalid_color"}
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            lists = model.get("lists", {})
            list_obj = lists.get(list_id)
            if not isinstance(list_obj, dict):
                return {"ok": False, "error": "list_not_found"}
            list_obj["color"] = color
            await _save()
            await _record_activity(
                "Updated list color",
                color,
                str(list_obj.get("name", list_id)).strip() or list_id,
                "typed",
            )
            return {"ok": True}

        if action == "archive_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            result = apply_archive_list(model, list_id)
            if not result.get("ok"):
                return result
            model["list_order"] = [candidate for candidate in _ordered_list_ids() if candidate != list_id]
            await _save()
            archived_name = str(result.get("list_name", list_id)).strip() or list_id
            await _record_activity("Archived list", archived_name, archived_name, "typed")
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal("default")}

        if action == "restore_archived_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            model = hass.data[DOMAIN]["multilist"]
            result = apply_restore_archived_list(model, list_id)
            if not result.get("ok"):
                return result
            ordered = _ordered_list_ids()
            if list_id not in ordered:
                ordered.append(list_id)
            model["list_order"] = ordered
            await _save()
            restored_name = str(result.get("list_name", list_id)).strip() or list_id
            await _record_activity("Restored archived list", restored_name, restored_name, "typed")
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal(list_id)}

        if action == "delete_archived_list":
            if not multilist_mode:
                return {"ok": False, "error": "multilist_disabled"}
            list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _ensure_multilist_model()
            result = apply_delete_archived_list(hass.data[DOMAIN]["multilist"], list_id)
            if not result.get("ok"):
                return result
            await _save()
            archived_name = str(result.get("list_name", list_id)).strip() or list_id
            await _record_activity("Deleted archived list", archived_name, archived_name, "typed")
            return {"ok": True, "dashboard": await _build_dashboard_payload_internal("default")}

        if action == "set_status":
            list_entity = str(payload.get("list_entity", "")).strip()
            item_ref = str(payload.get("item", "")).strip()
            status = str(payload.get("status", "")).strip().lower()
            selected_list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _mark_changed_list(selected_list_id)
            if list_entity and item_ref and status in {"completed", "needs_action"}:
                if multilist_mode:
                    _, list_obj = _internal_list_by_id(selected_list_id) if selected_list_id else _active_internal_list()
                    items: list[dict[str, Any]] = list_obj.setdefault("items", [])
                    item = _internal_find_item(items, item_ref)
                    if item is not None:
                        item["status"] = status
                        await _save()
                        await _record_activity(
                            "Item completed" if status == "completed" else "Item restored",
                            str(item.get("summary", "")).strip(),
                            str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
                            "typed",
                        )
                    return {"ok": True}
                await hass.services.async_call(
                    "todo",
                    "update_item",
                    {"item": item_ref, "status": status},
                    target={"entity_id": list_entity},
                    blocking=True,
                )
            return {"ok": True}

        if action == "update_item":
            list_entity = str(payload.get("list_entity", "")).strip()
            item_ref = str(payload.get("item", "")).strip()
            next_summary = str(payload.get("summary", "")).strip()
            next_quantity = _coerce_quantity(payload.get("quantity", 1))
            target_category = _normalize_category(str(payload.get("target_category", "")).strip())
            learn = bool(payload.get("learn", True))
            selected_list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _mark_changed_list(selected_list_id)
            categories = _active_categories()
            if not list_entity or not item_ref or not next_summary:
                return {"ok": False, "error": "missing_item_reference"}
            if multilist_mode:
                _, list_obj = _internal_list_by_id(selected_list_id) if selected_list_id else _active_internal_list()
                list_categories = [c for c in list_obj.get("categories", []) if c != "other"]
                if target_category not in list_categories and target_category != "other":
                    target_category = "other"
                items: list[dict[str, Any]] = list_obj.setdefault("items", [])
                found_internal = _internal_find_item(items, item_ref)
                if found_internal is None:
                    return {"ok": False, "error": "item_not_found"}
                old_summary = str(found_internal.get("summary", "")).strip()
                old_category = str(found_internal.get("category", "other")).strip() or "other"
                found_internal["summary"] = next_summary
                found_internal["quantity"] = next_quantity
                if target_category:
                    found_internal["category"] = target_category
                _move_item_meta_entry(
                    _internal_list_entity(old_category),
                    old_summary,
                    _internal_list_entity(str(found_internal.get("category", "other")).strip() or "other"),
                    next_summary,
                )
                await _set_item_meta_quantity(
                    _internal_list_entity(str(found_internal.get("category", "other")).strip() or "other"),
                    next_summary,
                    next_quantity,
                )
                if learn and target_category in categories:
                    norm = _normalize_term(next_summary)
                    terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
                    existing = set(terms_obj.data.get(target_category, []))
                    if norm and norm not in existing:
                        terms_obj.data.setdefault(target_category, []).append(norm)
                await _save()
                await _record_activity(
                    "Item updated",
                    f"{old_summary} -> {next_summary}" if old_summary != next_summary else next_summary,
                    str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
                    "typed",
                )
                return {"ok": True}
            found = await _resolve_item_ref(list_entity, item_ref)
            if found is None:
                return {"ok": False, "error": "item_not_found"}
            old_summary = str(found.get("summary", "")).strip()
            description = str(found.get("description", "")).strip()
            status = str(found.get("status", "needs_action")).strip().lower() or "needs_action"
            remove_id = str(found.get("uid", "")).strip() or old_summary
            target_list = list_entity
            if target_category:
                if target_category not in categories and target_category != "other":
                    target_category = "other"
                target_list = _target_list_for_category(target_category)
            await hass.services.async_call(
                "todo",
                "add_item",
                {"item": next_summary, "description": description},
                target={"entity_id": target_list},
                blocking=True,
            )
            _move_item_meta_entry(list_entity, old_summary, target_list, next_summary)
            await _set_item_meta_quantity(target_list, next_summary, next_quantity)
            replacement = await _resolve_item_ref(target_list, next_summary)
            if replacement is not None:
                replacement_id = str(replacement.get("uid", "")).strip() or next_summary
                replacement_description = _description_with_existing_meta(
                    target_list,
                    next_summary,
                    str(replacement.get("description", "")).strip() or description,
                )
                update_payload: dict[str, Any] = {"item": replacement_id, "description": replacement_description}
                if status == "completed":
                    update_payload["status"] = "completed"
                await hass.services.async_call(
                    "todo",
                    "update_item",
                    update_payload,
                    target={"entity_id": target_list},
                    blocking=True,
                )
            if remove_id:
                await hass.services.async_call(
                    "todo",
                    "remove_item",
                    {"item": remove_id},
                    target={"entity_id": list_entity},
                    blocking=True,
                )
            if learn and target_category in categories:
                norm = _normalize_term(next_summary)
                terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
                existing = set(terms_obj.data.get(target_category, []))
                if norm and norm not in existing:
                    terms_obj.data.setdefault(target_category, []).append(norm)
            await _save()
            return {"ok": True}

        if action == "recategorize":
            from_list = str(payload.get("from_list", "")).strip()
            item_ref = str(payload.get("item", "")).strip()
            target_category = _normalize_category(str(payload.get("target_category", "")).strip())
            learn = bool(payload.get("learn", True))
            selected_list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            categories = _active_categories()
            if not from_list or not item_ref:
                return {"ok": False, "error": "missing_item_reference"}
            if multilist_mode:
                _, list_obj = _internal_list_by_id(selected_list_id) if selected_list_id else _active_internal_list()
                list_categories = [c for c in list_obj.get("categories", []) if c != "other"]
                if target_category not in list_categories and target_category != "other":
                    target_category = "other"
                items: list[dict[str, Any]] = list_obj.setdefault("items", [])
                found_internal = _internal_find_item(items, item_ref)
                if found_internal is None:
                    await _clear_pending_review()
                    return {"ok": False, "error": "item_not_found"}
                summary = str(found_internal.get("summary", "")).strip()
                if not summary:
                    return {"ok": False, "error": "item_summary_missing"}
                found_internal["category"] = target_category
                if learn and target_category in categories:
                    norm = _normalize_term(summary)
                    terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
                    existing = set(terms_obj.data.get(target_category, []))
                    if norm and norm not in existing:
                        terms_obj.data.setdefault(target_category, []).append(norm)
                await _clear_pending_review()
                await _save()
                await _record_activity(
                    "Category changed",
                    f"{summary} -> {_display_name_for_category(target_category)}",
                    str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
                    "review_move" if learn else "typed",
                )
                return {"ok": True}
            if target_category not in categories and target_category != "other":
                target_category = "other"
            target_list = _target_list_for_category(target_category)
            found = await _resolve_item_ref(from_list, item_ref)
            if found is not None:
                summary = str(found.get("summary", "")).strip()
                description = str(found.get("description", "")).strip()
                remove_id = str(found.get("uid", "")).strip() or summary
                if summary:
                    await hass.services.async_call(
                        "todo",
                        "add_item",
                        {"item": summary, "description": description},
                        target={"entity_id": target_list},
                        blocking=True,
                    )
                    if remove_id:
                        await hass.services.async_call(
                            "todo",
                            "remove_item",
                            {"item": remove_id},
                            target={"entity_id": from_list},
                            blocking=True,
                        )
                    if learn and target_category in categories:
                        norm = _normalize_term(summary)
                        terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
                        existing = set(terms_obj.data.get(target_category, []))
                        if norm and norm not in existing:
                            terms_obj.data.setdefault(target_category, []).append(norm)
                            await _save()
                    await _clear_pending_review()
                    return {"ok": True}
                return {"ok": False, "error": "item_summary_missing"}
            await _clear_pending_review()
            return {"ok": False, "error": "item_not_found"}

        if action == "clear_completed":
            selected_list_id = _normalize_list_id(str(payload.get("list_id", "")).strip())
            _mark_changed_list(selected_list_id)
            if multilist_mode:
                active_list_id, list_obj = _internal_list_by_id(selected_list_id) if selected_list_id else _active_internal_list()
                items: list[dict[str, Any]] = list_obj.setdefault("items", [])
                removed_items = [i for i in items if str(i.get("status", "")).strip() == "completed"]
                removed_count = len(removed_items)
                for removed in removed_items:
                    await _remove_item_meta_entry(
                        _internal_list_entity(str(removed.get("category", "other")).strip() or "other"),
                        str(removed.get("summary", "")).strip(),
                    )
                list_obj["items"] = [i for i in items if str(i.get("status", "")).strip() != "completed"]
                await _save()
                await _record_activity(
                    "Cleared completed",
                    f"Removed {removed_count} completed item{'s' if removed_count != 1 else ''}",
                    str(list_obj.get("name", "Grocery List")).strip() or "Grocery List",
                    "typed",
                )
                return {"ok": True, "dashboard": await _build_dashboard_payload_internal(active_list_id)}
            completed_items = await _list_items(COMPLETED_LIST_ENTITY, "completed")
            removed_count = 0
            for item in completed_items:
                remove_id = str(item.get("uid", "")).strip() or str(item.get("summary", "")).strip()
                if not remove_id:
                    continue
                await _remove_item_meta_entry(COMPLETED_LIST_ENTITY, str(item.get("summary", "")).strip())
                await hass.services.async_call(
                    "todo",
                    "remove_item",
                    {"item": remove_id},
                    target={"entity_id": COMPLETED_LIST_ENTITY},
                    blocking=True,
                )
                removed_count += 1
            await _record_activity("Cleared completed", f"Removed {removed_count} completed item{'s' if removed_count != 1 else ''}", "Grocery Completed", "typed")
            return {"ok": True, "dashboard": await _build_dashboard_payload()}

        if action == "repair_system":
            active_entry = hass.data.get(DOMAIN, {}).get("entry")
            _ensure_multilist_model()
            await _ensure_required_lists(active_entry)
            await _ensure_internal_voice_bridges()
            await _ensure_required_helpers()
            if active_entry is not None and bool(_entry_value(active_entry, CONF_AUTO_DASHBOARD, True)):
                await _ensure_dashboards(active_entry)
            await _save()
            await _record_activity(
                "Repaired setup",
                "Re-provisioned lists, helpers, and dashboards",
                "Local List Assist",
                "typed",
            )
            return {"ok": True, "dashboard": await _build_dashboard_payload()}

        if action == "install_voice_sentences":
            language = str(payload.get("language", "en")).strip() or "en"
            path_written = await _install_voice_sentences(language)
            return {"ok": True, "path": path_written}

        if action == "save_settings":
            active_entry: ConfigEntry | None = hass.data.get(DOMAIN, {}).get("entry")
            if active_entry is None:
                return {"ok": False, "error": "entry_not_loaded"}

            categories = _categories_from_raw(payload.get("categories", _active_categories()))
            current_inbox = str(_entry_value(active_entry, CONF_INBOX_ENTITY, "todo.grocery_inbox")).strip() or "todo.grocery_inbox"
            inbox_entity = str(payload.get("inbox_entity", current_inbox)).strip() or current_inbox
            if "." not in inbox_entity:
                inbox_entity = f"todo.{_normalize_category(inbox_entity)}"

            auto_route = bool(payload.get("auto_route_inbox", bool(_entry_value(active_entry, CONF_AUTO_ROUTE_INBOX, True))))
            auto_provision = bool(payload.get("auto_provision", bool(_entry_value(active_entry, CONF_AUTO_PROVISION, True))))
            experimental_multilist = True
            default_grocery_categories = bool(
                payload.get("default_grocery_categories", bool(_entry_value(active_entry, CONF_DEFAULT_GROCERY_CATEGORIES, True)))
            )
            debug_mode = bool(payload.get("debug_mode", bool(_entry_value(active_entry, CONF_DEBUG_MODE, False))))
            dashboard_name = str(payload.get("dashboard_name", _dashboard_name(active_entry))).strip() or "Local List Assist"
            complete_setup = bool(payload.get("complete_setup", False))

            new_options = dict(active_entry.options)
            new_options[CONF_CATEGORIES] = categories
            new_options[CONF_INBOX_ENTITY] = inbox_entity
            new_options[CONF_AUTO_ROUTE_INBOX] = auto_route
            new_options[CONF_AUTO_PROVISION] = auto_provision
            new_options[CONF_EXPERIMENTAL_MULTILIST] = experimental_multilist
            new_options[CONF_DEFAULT_GROCERY_CATEGORIES] = default_grocery_categories
            new_options[CONF_DEBUG_MODE] = debug_mode
            new_options[CONF_DASHBOARD_NAME] = dashboard_name
            if complete_setup:
                new_options[CONF_WIZARD_COMPLETED] = True

            hass.config_entries.async_update_entry(active_entry, options=new_options)
            hass.data[DOMAIN]["categories"] = categories

            store_obj: GroceryLearningStore = hass.data[DOMAIN]["store"]
            hass.data[DOMAIN]["terms"] = await store_obj.load(categories)
            hass.data[DOMAIN]["item_meta"] = await store_obj.load_item_meta()
            hass.data[DOMAIN]["multilist"] = await store_obj.load_multilist(categories)
            _ensure_multilist_model()
            default_list = hass.data[DOMAIN]["multilist"].get("lists", {}).get("default")
            if isinstance(default_list, dict):
                default_list["categories"] = categories + ["other"]
            await _save()
            await _ensure_internal_voice_bridges()
            await _sync_helpers_internal()
            if bool(_entry_value(active_entry, CONF_AUTO_DASHBOARD, True)):
                await _ensure_dashboards(active_entry)
            return {"ok": True, "dashboard": await _build_dashboard_payload()}

        if action == "apply_review":
            if multilist_mode:
                category = str(payload.get("category", "")).strip()
                learn = bool(payload.get("learn", True))
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_APPLY_REVIEW,
                    {"category": category, "learn": learn},
                    blocking=True,
                )
                return {"ok": True}
            category = str(payload.get("category", "")).strip()
            learn = bool(payload.get("learn", True))
            await hass.services.async_call(
                DOMAIN,
                SERVICE_APPLY_REVIEW,
                {"category": category, "learn": learn},
                blocking=True,
            )
            return {"ok": True}

        if action == "confirm_duplicate":
            decision = str(payload.get("decision", "skip")).strip().lower()
            actor_user_id = str(payload.get("actor_user_id", "")).strip() or str(payload.get("_request_user_id", "")).strip()
            actor_name = str(payload.get("actor_name", "")).strip()
            if actor_user_id and not actor_name:
                dup_user = await hass.auth.async_get_user(actor_user_id)
                actor_name = _display_name_from_user(dup_user)
            if multilist_mode:
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_CONFIRM_DUPLICATE,
                    {
                        "decision": decision if decision in {"add", "skip"} else "skip",
                        "actor_user_id": actor_user_id,
                        "actor_name": actor_name,
                    },
                    blocking=True,
                )
                return {"ok": True}
            await hass.services.async_call(
                DOMAIN,
                SERVICE_CONFIRM_DUPLICATE,
                {
                    "decision": decision if decision in {"add", "skip"} else "skip",
                    "actor_user_id": actor_user_id,
                    "actor_name": actor_name,
                },
                blocking=True,
            )
            return {"ok": True}

        return {"ok": False, "error": "unknown_action"}

    async def _clear_pending_duplicate() -> None:
        hass.data[DOMAIN]["pending_duplicate"] = {}
        await _set_helper_if_exists(DUPLICATE_PENDING_ITEM_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_TARGET_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_KEY_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_BY_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_WHEN_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_SOURCE_HELPER, "")
        await _set_helper_if_exists(DUPLICATE_PENDING_HELPER, "off")
        _update_duplicate_status_entities(pending=False)

    async def _set_pending_duplicate(
        *,
        item: str,
        target_list: str,
        normalized: str,
        existing_by: str,
        existing_source: str,
        existing_when: str,
        interactive: bool,
    ) -> None:
        hass.data[DOMAIN]["pending_duplicate"] = {
            "item": item,
            "target_list": target_list,
            "normalized": normalized,
            "existing_by": existing_by,
            "existing_source": existing_source,
            "existing_when": existing_when,
            "interactive": interactive,
        }
        await _set_helper_if_exists(DUPLICATE_PENDING_ITEM_HELPER, item)
        await _set_helper_if_exists(DUPLICATE_PENDING_TARGET_HELPER, target_list)
        await _set_helper_if_exists(DUPLICATE_PENDING_KEY_HELPER, normalized)
        await _set_helper_if_exists(DUPLICATE_PENDING_BY_HELPER, existing_by)
        await _set_helper_if_exists(DUPLICATE_PENDING_WHEN_HELPER, existing_when)
        await _set_helper_if_exists(DUPLICATE_PENDING_SOURCE_HELPER, existing_source)
        await _set_helper_if_exists(DUPLICATE_PENDING_HELPER, "on")
        _update_duplicate_status_entities(
            pending=True,
            item=item,
            target=target_list,
            added_by=existing_by,
            added_when=existing_when,
            source=existing_source,
        )

    async def _set_pending_review(item: str, source_list: str) -> None:
        hass.data[DOMAIN]["pending_review"] = {"item": item, "source_list": source_list}
        await _set_helper_if_exists(REVIEW_ITEM_HELPER, item)
        await _set_helper_if_exists(REVIEW_SOURCE_HELPER, source_list)
        await _set_helper_if_exists(REVIEW_PENDING_HELPER, "on")
        _update_review_status_entities(pending=True, item=item, source_list=source_list)

    async def _clear_pending_review() -> None:
        hass.data[DOMAIN]["pending_review"] = {}
        await _set_helper_if_exists(REVIEW_PENDING_HELPER, "off")
        await _set_helper_if_exists(REVIEW_ITEM_HELPER, "")
        await _set_helper_if_exists(REVIEW_SOURCE_HELPER, "")
        _update_review_status_entities(pending=False)

    def _find_todo_entity_by_friendly_name(title: str) -> str:
        expected = str(title).strip().lower()
        if not expected:
            return ""
        for state_obj in hass.states.async_all("todo"):
            friendly = str(state_obj.attributes.get("friendly_name", "")).strip().lower()
            if friendly == expected:
                return str(state_obj.entity_id).strip()
        return ""

    async def _ensure_local_todo_list(entity_id: str, title: str) -> str:
        if hass.states.get(entity_id) is not None:
            return entity_id

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
                return entity_id
            matched = _find_todo_entity_by_friendly_name(title)
            if matched:
                return matched
        return ""

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
        await _ensure_local_todo_list(COMPLETED_LIST_ENTITY, "Grocery Completed")

    async def _ensure_internal_voice_bridges() -> None:
        if not _multilist_enabled():
            return
        _ensure_multilist_model()
        model = hass.data[DOMAIN]["multilist"]
        lists = model.get("lists", {})
        changed = False
        for list_id, list_obj in lists.items():
            if not isinstance(list_obj, dict):
                continue
            name = str(list_obj.get("name", list_id)).strip() or str(list_id)
            voice_entity = str(list_obj.get("voice_entity", _internal_voice_bridge_entity(str(list_id)))).strip()
            if not voice_entity:
                voice_entity = _internal_voice_bridge_entity(str(list_id))
            resolved_voice = await _ensure_local_todo_list(voice_entity, name)
            if resolved_voice:
                voice_entity = resolved_voice
            if str(list_obj.get("voice_entity", "")).strip() != voice_entity:
                list_obj["voice_entity"] = voice_entity
                changed = True
            alias_title = _voice_bridge_title(name)
            if alias_title.strip().lower() != name.strip().lower():
                alias_entity = _internal_voice_alias_entity(str(list_id))
                resolved_alias = await _ensure_local_todo_list(alias_entity, alias_title)
                alias_entities = [
                    str(candidate).strip()
                    for candidate in list_obj.get("voice_alias_entities", [])
                    if isinstance(candidate, str) and str(candidate).strip()
                ]
                if resolved_alias and resolved_alias != voice_entity and resolved_alias not in alias_entities:
                    alias_entities.append(resolved_alias)
                if alias_entity not in alias_entities and hass.states.get(alias_entity) is not None:
                    alias_entities.append(alias_entity)
                if alias_entities != list_obj.get("voice_alias_entities", []):
                    list_obj["voice_alias_entities"] = alias_entities
                    changed = True
        if changed:
            await _save()

    async def _ensure_helper_entity(
        helper_domain: str,
        entity_id: str,
        title: str,
        payload: dict[str, Any],
    ) -> None:
        if hass.states.get(entity_id) is not None:
            return

        attempts = [dict(payload), {k: v for k, v in payload.items() if k != "icon"}]
        for base_payload in attempts:
            try:
                result = await hass.config_entries.flow.async_init(
                    helper_domain,
                    context={"source": "user"},
                    data=base_payload,
                )
            except Exception as err:  # pragma: no cover
                _LOGGER.debug("Helper async_init failed for %s (%s): %s", entity_id, helper_domain, err)
                continue

            for _ in range(5):
                if hass.states.get(entity_id) is not None:
                    return
                if not isinstance(result, Mapping):
                    break
                if result.get("type") in {"create_entry", "abort"}:
                    break
                if result.get("type") != "form" or "flow_id" not in result:
                    break

                next_input: dict[str, Any] = {}
                data_schema = result.get("data_schema")
                schema_map = getattr(data_schema, "schema", {}) if data_schema else {}
                if isinstance(schema_map, dict):
                    for marker, validator in schema_map.items():
                        key = getattr(marker, "schema", marker)
                        key_name = str(key)
                        key_low = key_name.lower()
                        if key_name in base_payload:
                            next_input[key_name] = base_payload[key_name]
                        elif "name" in key_low:
                            next_input[key_name] = title
                        elif "option" in key_low and "options" in base_payload:
                            next_input[key_name] = list(base_payload["options"])
                        elif "max" in key_low:
                            next_input[key_name] = int(base_payload.get("max", 255))
                        elif "min" in key_low:
                            next_input[key_name] = int(base_payload.get("min", 0))
                        elif validator is bool:
                            next_input[key_name] = bool(base_payload.get(key_name, True))
                result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=next_input or base_payload)

            if hass.states.get(entity_id) is not None:
                return

    async def _ensure_required_helpers() -> None:
        categories = _active_categories()

        await _ensure_helper_entity(
            "input_boolean",
            REVIEW_PENDING_HELPER,
            "Local List Review Pending",
            {"name": "Local List Review Pending", "icon": "mdi:clipboard-text-clock-outline"},
        )
        await _ensure_helper_entity(
            "input_text",
            REVIEW_ITEM_HELPER,
            "Local List Review Item",
            {"name": "Local List Review Item", "max": 255, "icon": "mdi:cart"},
        )
        await _ensure_helper_entity(
            "input_text",
            REVIEW_SOURCE_HELPER,
            "Local List Review Source List",
            {"name": "Local List Review Source List", "max": 255, "icon": "mdi:playlist-check"},
        )
        await _ensure_helper_entity(
            "input_select",
            REVIEW_CATEGORY_HELPER,
            "Grocery Review Category",
            {
                "name": "Grocery Review Category",
                "options": [_display_name_for_category(c) for c in categories] + ["Keep Other"],
                "icon": "mdi:shape-outline",
            },
        )
        await _ensure_helper_entity(
            "input_button",
            "input_button.grocery_review_apply",
            "Apply Category Review",
            {"name": "Apply Category Review", "icon": "mdi:check-bold"},
        )

        await _ensure_helper_entity(
            "input_boolean",
            DUPLICATE_PENDING_HELPER,
            "Local List Duplicate Pending",
            {"name": "Local List Duplicate Pending", "icon": "mdi:content-duplicate"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_ITEM_HELPER,
            "Local List Duplicate Item",
            {"name": "Local List Duplicate Item", "max": 255, "icon": "mdi:cart-outline"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_TARGET_HELPER,
            "Local List Duplicate Target List",
            {"name": "Local List Duplicate Target List", "max": 255, "icon": "mdi:format-list-bulleted"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_KEY_HELPER,
            "Local List Duplicate Key",
            {"name": "Local List Duplicate Key", "max": 255, "icon": "mdi:key-variant"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_BY_HELPER,
            "Local List Duplicate Added By",
            {"name": "Local List Duplicate Added By", "max": 255, "icon": "mdi:account"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_WHEN_HELPER,
            "Local List Duplicate Added When",
            {"name": "Local List Duplicate Added When", "max": 255, "icon": "mdi:clock-outline"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_SOURCE_HELPER,
            "Local List Duplicate Source",
            {"name": "Local List Duplicate Source", "max": 255, "icon": "mdi:source-branch"},
        )

        for category in categories:
            await _ensure_helper_entity(
                "input_text",
                _helper_for_category(category),
                f"Grocery Learned {_display_name_for_category(category)}",
                {"name": f"Grocery Learned {_display_name_for_category(category)}", "max": 255, "icon": "mdi:brain"},
            )

    async def _upsert_storage_dashboard_meta(
        dashboard_id: str,
        title: str,
        icon: str,
        require_admin: bool,
        url_path: str,
        show_in_sidebar: bool = True,
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
                    "show_in_sidebar": show_in_sidebar,
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
                    "show_in_sidebar": show_in_sidebar,
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
                "hide_completed": True,
                "hide_create": True,
                "hide_section_headers": True,
            },
        }

    def _build_main_dashboard_config(entry: ConfigEntry | None) -> dict[str, Any]:
        dashboard_name = _dashboard_name(entry)
        return {
            "config": {
                "title": dashboard_name,
                "views": [
                    {
                        "title": dashboard_name,
                        "path": "grocery",
                        "icon": "mdi:cart-variant",
                        "type": "masonry",
                        "cards": [
                            {
                                "type": "button",
                                "name": "Open Local List Assist",
                                "icon": "mdi:cart-variant",
                                "tap_action": {"action": "navigate", "navigation_path": "/grocery-app"},
                            }
                        ],
                    }
                ],
            }
        }

    def _build_admin_dashboard_config(entry: ConfigEntry | None) -> dict[str, Any]:
        dashboard_name = _admin_dashboard_name(entry)
        return {
            "config": {
                "title": dashboard_name,
                "views": [
                    {
                        "title": dashboard_name,
                        "path": "grocery-admin",
                        "icon": "mdi:shield-crown",
                        "type": "masonry",
                        "cards": [
                            {
                                "type": "button",
                                "name": "Open Local List Assist",
                                "icon": "mdi:cart-variant",
                                "tap_action": {"action": "navigate", "navigation_path": "/grocery-app"},
                            }
                        ],
                    }
                ],
            }
        }

    async def _ensure_dashboards(entry: ConfigEntry | None) -> None:
        if not bool(_entry_value(entry, CONF_AUTO_DASHBOARD, True)):
            return

        dashboard_name = _dashboard_name(entry)
        admin_dashboard_name = _admin_dashboard_name(entry)

        await _upsert_storage_dashboard_meta("grocery", dashboard_name, "mdi:cart-variant", False, "grocery", show_in_sidebar=False)
        await _upsert_storage_dashboard_meta(
            "grocery_admin",
            admin_dashboard_name,
            "mdi:shield-crown",
            True,
            "grocery-admin",
            show_in_sidebar=False,
        )

        main_store = Store(hass, 1, "lovelace.grocery")
        admin_store = Store(hass, 1, "lovelace.grocery_admin")
        await main_store.async_save(_build_main_dashboard_config(entry))
        await admin_store.async_save(_build_admin_dashboard_config(entry))

    def _get_category_for_term(terms_obj: LearnedTerms, normalized: str) -> str:
        return _category_for_term(
            terms_obj.data,
            normalized,
            _active_categories(),
            DEFAULT_KEYWORDS_BY_CATEGORY,
        )

    async def _route_item(call: ServiceCall) -> None:
        if _multilist_enabled():
            await _route_item_internal(call)
            return

    async def _add_to_list(call: ServiceCall) -> None:
        item = str(call.data.get("item", "")).strip()
        if not item:
            return
        quantity = _coerce_quantity(call.data.get("quantity", 1))
        source = str(call.data.get("source", "service_call")).strip() or "service_call"
        actor_user_id = str(call.data.get("actor_user_id", "")).strip()
        actor_name = str(call.data.get("actor_name", "")).strip()
        list_name = str(call.data.get("list_name", "")).strip()
        list_id = str(call.data.get("list_id", "")).strip()
        resolved_list_name = list_name
        if list_id and not resolved_list_name:
            resolved_id, resolved_obj = _internal_list_by_id(list_id)
            resolved_list_name = str(resolved_obj.get("name", resolved_id)).strip()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_ROUTE_ITEM,
            {
                "item": item,
                "quantity": quantity,
                "source": source,
                "source_list_name": resolved_list_name,
                "allow_duplicate": bool(call.data.get("allow_duplicate", False)),
                "actor_user_id": actor_user_id,
                "actor_name": actor_name,
                "review_on_other": True,
            },
            blocking=True,
            context=call.context,
        )

    async def _apply_review(call: ServiceCall) -> None:
        if _multilist_enabled():
            await _apply_review_internal(call)
            return

    async def _confirm_duplicate(call: ServiceCall) -> None:
        if _multilist_enabled():
            await _confirm_duplicate_internal(call)
            return

    def _voice_sentence_pack(language: str) -> str:
        if language != "en":
            raise vol.Invalid("Only English voice sentences are bundled right now")
        return """language: "en"
intents:
  LocalListAssistAddItem:
    data:
      - sentences:
          - "(add|put) {item} to [my] (grocery|shopping) list"
          - "(add|put) {item} on [my] (grocery|shopping) list"
          - "(add|put) {item} to [my] grocery"
          - "(add|put) {item} on [my] shopping"
        slots:
          list_name: "Grocery List"
      - sentences:
          - "(add|put) {item} to [my] {list_name} list"
          - "(add|put) {item} on [my] {list_name} list"
          - "(add|put) {item} to [my] {list_name}"
          - "(add|put) {item} on [my] {list_name}"
          - "(add|put) {item} for [my] {list_name} list"
          - "(add|put) {item} for [my] {list_name}"
          - "(add|put) {item} into [my] {list_name} list"
          - "(add|put) {item} into [my] {list_name}"
lists:
  item:
    wildcard: true
  list_name:
    wildcard: true
"""

    async def _install_voice_sentences(language: str) -> str:
        normalized_language = language.strip().lower() or "en"
        content = _voice_sentence_pack(normalized_language)
        sentences_dir = Path(hass.config.path("custom_sentences", normalized_language))
        sentences_path = sentences_dir / "local_list_assist.yaml"

        def _write_pack() -> None:
            sentences_dir.mkdir(parents=True, exist_ok=True)
            sentences_path.write_text(content, encoding="utf-8")

        # Filesystem writes must not run on the event loop.
        await hass.async_add_executor_job(_write_pack)
        try:
            await hass.services.async_call("conversation", "reload", blocking=True)
        except Exception as err:  # pragma: no cover
            _LOGGER.debug("Conversation reload after sentence install failed: %s", err)
        await _record_activity(
            "Voice phrases installed",
            f"Installed {normalized_language} sentence pack",
            "Local List Assist",
            "system",
        )
        return str(sentences_path)

    async def _install_voice_sentences_service(call: ServiceCall) -> None:
        language = str(call.data.get("language", "en")).strip() or "en"
        await _install_voice_sentences(language)

    class LocalListAssistAddItemIntent(intent_helper.IntentHandler):
        """Direct Assist intent handler for internal list adds."""

        intent_type = INTENT_LOCAL_LIST_ASSIST_ADD_ITEM
        description = "Add an item to a Local List Assist list"
        platforms = {"conversation"}

        @property
        def slot_schema(self) -> dict[str, Any]:
            return {
                vol.Required("item"): intent_helper.non_empty_string,
                vol.Optional("list_name"): intent_helper.non_empty_string,
            }

        async def async_handle(
            self,
            intent_obj: intent_helper.Intent,
        ) -> intent_helper.IntentResponse:
            slots = self.async_validate_slots(intent_obj.slots)
            item = str(slots.get("item", {}).get("value", "")).strip()
            spoken_item = _display_item_summary(item) or item
            requested_list_name = str(slots.get("list_name", {}).get("value", "")).strip()
            response = intent_obj.create_response()

            if not item:
                response.async_set_error(
                    intent_helper.IntentResponseErrorCode.NO_INTENT_MATCH,
                    "I didn't catch the item to add.",
                )
                return response

            actor_user_id = str(intent_obj.context.user_id or "").strip()
            actor_name = ""
            if actor_user_id:
                actor_user = await hass.auth.async_get_user(actor_user_id)
                actor_name = _display_name_from_user(actor_user)

            if _multilist_enabled():
                target_list_id = ""
                if requested_list_name:
                    target_list_id = _internal_list_id_from_voice_name(requested_list_name)
                    if not target_list_id:
                        normalized_list_name = _normalize_term(requested_list_name)
                        if "grocery" in normalized_list_name or "shopping" in normalized_list_name:
                            target_list_id = "default"
                if not target_list_id:
                    target_list_id = "default"

                resolved_list_id, resolved_list = _internal_list_by_id(target_list_id)
                resolved_list_name = str(resolved_list.get("name", "Grocery List")).strip() or "Grocery List"
                normalized_item = _normalize_term(spoken_item)

                async def _add_and_count() -> int:
                    # Read the pre-existing count and perform the add atomically
                    # under the action lock so a concurrent add of the same item
                    # cannot make the spoken confirmation wrong. The nested
                    # service call re-enters the lock (same context) safely.
                    _, current_list = _internal_list_by_id(resolved_list_id)
                    prior = sum(
                        1
                        for existing in current_list.get("items", [])
                        if str(existing.get("status", "")).strip() == "needs_action"
                        and _normalize_term(str(existing.get("summary", "")).strip()) == normalized_item
                    )
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_ADD_TO_LIST,
                        {
                            "item": item,
                            "list_id": resolved_list_id,
                            "list_name": resolved_list_name,
                            "source": "voice_assistant",
                            "actor_user_id": actor_user_id,
                            "actor_name": actor_name,
                            "allow_duplicate": False,
                        },
                        blocking=True,
                        context=intent_obj.context,
                    )
                    return prior

                before_count = await _run_locked(_add_and_count)

                # add_to_list always records the add: a brand-new row adds one
                # to the count, while an existing item merges into its quantity
                # and leaves the count unchanged. Report both honestly instead
                # of claiming nothing happened on a merge.
                if before_count > 0:
                    response.async_set_speech(f"Added another {spoken_item} to {resolved_list_name}.")
                else:
                    response.async_set_speech(f"Added {spoken_item} to {resolved_list_name}.")
                response.async_set_card("Local List Assist", f"{spoken_item} -> {resolved_list_name}")
                return response

            await hass.services.async_call(
                DOMAIN,
                SERVICE_ADD_TO_LIST,
                {
                    "item": item,
                    "source": "voice_assistant",
                    "actor_user_id": actor_user_id,
                    "actor_name": actor_name,
                    "allow_duplicate": False,
                },
                blocking=True,
                context=intent_obj.context,
            )
            response.async_set_speech(f"Added {spoken_item} to Grocery List.")
            response.async_set_card("Local List Assist", f"{spoken_item} -> Grocery List")
            return response

    def _locked_service(handler):
        """Wrap a service handler so its state mutations run under the lock."""

        async def _wrapped(call: ServiceCall) -> None:
            await _run_locked(lambda: handler(call))

        return _wrapped

    hass.services.async_register(DOMAIN, SERVICE_LEARN_TERM, _locked_service(_learn_term), schema=LEARN_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FORGET_TERM, _locked_service(_forget_term), schema=FORGET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SYNC_HELPERS, _sync_helpers)
    hass.services.async_register(DOMAIN, SERVICE_ROUTE_ITEM, _locked_service(_route_item), schema=ROUTE_ITEM_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ADD_TO_LIST, _locked_service(_add_to_list), schema=ADD_TO_LIST_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_INSTALL_VOICE_SENTENCES,
        _locked_service(_install_voice_sentences_service),
        schema=INSTALL_VOICE_SENTENCES_SCHEMA,
    )
    hass.services.async_register(DOMAIN, SERVICE_APPLY_REVIEW, _locked_service(_apply_review), schema=APPLY_REVIEW_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIRM_DUPLICATE,
        _locked_service(_confirm_duplicate),
        schema=CONFIRM_DUPLICATE_SCHEMA,
    )
    if not data.get("intent_registered"):
        intent_helper.async_register(hass, LocalListAssistAddItemIntent())
        data["intent_registered"] = True

    _update_review_status_entities(pending=False)
    _update_duplicate_status_entities(pending=False)

    if not data.get("views_registered"):
        hass.http.register_view(GroceryLearningDashboardView())
        hass.http.register_view(GroceryLearningActionView())
        data["views_registered"] = True

    if not data.get("ws_registered"):
        data.setdefault("update_listeners", set())

        @websocket_api.websocket_command(
            {vol.Required("type"): "grocery_learning/subscribe_updates"}
        )
        @websocket_api.async_response
        async def _ws_subscribe_updates(hass_inner, connection, msg):
            listeners: set = hass_inner.data.setdefault(DOMAIN, {}).setdefault("update_listeners", set())

            def _forward(revision: int, changed_list_id: str = "*") -> None:
                connection.send_message(
                    websocket_api.event_message(
                        msg["id"], {"revision": revision, "list_id": changed_list_id}
                    )
                )

            listeners.add(_forward)

            @callback
            def _unsubscribe() -> None:
                listeners.discard(_forward)

            connection.subscriptions[msg["id"]] = _unsubscribe
            connection.send_result(msg["id"])
            # Send the current revision immediately so a just-opened panel syncs.
            _forward(int(hass_inner.data.get(DOMAIN, {}).get("dashboard_revision", 0) or 0), "*")

        websocket_api.async_register_command(hass, _ws_subscribe_updates)
        data["ws_registered"] = True

    if not data.get("panel_registered"):
        panel_dir = Path(__file__).resolve().parent / "frontend"
        if not data.get("panel_assets_registered"):
            await hass.http.async_register_static_paths(
                [StaticPathConfig("/grocery_learning-panel", str(panel_dir), False)]
            )
            data["panel_assets_registered"] = True
        await _register_sidebar_panel(hass, "Local List Assist")

    data["build_dashboard_payload"] = _build_dashboard_payload
    data["handle_dashboard_action"] = _handle_dashboard_action
    data["ensure_required_lists"] = _ensure_required_lists
    data["ensure_internal_voice_bridges"] = _ensure_internal_voice_bridges
    data["ensure_required_helpers"] = _ensure_required_helpers
    data["ensure_dashboards"] = _ensure_dashboards
    # Expose the closures that the config-entry-scoped event handlers reach for
    # (they live in a different function scope and would otherwise be undefined).
    data["record_activity"] = _record_activity
    data["move_item_meta_entry"] = _move_item_meta_entry
    data["internal_voice_alias_entity"] = _internal_voice_alias_entity
    data["run_locked"] = _run_locked
    data["runtime_ready"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Local List Assist from config entry."""
    hass.data.setdefault(DOMAIN, {})["runtime_ready"] = False
    await _async_setup_runtime(hass)
    data = hass.data[DOMAIN]
    data["entry"] = entry
    data["categories"] = _categories_from_entry(entry)
    await _register_sidebar_panel(hass, _dashboard_name(entry), replace_existing=True)

    store: GroceryLearningStore = data["store"]
    data["terms"] = await store.load(data["categories"])
    data["item_meta"] = await store.load_item_meta()

    ensure_required_lists = data.get("ensure_required_lists")
    if ensure_required_lists:
        await ensure_required_lists(entry)

    ensure_internal_voice_bridges = data.get("ensure_internal_voice_bridges")
    if ensure_internal_voice_bridges:
        await ensure_internal_voice_bridges()

    ensure_required_helpers = hass.data[DOMAIN].get("ensure_required_helpers")
    if ensure_required_helpers:
        await ensure_required_helpers()

    ensure_dashboards = data.get("ensure_dashboards")
    if ensure_dashboards:
        await ensure_dashboards(entry)

    internal_context_ids: set[str] = data.setdefault("internal_context_ids", set())

    # Bind the runtime closures the event handlers below rely on. They are
    # defined in _async_setup_runtime's scope and exposed via hass.data, so the
    # local names captured by the nested handlers resolve correctly.
    _record_activity = data["record_activity"]
    _move_item_meta_entry = data["move_item_meta_entry"]
    _internal_voice_alias_entity = data["internal_voice_alias_entity"]
    _run_locked = data["run_locked"]

    def _extract_entity_id(event_data: dict[str, Any], service_data: dict[str, Any]) -> str:
        top_target = event_data.get("target", {})
        service_target = service_data.get("target", {})
        candidates: list[Any] = [
            service_data.get("entity_id", ""),
            service_target.get("entity_id", "") if isinstance(service_target, dict) else "",
            top_target.get("entity_id", "") if isinstance(top_target, dict) else "",
        ]
        for candidate in candidates:
            if isinstance(candidate, list) and candidate:
                return str(candidate[0]).strip()
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""

    def _normalize_label(value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        return re.sub(r"\s+", " ", cleaned)

    def _is_voice_intake_list(
        list_entity: str,
        inbox_entity: str,
        tracked_lists: list[str],
    ) -> bool:
        if not list_entity:
            return False
        if list_entity == inbox_entity:
            return True
        if list_entity in tracked_lists or list_entity == COMPLETED_LIST_ENTITY:
            return False

        state_obj = hass.states.get(list_entity)
        friendly_name = str(state_obj.attributes.get("friendly_name", "")).strip() if state_obj else ""
        slug_name = list_entity.split(".", 1)[1] if "." in list_entity else list_entity
        slug_name = slug_name.replace("_", " ")

        haystack = " | ".join(
            value for value in (_normalize_label(friendly_name), _normalize_label(slug_name)) if value
        )
        if not haystack:
            return False

        aliases = {
            "shopping list",
            "grocery list",
            "shopping",
            "groceries",
            "grocery",
        }
        return any(alias in haystack for alias in aliases)

    def _source_from_event_context(service_context: Context | None) -> str:
        if service_context is None:
            return "voice_assistant"
        if service_context.parent_id and service_context.user_id:
            return "voice_assistant"
        if service_context.parent_id:
            return "automation"
        if service_context.user_id:
            return "typed"
        return "voice_assistant"

    async def _get_items(list_entity: str, status: str) -> list[dict[str, Any]]:
        if not list_entity or hass.states.get(list_entity) is None:
            return []
        response = await hass.services.async_call(
            "todo",
            "get_items",
            {"status": status},
            target={"entity_id": list_entity},
            blocking=True,
            return_response=True,
        )
        resp = response.get(list_entity, response) if isinstance(response, dict) else {}
        items = resp.get("items", []) if isinstance(resp, dict) else []
        return [item for item in items if isinstance(item, dict)]

    async def _find_item(list_entity: str, item_ref: str, statuses: list[str]) -> dict[str, Any] | None:
        normalized_ref = _normalize_term(item_ref)
        for status in statuses:
            items = await _get_items(list_entity, status)
            for item in items:
                uid = str(item.get("uid", "")).strip()
                summary = str(item.get("summary", "")).strip()
                if uid and item_ref == uid:
                    return item
                if summary and (item_ref == summary or _normalize_term(summary) == normalized_ref):
                    return item
        return None

    def _split_original_list_marker(description: str) -> tuple[str, str]:
        marker = "Original list:"
        clean_lines: list[str] = []
        original_list = ""
        for line in description.splitlines():
            line_clean = line.strip()
            if line_clean.lower().startswith(marker.lower()):
                original_list = line_clean.split(":", 1)[1].strip()
                continue
            clean_lines.append(line)
        clean_description = "\n".join([line for line in clean_lines if line.strip()]).strip()
        return clean_description, original_list

    async def _move_checked_item_to_completed(source_list: str, item_ref: str) -> None:
        found = await _find_item(source_list, item_ref, ["completed", "needs_action"])
        if not found:
            return
        summary = str(found.get("summary", "")).strip()
        if not summary:
            return
        source_uid = str(found.get("uid", "")).strip() or summary
        description = str(found.get("description", "")).strip()
        marker = f"Original list: {source_list}"
        if marker not in description:
            description = f"{description}\n{marker}".strip() if description else marker

        add_ctx = Context()
        internal_context_ids.add(add_ctx.id)
        await hass.services.async_call(
            "todo",
            "add_item",
            {"item": summary, "description": description},
            target={"entity_id": COMPLETED_LIST_ENTITY},
            blocking=True,
            context=add_ctx,
        )

        added = await _find_item(COMPLETED_LIST_ENTITY, summary, ["needs_action"])
        if added:
            complete_ctx = Context()
            internal_context_ids.add(complete_ctx.id)
            await hass.services.async_call(
                "todo",
                "update_item",
                {"item": str(added.get("uid", "")).strip() or summary, "status": "completed"},
                target={"entity_id": COMPLETED_LIST_ENTITY},
                blocking=True,
                context=complete_ctx,
            )

        remove_ctx = Context()
        internal_context_ids.add(remove_ctx.id)
        await hass.services.async_call(
            "todo",
            "remove_item",
            {"item": source_uid},
            target={"entity_id": source_list},
            blocking=True,
            context=remove_ctx,
        )
        _move_item_meta_entry(source_list, summary, COMPLETED_LIST_ENTITY, summary)
        source_state = hass.states.get(source_list)
        source_name = str(source_state.attributes.get("friendly_name", "")).strip() if source_state is not None else source_list
        await _record_activity("Item completed", summary, source_name, "typed")

    async def _restore_unchecked_item_from_completed(item_ref: str) -> None:
        found = await _find_item(COMPLETED_LIST_ENTITY, item_ref, ["needs_action", "completed"])
        if not found:
            return
        summary = str(found.get("summary", "")).strip()
        if not summary:
            return
        completed_uid = str(found.get("uid", "")).strip() or summary
        description = str(found.get("description", "")).strip()
        clean_description, original_list = _split_original_list_marker(description)
        if not original_list:
            original_list = _target_list_for_category("other")
        if hass.states.get(original_list) is None:
            original_list = _target_list_for_category("other")

        add_ctx = Context()
        internal_context_ids.add(add_ctx.id)
        await hass.services.async_call(
            "todo",
            "add_item",
            {"item": summary, "description": clean_description},
            target={"entity_id": original_list},
            blocking=True,
            context=add_ctx,
        )

        remove_ctx = Context()
        internal_context_ids.add(remove_ctx.id)
        await hass.services.async_call(
            "todo",
            "remove_item",
            {"item": completed_uid},
            target={"entity_id": COMPLETED_LIST_ENTITY},
            blocking=True,
            context=remove_ctx,
        )
        _move_item_meta_entry(COMPLETED_LIST_ENTITY, summary, original_list, summary)
        restored_state = hass.states.get(original_list)
        restored_name = str(restored_state.attributes.get("friendly_name", "")).strip() if restored_state is not None else original_list
        await _record_activity("Item restored", summary, restored_name, "typed")

    async def _handle_call_service(event) -> None:
        # This bus listener is always a fresh top-level unit of work: any todo
        # call it reacts to is either external (native card/voice) or one of our
        # own tagged internal writes (filtered below). Home Assistant may create
        # the listener task while a locked action's context is active, which
        # would otherwise let _IN_LOCKED_ACTION leak in and make the nested
        # _run_locked calls skip the lock. Reset it so the listener always
        # acquires the lock on its own.
        _IN_LOCKED_ACTION.set(False)
        if event.context and event.context.id in internal_context_ids:
            internal_context_ids.discard(event.context.id)
            return

        data_event = event.data.get("service_data", {})
        service_domain = str(event.data.get("domain", "")).strip().lower()
        if service_domain not in {"todo", "shopping_list"}:
            return

        service_name = str(event.data.get("service", "")).strip()
        list_id = _extract_entity_id(event.data, data_event)
        source_ctx = _source_from_event_context(event.context)
        source_list_name = str(data_event.get("name", "")).strip()
        if not source_list_name:
            source_list_name = str(data_event.get("list_name", "")).strip()
        if not source_list_name:
            source_list_name = str(data_event.get("todo_list_name", "")).strip()
        if not source_list_name:
            source_list_name = str(data_event.get("list", "")).strip()
        if not source_list_name and list_id:
            list_state = hass.states.get(list_id)
            source_list_name = str(list_state.attributes.get("friendly_name", "")).strip() if list_state is not None else ""
        inbox_entity = _entry_value(entry, CONF_INBOX_ENTITY, "todo.grocery_inbox")
        category_lists = [_target_list_for_category(category) for category in data.get("categories", list(DEFAULT_CATEGORIES))]
        tracked_lists = category_lists + [_target_list_for_category("other")]
        multilist_enabled = True
        internal_voice_lists: list[str] = []
        if multilist_enabled:
            model = data.get("multilist", {})
            lists = model.get("lists", {}) if isinstance(model, dict) else {}
            for list_id, list_obj in lists.items():
                if not isinstance(list_obj, dict):
                    continue
                voice_entity = str(list_obj.get("voice_entity", f"todo.lla_{_normalize_category(str(list_id))}")).strip()
                if voice_entity:
                    internal_voice_lists.append(voice_entity)
                    internal_voice_lists.append(_internal_voice_alias_entity(str(list_id)))
                for alias_entity in list_obj.get("voice_alias_entities", []):
                    if isinstance(alias_entity, str) and alias_entity.strip():
                        internal_voice_lists.append(alias_entity.strip())

        if service_name == "add_item":
            item_text = str(data_event.get("item", "")).strip()
            if not item_text:
                item_text = str(data_event.get("name", "")).strip()
            if not item_text:
                return
            is_internal_voice_target = bool(list_id and list_id in internal_voice_lists)
            if not is_internal_voice_target and not _entry_value(entry, CONF_AUTO_ROUTE_INBOX, True):
                return
            is_intake_list = False
            if is_internal_voice_target:
                is_intake_list = True
            elif list_id:
                is_intake_list = _is_voice_intake_list(list_id, inbox_entity, tracked_lists)
            elif multilist_enabled and source_ctx == "voice_assistant" and source_list_name:
                is_intake_list = True
            elif multilist_enabled and source_ctx == "voice_assistant":
                is_intake_list = True
            # In internal multi-list mode, voice requests can arrive as parent-context calls
            # with inconsistent list targeting fields. Treat these as voice intake as well.
            if multilist_enabled and source_ctx in {"voice_assistant", "automation"}:
                is_intake_list = True
            if not is_intake_list:
                return
            source_label = "voice_assistant"
            try:
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_ROUTE_ITEM,
                    {
                        "item": item_text,
                        "source_list": list_id,
                        "source_list_name": source_list_name,
                        "remove_from_source": bool(is_internal_voice_target),
                        "review_on_other": True,
                        "allow_duplicate": True,
                        "interactive_duplicate": False,
                        "source": source_label,
                    },
                    blocking=True,
                    context=event.context,
                )
            except Exception as err:  # pragma: no cover
                _LOGGER.exception("Failed routing todo.add_item event item=%s list_id=%s list_name=%s: %s", item_text, list_id, source_list_name, err)
            return

        if service_name != "update_item":
            return
        if not list_id:
            return

        item_ref = str(data_event.get("item", "")).strip()
        status = str(data_event.get("status", "")).strip().lower()
        if not item_ref:
            return

        if list_id in tracked_lists and status == "completed":
            await _run_locked(lambda: _move_checked_item_to_completed(list_id, item_ref))
            return

        if list_id == COMPLETED_LIST_ENTITY and status == "needs_action":
            await _run_locked(lambda: _restore_unchecked_item_from_completed(item_ref))
            return

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







