"""Local Grocery Assistant custom integration."""

from __future__ import annotations

import logging
import re
import asyncio
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Context, HomeAssistant, ServiceCall
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

REVIEW_STATUS_PENDING_ENTITY = "sensor.grocery_review_pending_status"
REVIEW_STATUS_ITEM_ENTITY = "sensor.grocery_review_item"
REVIEW_STATUS_SOURCE_ENTITY = "sensor.grocery_review_source"

DUPLICATE_STATUS_PENDING_ENTITY = "sensor.grocery_duplicate_pending_status"
DUPLICATE_STATUS_ITEM_ENTITY = "sensor.grocery_duplicate_item"
DUPLICATE_STATUS_TARGET_ENTITY = "sensor.grocery_duplicate_target"
DUPLICATE_STATUS_BY_ENTITY = "sensor.grocery_duplicate_added_by"
DUPLICATE_STATUS_WHEN_ENTITY = "sensor.grocery_duplicate_added_when"
DUPLICATE_STATUS_SOURCE_ENTITY = "sensor.grocery_duplicate_source"


class GroceryLearningAppView(HomeAssistantView):
    """Serve a self-contained Grocery web app inside Home Assistant."""

    url = "/api/grocery_learning/app"
    name = "api:grocery_learning:app"
    requires_auth = True

    async def get(self, request):
        html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Grocery App</title>
  <style>
    :root { --bg:#11161c; --panel:#1a212a; --muted:#8ea0b5; --text:#f4f7fb; --accent:#3ea6ff; --ok:#39c27f; --warn:#ffbf47; --danger:#ff6b6b; }
    * { box-sizing:border-box; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
    body { margin:0; background:linear-gradient(180deg,#0f141a,#0b1016); color:var(--text); }
    .wrap { max-width:1100px; margin:0 auto; padding:16px; }
    .header { background:var(--panel); border-radius:14px; padding:16px; margin-bottom:12px; border:1px solid #263241; }
    .row { display:flex; gap:8px; flex-wrap:wrap; }
    .input { flex:1; min-width:220px; background:#0f141a; color:var(--text); border:1px solid #314154; border-radius:10px; padding:10px; }
    .btn { background:#243447; border:1px solid #3a506a; color:#eaf2fb; border-radius:10px; padding:10px 12px; cursor:pointer; }
    .btn.primary { background:#1f4f78; border-color:#3ea6ff; }
    .btn.warn { background:#5a4416; border-color:#ffbf47; }
    .btn.danger { background:#5f2424; border-color:#ff6b6b; }
    .section { background:var(--panel); border:1px solid #263241; border-radius:14px; padding:12px; margin-bottom:12px; }
    .title { font-size:20px; font-weight:700; margin:0 0 10px 0; }
    .sub { color:var(--muted); font-size:13px; margin-top:2px; }
    .item { padding:10px; border:1px solid #2a3848; border-radius:10px; margin-bottom:8px; background:#121922; }
    .item-top { display:flex; align-items:center; justify-content:space-between; gap:8px; }
    .small { font-size:12px; color:var(--muted); }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }
    .pill { display:inline-block; font-size:11px; padding:3px 8px; border-radius:999px; background:#203445; color:#b9dbff; margin-right:6px; }
    select { background:#0f141a; color:var(--text); border:1px solid #314154; border-radius:8px; padding:6px; }
    .empty { color:var(--muted); font-size:13px; padding:4px 0; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <div class="title">Local Grocery Assistant</div>
      <div class="sub">Single-list app shell with categories, review queue, duplicates, and completed history.</div>
      <div class="row" style="margin-top:10px;">
        <input id="quickAdd" class="input" placeholder="Add item" />
        <button id="addBtn" class="btn primary">Add</button>
      </div>
    </div>
    <div id="attention"></div>
    <div id="lists"></div>
    <div class="section">
      <div class="title">Completed</div>
      <div id="completed"></div>
    </div>
  </div>
  <script>
    let state = null;
    const byId = (id) => document.getElementById(id);
    const esc = (v) => String(v ?? "").replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

    async function api(path, method='GET', body=null){
      const res = await fetch(path, {method, headers: {'Content-Type':'application/json'}, body: body?JSON.stringify(body):null});
      if(!res.ok){ throw new Error(await res.text()); }
      return await res.json();
    }
    async function act(payload){ await api('/api/grocery_learning/action','POST',payload); await load(); }

    function itemRow(item, categories){
      const options = categories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      return `
        <div class="item">
          <div class="item-top">
            <label><input type="checkbox" onchange="window.__g.complete('${esc(item.list_entity)}','${esc(item.item_ref)}',this.checked)" /> <strong>${esc(item.summary)}</strong></label>
            <span class="pill">${esc(item.category_display)}</span>
          </div>
          <div class="small">${esc(item.description || '')}</div>
          <div class="row" style="margin-top:8px;">
            <select id="cat_${esc(item.item_ref)}">${options}</select>
            <button class="btn" onclick="window.__g.move('${esc(item.list_entity)}','${esc(item.item_ref)}')">Move</button>
          </div>
        </div>`;
    }

    function render(){
      if(!state) return;
      const attention = [];
      if(state.pending_duplicate?.pending){
        attention.push(`<div class="section"><div class="title">Duplicate Needs Decision</div>
          <div class="small">${esc(state.pending_duplicate.item)} is already in ${esc(state.pending_duplicate.target)}.</div>
          <div class="row" style="margin-top:8px;">
            <button class="btn warn" onclick="window.__g.confirmDup('add')">Add Anyway</button>
            <button class="btn" onclick="window.__g.confirmDup('skip')">Skip</button>
          </div></div>`);
      }
      if(state.pending_review?.pending){
        const buttons = state.categories.map(c => `<button class="btn" onclick="window.__g.review('${esc(c)}')">${esc(c.replaceAll('_',' '))}</button>`).join('');
        attention.push(`<div class="section"><div class="title">Review Needed</div>
          <div class="small">Item: <strong>${esc(state.pending_review.item)}</strong> (from ${esc(state.pending_review.source_list)})</div>
          <div class="row" style="margin-top:8px;">${buttons}<button class="btn" onclick="window.__g.review('other', false)">Keep Other</button></div></div>`);
      }
      byId('attention').innerHTML = attention.join('');

      const groups = state.groups.map(g => {
        const items = g.items.length ? g.items.map(i => itemRow(i, state.categories)).join('') : `<div class="empty">No items.</div>`;
        return `<div class="section"><div class="title">${esc(g.title)}</div>${items}</div>`;
      }).join('');
      byId('lists').innerHTML = groups;

      byId('completed').innerHTML = state.completed.length
        ? state.completed.map(i => `<div class="item"><label><input type="checkbox" checked onchange="window.__g.undo('${esc(i.item_ref)}',this.checked)" /> <strong>${esc(i.summary)}</strong></label><div class="small">${esc(i.description || '')}</div></div>`).join('')
        : '<div class="empty">No completed items.</div>';
    }

    async function load(){ state = await api('/api/grocery_learning/dashboard'); render(); }

    window.__g = {
      async add(){ const val = byId('quickAdd').value.trim(); if(!val) return; byId('quickAdd').value=''; await act({action:'add_item', item:val}); },
      async complete(listEntity,itemRef,checked){ if(checked) await act({action:'set_status', list_entity:listEntity, item:itemRef, status:'completed'}); },
      async undo(itemRef,checked){ if(!checked) await act({action:'set_status', list_entity:'todo.grocery_completed', item:itemRef, status:'needs_action'}); },
      async move(fromList,itemRef){ const sel = byId('cat_'+itemRef); await act({action:'recategorize', from_list:fromList, item:itemRef, target_category:sel.value, learn:true}); },
      async review(category, learn=true){ await act({action:'apply_review', category, learn}); },
      async confirmDup(decision){ await act({action:'confirm_duplicate', decision}); }
    };

    byId('addBtn').addEventListener('click', () => window.__g.add());
    byId('quickAdd').addEventListener('keydown', (e) => { if(e.key==='Enter'){ e.preventDefault(); window.__g.add(); }});
    load().catch((err) => { byId('lists').innerHTML = `<div class="section"><div class="title">Error</div><div class="small">${esc(err.message)}</div></div>`; });
  </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")


class GroceryLearningDashboardView(HomeAssistantView):
    """Return dashboard payload for custom Grocery app."""

    url = "/api/grocery_learning/dashboard"
    name = "api:grocery_learning:dashboard"
    requires_auth = True

    async def get(self, request):
        builder = self.hass.data.get(DOMAIN, {}).get("build_dashboard_payload")
        if builder is None:
            return self.json({"error": "not_ready"})
        return self.json(await builder())


class GroceryLearningActionView(HomeAssistantView):
    """Handle custom app actions."""

    url = "/api/grocery_learning/action"
    name = "api:grocery_learning:action"
    requires_auth = True

    async def post(self, request):
        handler = self.hass.data.get(DOMAIN, {}).get("handle_dashboard_action")
        if handler is None:
            return self.json({"ok": False, "error": "not_ready"})
        payload = await request.json()
        result = await handler(payload)
        return self.json(result)


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
    data["pending_review"] = {}
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
            friendly_name="Review Pending",
        )
        _set_status_entity(
            REVIEW_STATUS_ITEM_ENTITY,
            item or "none",
            icon="mdi:cart-outline",
            friendly_name="Review Item",
        )
        _set_status_entity(
            REVIEW_STATUS_SOURCE_ENTITY,
            source_list or "none",
            icon="mdi:playlist-check",
            friendly_name="Review Source List",
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
            friendly_name="Duplicate Added By",
        )
        _set_status_entity(
            DUPLICATE_STATUS_WHEN_ENTITY,
            added_when or "unknown",
            icon="mdi:clock-outline",
            friendly_name="Duplicate Added When",
        )
        _set_status_entity(
            DUPLICATE_STATUS_SOURCE_ENTITY,
            source or "unknown",
            icon="mdi:source-branch",
            friendly_name="Duplicate Source",
        )

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

    async def _build_item_description(
        call: ServiceCall,
        source_override: str | None = None,
    ) -> str:
        _, user_name = await _user_name_from_context(call)
        source = _friendly_source(source_override or _source_from_call(call))
        return f"Added by {user_name} · just now · {source}"

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

    async def _list_items(list_entity: str, status: str) -> list[dict[str, Any]]:
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

    async def _build_dashboard_payload() -> dict[str, Any]:
        categories = _active_categories()
        grouped: list[dict[str, Any]] = []
        for category in categories + ["other"]:
            entity_id = _target_list_for_category(category)
            raw_items = await _list_items(entity_id, "needs_action")
            grouped.append(
                {
                    "category": category,
                    "title": _display_name_for_category(category),
                    "items": [
                        {
                            "item_ref": str(item.get("uid", "")).strip() or str(item.get("summary", "")).strip(),
                            "summary": str(item.get("summary", "")).strip(),
                            "description": str(item.get("description", "")).strip(),
                            "list_entity": entity_id,
                            "category": category,
                            "category_display": _display_name_for_category(category),
                        }
                        for item in raw_items
                    ],
                }
            )

        completed_items = await _list_items(COMPLETED_LIST_ENTITY, "completed")
        pending_review = dict(hass.data[DOMAIN].get("pending_review", {}))
        pending_duplicate = dict(hass.data[DOMAIN].get("pending_duplicate", {}))

        return {
            "categories": categories + ["other"],
            "groups": grouped,
            "completed": [
                {
                    "item_ref": str(item.get("uid", "")).strip() or str(item.get("summary", "")).strip(),
                    "summary": str(item.get("summary", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                    "list_entity": COMPLETED_LIST_ENTITY,
                }
                for item in completed_items
            ],
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
        }

    async def _handle_dashboard_action(payload: dict[str, Any]) -> dict[str, Any]:
        action = str(payload.get("action", "")).strip()
        if action == "add_item":
            item = str(payload.get("item", "")).strip()
            if item:
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_ROUTE_ITEM,
                    {"item": item, "review_on_other": True, "source": "typed"},
                    blocking=True,
                )
            return {"ok": True}

        if action == "set_status":
            list_entity = str(payload.get("list_entity", "")).strip()
            item_ref = str(payload.get("item", "")).strip()
            status = str(payload.get("status", "")).strip().lower()
            if list_entity and item_ref and status in {"completed", "needs_action"}:
                await hass.services.async_call(
                    "todo",
                    "update_item",
                    {"item": item_ref, "status": status},
                    target={"entity_id": list_entity},
                    blocking=True,
                )
            return {"ok": True}

        if action == "recategorize":
            from_list = str(payload.get("from_list", "")).strip()
            item_ref = str(payload.get("item", "")).strip()
            target_category = _normalize_category(str(payload.get("target_category", "")).strip())
            learn = bool(payload.get("learn", True))
            categories = _active_categories()
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

        if action == "apply_review":
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
            await hass.services.async_call(
                DOMAIN,
                SERVICE_CONFIRM_DUPLICATE,
                {"decision": decision if decision in {"add", "skip"} else "skip"},
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
        await _ensure_local_todo_list(COMPLETED_LIST_ENTITY, "Grocery Completed")

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
            "Grocery Review Pending",
            {"name": "Grocery Review Pending", "icon": "mdi:clipboard-text-clock-outline"},
        )
        await _ensure_helper_entity(
            "input_text",
            REVIEW_ITEM_HELPER,
            "Grocery Review Item",
            {"name": "Grocery Review Item", "max": 255, "icon": "mdi:cart"},
        )
        await _ensure_helper_entity(
            "input_text",
            REVIEW_SOURCE_HELPER,
            "Grocery Review Source List",
            {"name": "Grocery Review Source List", "max": 255, "icon": "mdi:playlist-check"},
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
            "Apply Grocery Review",
            {"name": "Apply Grocery Review", "icon": "mdi:check-bold"},
        )

        await _ensure_helper_entity(
            "input_boolean",
            DUPLICATE_PENDING_HELPER,
            "Grocery Duplicate Pending",
            {"name": "Grocery Duplicate Pending", "icon": "mdi:content-duplicate"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_ITEM_HELPER,
            "Grocery Duplicate Item",
            {"name": "Grocery Duplicate Item", "max": 255, "icon": "mdi:cart-outline"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_TARGET_HELPER,
            "Grocery Duplicate Target List",
            {"name": "Grocery Duplicate Target List", "max": 255, "icon": "mdi:format-list-bulleted"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_KEY_HELPER,
            "Grocery Duplicate Key",
            {"name": "Grocery Duplicate Key", "max": 255, "icon": "mdi:key-variant"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_BY_HELPER,
            "Grocery Duplicate Added By",
            {"name": "Grocery Duplicate Added By", "max": 255, "icon": "mdi:account"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_WHEN_HELPER,
            "Grocery Duplicate Added When",
            {"name": "Grocery Duplicate Added When", "max": 255, "icon": "mdi:clock-outline"},
        )
        await _ensure_helper_entity(
            "input_text",
            DUPLICATE_PENDING_SOURCE_HELPER,
            "Grocery Duplicate Source",
            {"name": "Grocery Duplicate Source", "max": 255, "icon": "mdi:source-branch"},
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
                "hide_completed": True,
                "hide_create": True,
                "hide_section_headers": True,
            },
        }

    def _build_main_dashboard_config(entry: ConfigEntry | None) -> dict[str, Any]:
        return {
            "config": {
                "title": "Grocery",
                "views": [
                    {
                        "title": "Grocery",
                        "path": "grocery",
                        "icon": "mdi:cart-variant",
                        "type": "masonry",
                        "cards": [
                            {
                                "type": "iframe",
                                "url": "/api/grocery_learning/app",
                                "aspect_ratio": "56%",
                                "title": "Grocery App",
                            }
                        ],
                    }
                ],
            }
        }

    def _build_admin_dashboard_config() -> dict[str, Any]:
        return {
            "config": {
                "title": "Grocery Admin",
                "views": [
                    {
                        "title": "Grocery Admin",
                        "path": "grocery-admin",
                        "icon": "mdi:shield-crown",
                        "type": "masonry",
                        "cards": [
                            {
                                "type": "iframe",
                                "url": "/api/grocery_learning/app?mode=admin",
                                "aspect_ratio": "56%",
                                "title": "Grocery Admin App",
                            }
                        ],
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
            {"item": raw_item, "description": await _build_item_description(call)},
            target={"entity_id": target_list},
            blocking=True,
        )
        await _record_item_meta(target_list, raw_item, call)

        if remove_from_source:
            await _remove_from_list(source_list, raw_item)

        if category == "other" and review_on_other:
            await _set_pending_review(raw_item, target_list)
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

        pending_review = dict(hass.data[DOMAIN].get("pending_review", {}))
        review_item_state = hass.states.get(REVIEW_ITEM_HELPER)
        source_list_state = hass.states.get(REVIEW_SOURCE_HELPER)
        review_item = str(review_item_state.state).strip() if review_item_state else ""
        source_list = str(source_list_state.state).strip() if source_list_state else ""
        if not review_item:
            review_item = str(pending_review.get("item", "")).strip()
        if not source_list:
            source_list = str(pending_review.get("source_list", "")).strip()
        if not source_list:
            source_list = _target_list_for_category("other")
        if not review_item:
            candidate = await _first_open_item(source_list)
            if candidate:
                review_item = str(candidate.get("summary", "")).strip()
        if not review_item and source_list != _target_list_for_category("other"):
            candidate = await _first_open_item(_target_list_for_category("other"))
            if candidate:
                review_item = str(candidate.get("summary", "")).strip()
                source_list = _target_list_for_category("other")
        target_list = _target_list_for_category(target_category)
        if not review_item:
            return

        if source_list != target_list:
            await _remove_from_list(source_list, review_item)
            await hass.services.async_call(
                "todo",
                "add_item",
                {"item": review_item, "description": await _build_item_description(call)},
                target={"entity_id": target_list},
                blocking=True,
            )
            await _record_item_meta(target_list, review_item, call, source_override="review_move")

        if learn and target_category in categories:
            norm = _normalize_term(review_item)
            terms_obj: LearnedTerms = hass.data[DOMAIN]["terms"]
            existing = set(terms_obj.data.get(target_category, []))
            if norm and norm not in existing:
                terms_obj.data.setdefault(target_category, []).append(norm)
                await _save()
                await _sync_helpers_internal()

        await _clear_pending_review()
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
                {"item": item, "description": await _build_item_description(call, source_override="duplicate_confirmation")},
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

    _update_review_status_entities(pending=False)
    _update_duplicate_status_entities(pending=False)

    if not data.get("views_registered"):
        hass.http.register_view(GroceryLearningAppView())
        hass.http.register_view(GroceryLearningDashboardView())
        hass.http.register_view(GroceryLearningActionView())
        data["views_registered"] = True

    data["build_dashboard_payload"] = _build_dashboard_payload
    data["handle_dashboard_action"] = _handle_dashboard_action
    data["ensure_required_lists"] = _ensure_required_lists
    data["ensure_required_helpers"] = _ensure_required_helpers
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

    ensure_required_helpers = hass.data[DOMAIN].get("ensure_required_helpers")
    if ensure_required_helpers:
        await ensure_required_helpers()

    ensure_dashboards = data.get("ensure_dashboards")
    if ensure_dashboards:
        await ensure_dashboards(entry)

    internal_context_ids: set[str] = data.setdefault("internal_context_ids", set())

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

    async def _handle_call_service(event) -> None:
        if event.context and event.context.id in internal_context_ids:
            internal_context_ids.discard(event.context.id)
            return

        data_event = event.data.get("service_data", {})
        if event.data.get("domain") != "todo":
            return

        service_name = str(event.data.get("service", "")).strip()
        list_id = _extract_entity_id(event.data, data_event)
        if not list_id:
            return
        inbox_entity = _entry_value(entry, CONF_INBOX_ENTITY, "todo.grocery_inbox")
        category_lists = [_target_list_for_category(category) for category in data.get("categories", list(DEFAULT_CATEGORIES))]
        tracked_lists = category_lists + [_target_list_for_category("other")]

        if service_name == "add_item":
            if not _entry_value(entry, CONF_AUTO_ROUTE_INBOX, True):
                return
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
            return

        if service_name != "update_item":
            return

        item_ref = str(data_event.get("item", "")).strip()
        status = str(data_event.get("status", "")).strip().lower()
        if not item_ref:
            return

        if list_id in tracked_lists and status == "completed":
            await _move_checked_item_to_completed(list_id, item_ref)
            return

        if list_id == COMPLETED_LIST_ENTITY and status == "needs_action":
            await _restore_unchecked_item_from_completed(item_ref)
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
