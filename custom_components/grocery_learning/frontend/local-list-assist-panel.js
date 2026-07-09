import { LitElement, html, css, nothing } from "./vendor/lit.js";
import { repeat } from "./vendor/lit.js";
import { live } from "./vendor/lit.js";
import { styleMap } from "./vendor/lit.js";
import {
  categoryDisplay as displayCategory,
  createListLocal as applyCreateListLocal,
  deleteArchivedListLocal as applyDeleteArchivedListLocal,
  groupTitle as deriveGroupTitle,
  moveItemToCompleted as applyMoveItemToCompleted,
  switchListLocal as applySwitchListLocal,
  updateItemLocal as applyUpdateItemLocal,
} from "./state-helpers.js";

const TEMPLATE_LABELS = {
  flat: "Flat List",
  grocery: "Grocery",
  todo: "To-do",
  camping: "Camping",
  travel: "Travel",
};

const LIVE_REVISION_ENTITY_ID = "sensor.local_list_assist_live_revision";
const UNDO_TIMEOUT_MS = 6000;

class LocalListAssistPanel extends LitElement {
  static properties = {
    _state: { state: true },
    _error: { state: true },
    _loading: { state: true },
    _view: { state: true },
    _narrow: { state: true },
    _configOpen: { state: true },
    _createListOpen: { state: true },
    _listSettingsOpen: { state: true },
    _menuOpen: { state: true },
    _reorderListId: { state: true },
    _appToolsOpen: { state: true },
    _listToolsOpen: { state: true },
    _openEditorKey: { state: true },
    _undo: { state: true },
    _dragListId: { state: true },
    _dragOverListId: { state: true },
    _draggingItemRef: { state: true },
    _dragOverItemRef: { state: true },
  };

  constructor() {
    super();
    this._hass = null;
    this._panel = null;
    this._state = null;
    this._error = "";
    this._loading = false;
    this._view = "list";
    this._narrow = false;
    this._configOpen = false;
    this._createListOpen = false;
    this._listSettingsOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
    this._appToolsOpen = false;
    this._listToolsOpen = false;
    this._openEditorKey = "";
    this._undo = null;
    this._dragListId = "";
    this._dragOverListId = "";
    this._dragItemRef = "";
    this._dragItemCategory = "";
    this._draggingItemRef = "";
    this._dragOverItemRef = "";
    this._undoTimer = null;
    this._chipLongPressTimer = null;
    this._suppressNextChipClick = "";
    this._categoryRenameDrafts = { activeListCategories: {} };
    this._drafts = {
      quickAdd: "",
      quickAddQty: "1",
      dashboardName: "",
      settingsCategories: "",
      newListName: "",
      newListTemplate: "flat",
      newListCategories: "",
      newListVoiceAliases: "",
      activeListName: "",
      activeListCategories: "",
      activeListVoiceAliases: "",
      activeListColor: "",
    };
    this._lastSeenLiveRevision = "";
    this._wsUnsub = null;
    this._wsActive = false;
    this._wsSubscribing = false;
    this._disconnected = false;
  }

  // --- Home Assistant provided properties ---
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._lastSeenLiveRevision = this.currentLiveRevision();
      this.subscribeLiveUpdates();
      this.load();
    } else if (!this._wsActive) {
      // Fallback path: diff the revision sensor when the WebSocket push isn't active.
      const nextRevision = this.currentLiveRevision();
      if (nextRevision && nextRevision !== this._lastSeenLiveRevision) {
        this._lastSeenLiveRevision = nextRevision;
        this.load(true);
      }
    }
  }

  get hass() {
    return this._hass;
  }

  set panel(panel) {
    this._panel = panel;
    this.requestUpdate();
  }

  set narrow(narrow) {
    this._narrow = !!narrow;
  }

  connectedCallback() {
    super.connectedCallback();
    this._disconnected = false;
    if (this._hass && !this._wsUnsub) {
      this.subscribeLiveUpdates();
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._disconnected = true;
    if (this._wsUnsub) {
      try {
        this._wsUnsub();
      } catch (_err) {
        // ignore teardown errors
      }
      this._wsUnsub = null;
    }
    this._wsActive = false;
    if (this._undoTimer) {
      window.clearTimeout(this._undoTimer);
      this._undoTimer = null;
    }
  }

  // --- live updates ---
  async subscribeLiveUpdates() {
    if (this._wsUnsub || this._wsSubscribing || !this._hass?.connection?.subscribeMessage) {
      return;
    }
    this._wsSubscribing = true;
    try {
      const unsub = await this._hass.connection.subscribeMessage(
        (event) => this.onLiveUpdate(event),
        { type: "grocery_learning/subscribe_updates" }
      );
      if (this._disconnected) {
        try { unsub(); } catch (_e) {}
        return;
      }
      this._wsUnsub = unsub;
      this._wsActive = true;
    } catch (_err) {
      this._wsActive = false;
      this._wsUnsub = null;
    } finally {
      this._wsSubscribing = false;
    }
  }

  onLiveUpdate(event) {
    const revision = String(event?.revision ?? "");
    if (!revision || revision === this._lastSeenLiveRevision) {
      return;
    }
    this._lastSeenLiveRevision = revision;
    // Scoped updates: if the change was to a different list than the one this
    // panel is showing, there's nothing to refresh here. "*" means broadcast
    // (structural/list changes, or an action whose list is ambiguous).
    const changed = String(event?.list_id ?? "*");
    if (changed && changed !== "*" && changed !== this.currentListId()) {
      return;
    }
    // Keyed rendering + draft-backed inputs preserve focus and in-progress
    // edits across a reload, so we can refresh immediately.
    this.load(true);
  }

  currentLiveRevision() {
    return String(this._hass?.states?.[LIVE_REVISION_ENTITY_ID]?.state || "");
  }

  rememberRevisionFromState() {
    const revision = this._state?.revision;
    this._lastSeenLiveRevision = revision != null ? String(revision) : this.currentLiveRevision();
  }

  // --- persisted per-user active list ---
  storageKey() {
    const userId = this._hass?.user?.id || "anonymous";
    return `lla:active-list:${userId}`;
  }

  getPreferredListId() {
    try {
      return window.localStorage.getItem(this.storageKey()) || "default";
    } catch (_err) {
      return "default";
    }
  }

  setPreferredListId(listId) {
    const nextListId = String(listId || "").trim() || "default";
    try {
      window.localStorage.setItem(this.storageKey(), nextListId);
    } catch (_err) {
      // ignore storage failures
    }
  }

  currentListId() {
    return this._state?.system?.active_list_id || this.getPreferredListId() || "default";
  }

  // --- API ---
  get _token() {
    return (
      this._hass?.auth?.data?.accessToken ||
      this._hass?.connection?.options?.auth?.accessToken ||
      ""
    );
  }

  _headers() {
    const headers = { "Content-Type": "application/json" };
    if (this._token) {
      headers.Authorization = `Bearer ${this._token}`;
    }
    return headers;
  }

  async api(path, method = "GET", body = null) {
    const res = await fetch(`/api/grocery_learning/${path}`, {
      method,
      headers: this._headers(),
      body: body ? JSON.stringify(body) : null,
      credentials: "same-origin",
    });
    const text = await res.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_err) {
      data = { error: text || `HTTP ${res.status}` };
    }
    if (!res.ok) {
      throw new Error(data.error || text || `HTTP ${res.status}`);
    }
    return data;
  }

  async load(_forceRender = false) {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    try {
      const requestedListId = this.getPreferredListId() || "default";
      const state = await this.api(`dashboard?list_id=${encodeURIComponent(requestedListId)}`);
      this._state = state;
      this.setPreferredListId(state?.system?.active_list_id || requestedListId);
      this.syncDrafts();
      this._error = state?.error || "";
      this.rememberRevisionFromState();
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._loading = false;
      this.requestUpdate();
    }
  }

  _applyResult(result, payload) {
    if (result?.dashboard && typeof result.dashboard === "object") {
      this._state = result.dashboard;
      this.setPreferredListId(this._state?.system?.active_list_id || payload?.list_id || "default");
      this.syncDrafts();
      this._error = this._state?.error || "";
      this.rememberRevisionFromState();
      this.requestUpdate();
      return true;
    }
    return false;
  }

  async act(payload) {
    try {
      const result = await this.api("action", "POST", payload);
      if (this._applyResult(result, payload)) {
        return result;
      }
      await this.load(true);
      return result;
    } catch (err) {
      this._error = err.message || String(err);
      this.requestUpdate();
      return null;
    }
  }

  async actFast(payload, updater = null) {
    if (typeof updater === "function" && this._state) {
      updater(this._state);
      this.syncDrafts();
      this.requestUpdate();
    }
    try {
      const result = await this.api("action", "POST", payload);
      this._applyResult(result, payload);
      return result;
    } catch (err) {
      // Reconcile with the server on failure.
      await this.load(true);
      return null;
    }
  }

  // --- drafts ---
  syncDrafts() {
    const state = this._state;
    const active = state?.lists?.find((list) => list.active) || null;
    const activeId = active?.id || "";
    if (this._drafts.activeListId !== activeId) {
      this._drafts.activeListId = activeId;
      this._drafts.activeListName = active?.name || "";
      this._drafts.activeListCategories = (state?.system?.active_list_categories || []).join(", ");
      this._drafts.activeListVoiceAliases = (state?.system?.active_list_voice_aliases || []).join(", ");
      this._drafts.activeListColor = state?.system?.active_list_color || active?.color || "#2c78ba";
      this._categoryRenameDrafts.activeListCategories = {};
    }
    if (!this._drafts.settingsCategories) {
      this._drafts.settingsCategories = (state?.settings?.categories || []).join(", ");
    }
    if (!this._drafts.dashboardName) {
      this._drafts.dashboardName = state?.settings?.dashboard_name || "Local List Assist";
    }
  }

  updateDraft(key, value) {
    this._drafts[key] = value;
  }

  editorKey(item) {
    return `${item.list_entity || ""}::${item.item_ref || ""}`;
  }

  categoryDisplay(category) {
    return displayCategory(category, this._state?.categories || []);
  }

  groupTitle(category) {
    return deriveGroupTitle(this._state, category);
  }

  // --- category draft editing ---
  parseCategoryDraft(key) {
    return String(this._drafts[key] || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }

  writeCategoryDraft(key, categories) {
    this._drafts[key] = categories.join(", ");
  }

  addCategoryDraft(key, value) {
    const next = String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (!next) return false;
    const current = this.parseCategoryDraft(key);
    if (current.includes(next)) return false;
    current.push(next);
    this.writeCategoryDraft(key, current);
    return true;
  }

  moveCategoryDraft(key, index, direction) {
    const current = this.parseCategoryDraft(key);
    const target = index + direction;
    if (target < 0 || target >= current.length) return;
    const [entry] = current.splice(index, 1);
    current.splice(target, 0, entry);
    this.writeCategoryDraft(key, current);
  }

  removeCategoryDraft(key, index) {
    const current = this.parseCategoryDraft(key);
    current.splice(index, 1);
    this.writeCategoryDraft(key, current);
  }

  renameCategoryDraft(key, index, value) {
    const next = String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (!next) return false;
    const current = this.parseCategoryDraft(key);
    const previous = current[index];
    if (!previous) return false;
    if (current.some((category, categoryIndex) => categoryIndex !== index && category === next)) {
      return false;
    }
    current[index] = next;
    this.writeCategoryDraft(key, current);
    if (key === "activeListCategories") {
      const renameMap = { ...(this._categoryRenameDrafts.activeListCategories || {}) };
      const originalCategories = new Set((this._state?.system?.active_list_categories || []).filter(Boolean));
      let originalKey = previous;
      Object.entries(renameMap).forEach(([source, target]) => {
        if (target === previous) {
          originalKey = source;
          delete renameMap[source];
        }
      });
      if (originalCategories.has(originalKey) && originalKey !== next) {
        renameMap[originalKey] = next;
      }
      this._categoryRenameDrafts.activeListCategories = renameMap;
    }
    return true;
  }

  // --- panel/overlay helpers ---
  closePanels() {
    this._configOpen = false;
    this._createListOpen = false;
    this._listSettingsOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
    this._appToolsOpen = false;
    this._listToolsOpen = false;
  }

  openNavigation() {
    const toggleEvent = new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true });
    this.dispatchEvent(toggleEvent);
    window.dispatchEvent(toggleEvent);
    const homeAssistant = document.querySelector("home-assistant");
    const main = homeAssistant?.shadowRoot?.querySelector("home-assistant-main");
    if (main && typeof main._toggleSidebar === "function") {
      main._toggleSidebar();
      return;
    }
    if (window.history.length > 1) {
      window.history.back();
    }
  }

  clearChipLongPress() {
    if (this._chipLongPressTimer) {
      window.clearTimeout(this._chipLongPressTimer);
      this._chipLongPressTimer = null;
    }
  }

  openReorderPanel(listId) {
    this._reorderListId = listId || "";
    this._listSettingsOpen = false;
    this._configOpen = false;
    this._createListOpen = false;
    this._menuOpen = false;
  }

  // --- undo ---
  showUndo(label, undoFn) {
    if (this._undoTimer) {
      window.clearTimeout(this._undoTimer);
    }
    this._undo = { label, undoFn };
    this._undoTimer = window.setTimeout(() => {
      this._undo = null;
      this._undoTimer = null;
    }, UNDO_TIMEOUT_MS);
  }

  async runUndo() {
    const undo = this._undo;
    this._undo = null;
    if (this._undoTimer) {
      window.clearTimeout(this._undoTimer);
      this._undoTimer = null;
    }
    if (undo && typeof undo.undoFn === "function") {
      await undo.undoFn();
    }
  }

  // --- optimistic local mutations ---
  moveItemToCompleted(itemRef) {
    applyMoveItemToCompleted(this._state, itemRef);
  }

  updateItemLocal(itemRef, summary, targetCategory, quantity) {
    applyUpdateItemLocal(this._state, itemRef, { summary, targetCategory, quantity });
  }

  switchListLocal(listId) {
    return applySwitchListLocal(this._state, listId);
  }

  // --- actions ---
  async addItem() {
    const item = (this._drafts.quickAdd || "").trim();
    const quantity = Math.max(1, Number.parseInt(this._drafts.quickAddQty || "1", 10) || 1);
    if (!item) return;
    this._drafts.quickAdd = "";
    this._drafts.quickAddQty = "1";
    this.requestUpdate();
    await this.act({
      action: "add_item",
      item,
      quantity,
      list_id: this.currentListId(),
      actor_user_id: this._hass?.user?.id || "",
      actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
    });
    // Keep focus in the quick-add box for rapid entry.
    this.updateComplete.then(() => {
      const el = this.renderRoot?.getElementById("quickAdd");
      if (el) el.focus();
    });
  }

  toggleEditor(item) {
    const key = this.editorKey(item);
    if (this._openEditorKey === key) {
      this._openEditorKey = "";
      return;
    }
    this._drafts[`summary:${key}`] = item.summary ?? "";
    this._drafts[`quantity:${key}`] = String(item.quantity || 1);
    this._drafts[`category:${key}`] = item.category || "";
    this._openEditorKey = key;
    this.updateComplete.then(() => {
      const el = this.renderRoot?.getElementById(`summary-${key}`);
      if (el) el.focus();
    });
  }

  async completeItem(item) {
    const key = this.editorKey(item);
    if (this._openEditorKey === key) this._openEditorKey = "";
    const listEntity = item.list_entity;
    const itemRef = item.item_ref;
    const listId = this.currentListId();
    await this.actFast(
      { action: "set_status", list_entity: listEntity, list_id: listId, item: itemRef, status: "completed" },
      () => this.moveItemToCompleted(itemRef)
    );
    this.showUndo(`Completed ${item.summary}`, async () => {
      await this.act({
        action: "set_status",
        list_entity: "todo.grocery_completed",
        list_id: listId,
        item: itemRef,
        status: "needs_action",
      });
    });
  }

  async saveItem(item) {
    const key = this.editorKey(item);
    const nextSummary = (this._drafts[`summary:${key}`] || "").trim();
    const nextQuantity = Math.max(1, Number.parseInt(this._drafts[`quantity:${key}`] || "1", 10) || 1);
    const target = this._drafts[`category:${key}`] || item.category || "";
    if (!target || !nextSummary) return;
    this._openEditorKey = "";
    await this.actFast(
      {
        action: "update_item",
        list_entity: item.list_entity,
        list_id: this.currentListId(),
        item: item.item_ref,
        summary: nextSummary,
        quantity: nextQuantity,
        target_category: target,
        learn: true,
      },
      () => this.updateItemLocal(item.item_ref, nextSummary, target, nextQuantity)
    );
  }

  async restoreCompleted(item) {
    await this.act({
      action: "set_status",
      list_entity: "todo.grocery_completed",
      list_id: this.currentListId(),
      item: item.item_ref,
      status: "needs_action",
    });
  }

  async saveCompletedItem(item) {
    const key = this.editorKey(item);
    const nextSummary = (this._drafts[`summary:${key}`] || "").trim();
    const nextQuantity = Math.max(1, Number.parseInt(this._drafts[`quantity:${key}`] || "1", 10) || 1);
    if (!nextSummary) return;
    this._openEditorKey = "";
    await this.actFast(
      {
        action: "update_item",
        list_entity: item.list_entity,
        list_id: this.currentListId(),
        item: item.item_ref,
        summary: nextSummary,
        quantity: nextQuantity,
      },
      () => this.updateItemLocal(item.item_ref, nextSummary, "", nextQuantity)
    );
  }

  async clearCompleted() {
    await this.actFast({ action: "clear_completed", list_id: this.currentListId() }, (state) => {
      state.completed = [];
    });
  }

  async switchList(listId) {
    this.setPreferredListId(listId);
    await this.actFast({ action: "switch_list", list_id: listId }, () => this.switchListLocal(listId));
  }

  async createList() {
    const name = (this._drafts.newListName || "").trim();
    if (!name) return;
    const template = this._drafts.newListTemplate || "flat";
    const categories = this._drafts.newListCategories || "";
    const voiceAliases = this._drafts.newListVoiceAliases || "";
    const listId = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "list";
    const nextColor = "#" + ((Array.from(listId).reduce((sum, char) => sum + char.charCodeAt(0), 0) % 0xffffff).toString(16).padStart(6, "0"));
    await this.actFast(
      { action: "create_list", name, template, categories, voice_aliases: voiceAliases },
      (state) => applyCreateListLocal(state, { id: listId, name, color: nextColor })
    );
    this._drafts.newListName = "";
    this._drafts.newListTemplate = "flat";
    this._drafts.newListCategories = "";
    this._drafts.newListVoiceAliases = "";
    this.closePanels();
  }

  async saveActiveList() {
    const listId = this.currentListId();
    if (!listId) return;
    await this.act({
      action: "save_active_list",
      list_id: listId,
      name: (this._drafts.activeListName || "").trim(),
      categories: this._drafts.activeListCategories || "",
      renamed_categories: this._categoryRenameDrafts.activeListCategories || {},
      voice_aliases: this._drafts.activeListVoiceAliases || "",
      color: this._drafts.activeListColor || "#2c78ba",
    });
    this._categoryRenameDrafts.activeListCategories = {};
    this.closePanels();
  }

  async saveSettings() {
    const nextDashboardName = (this._drafts.dashboardName || "Local List Assist").trim() || "Local List Assist";
    const previousDashboardName = this._state?.settings?.dashboard_name || "Local List Assist";
    await this.act({
      action: "save_settings",
      dashboard_name: nextDashboardName,
      categories: this._drafts.settingsCategories || "",
      default_grocery_categories: !!this.renderRoot?.getElementById("settingsDefaultGroceryCategories")?.checked,
      debug_mode: !!this.renderRoot?.getElementById("settingsDebugMode")?.checked,
    });
    if (this._panel) {
      this._panel = { ...this._panel, title: nextDashboardName, config: { ...(this._panel.config || {}), title: nextDashboardName } };
    }
    document.title = nextDashboardName;
    this.closePanels();
    if (nextDashboardName !== previousDashboardName) {
      window.setTimeout(() => window.location.reload(), 450);
    }
  }

  async reorderList(direction) {
    const listId = this.currentListId();
    if (!listId || listId === "default") return;
    await this.act({ action: "reorder_list", list_id: listId, direction });
  }

  // --- drag and drop list reorder ---
  onChipDragStart(listId, ev) {
    this._dragListId = listId;
    if (ev.dataTransfer) {
      ev.dataTransfer.effectAllowed = "move";
      try { ev.dataTransfer.setData("text/plain", listId); } catch (_e) {}
      const chip = ev.currentTarget;
      if (chip && typeof ev.dataTransfer.setDragImage === "function") {
        const rect = chip.getBoundingClientRect();
        try { ev.dataTransfer.setDragImage(chip, ev.clientX - rect.left, ev.clientY - rect.top); } catch (_e) {}
      }
    }
  }

  onChipDragEnd() {
    this._dragListId = "";
    this._dragOverListId = "";
  }

  onChipDragOver(listId, ev) {
    if (this._dragListId) {
      ev.preventDefault();
      if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
      if (listId !== this._dragListId && this._dragOverListId !== listId) {
        this._dragOverListId = listId;
      }
    }
  }

  async onChipDrop(targetListId, ev) {
    ev.preventDefault();
    const dragged = this._dragListId;
    this._dragListId = "";
    this._dragOverListId = "";
    if (!dragged || dragged === targetListId) return;
    const order = (this._state?.lists || []).map((list) => list.id);
    const from = order.indexOf(dragged);
    const to = order.indexOf(targetListId);
    if (from < 0 || to < 0) return;
    order.splice(from, 1);
    order.splice(to, 0, dragged);
    await this.act({ action: "set_list_order", order });
  }

  // --- drag and drop item reorder (within a category) ---
  _groupFor(category) {
    return (this._state?.groups || []).find((group) => group.category === category) || null;
  }

  onItemDragStart(item, ev) {
    this._dragItemRef = item.item_ref;
    this._dragItemCategory = item.category;
    this._draggingItemRef = item.item_ref;
    if (ev.dataTransfer) {
      ev.dataTransfer.effectAllowed = "move";
      try { ev.dataTransfer.setData("text/plain", item.item_ref); } catch (_e) {}
      // Float the whole row under the cursor instead of just the grab handle,
      // so the drag is clearly visible.
      const row = ev.currentTarget?.closest?.(".item");
      if (row && typeof ev.dataTransfer.setDragImage === "function") {
        const rect = row.getBoundingClientRect();
        try { ev.dataTransfer.setDragImage(row, ev.clientX - rect.left, ev.clientY - rect.top); } catch (_e) {}
      }
    }
  }

  onItemDragEnd() {
    this._dragItemRef = "";
    this._dragItemCategory = "";
    this._draggingItemRef = "";
    this._dragOverItemRef = "";
  }

  onItemDragOver(item, ev) {
    // Only allow dropping onto another active item in the same category.
    if (this._dragItemRef && this._dragItemCategory === item.category) {
      ev.preventDefault();
      if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
      if (item.item_ref !== this._dragItemRef && this._dragOverItemRef !== item.item_ref) {
        this._dragOverItemRef = item.item_ref;
      }
    }
  }

  async onItemDrop(targetItem, ev) {
    ev.preventDefault();
    const draggedRef = this._dragItemRef;
    const category = this._dragItemCategory;
    this._dragItemRef = "";
    this._dragItemCategory = "";
    this._draggingItemRef = "";
    this._dragOverItemRef = "";
    if (!draggedRef || draggedRef === targetItem.item_ref || category !== targetItem.category) {
      return;
    }
    const group = this._groupFor(category);
    if (!group) return;
    const refs = (group.items || []).map((it) => it.item_ref);
    const from = refs.indexOf(draggedRef);
    const to = refs.indexOf(targetItem.item_ref);
    if (from < 0 || to < 0) return;
    refs.splice(from, 1);
    refs.splice(to, 0, draggedRef);
    await this.actFast(
      { action: "set_item_order", list_id: this.currentListId(), category, order: refs },
      (state) => {
        const g = (state.groups || []).find((grp) => grp.category === category);
        if (!g) return;
        const byRef = new Map((g.items || []).map((it) => [it.item_ref, it]));
        g.items = refs.map((ref) => byRef.get(ref)).filter(Boolean);
      }
    );
  }

  // --- templates ---
  render() {
    const state = this._state;
    if (!state && this._loading) {
      return html`<div class="wrap"><section class="hero"><div class="empty">Loading…</div></section></div>`;
    }
    const multilist = !!state?.settings?.experimental_multilist;
    const dashboardName = state?.settings?.dashboard_name || "Local List Assist";
    const active = state?.lists?.find((list) => list.active) || null;
    const activeListName = active?.name || "Grocery List";
    const activeListColor = state?.system?.active_list_color || active?.color || "#2c78ba";
    const visibleGroups = (state?.groups || []).filter((group) => (group.items || []).length > 0);

    if (this._view === "shopping" && state) {
      return this._shoppingTemplate(state, activeListName, activeListColor, visibleGroups);
    }

    return html`
      <div class="wrap" style=${styleMap({ "--accent": activeListColor })} @keydown=${(e) => this._onKeyDown(e)}>
        ${this._narrow
          ? html`<div class="mobile-bar">
              <button id="menuBtn" class="btn icon-btn" aria-label="Open navigation" @click=${() => this.openNavigation()}>☰</button>
              <div class="mobile-title">${dashboardName}</div>
            </div>`
          : nothing}
        <section class="hero">
          <div class="hero-head">
            <div>
              <div class="hero-title">${dashboardName}</div>
              <div class="sub">Local-only Home Assistant workspace. Current list: ${activeListName}.</div>
            </div>
            <div class="hero-actions">
              <button class="btn icon-btn compact shop-btn" aria-label="Shopping mode" title="Shopping mode" @click=${() => this.enterShopping()}>🛒</button>
              <button class="btn icon-btn compact" aria-label="Create list" title="Create list" @click=${() => this.openCreateList()}>+</button>
              <button class="btn icon-btn compact" aria-label="Open menu" title="Menu" @click=${() => { this._menuOpen = !this._menuOpen; }}>⋯</button>
              <button class="btn icon-btn compact" aria-label="Refresh list data" title="Refresh" @click=${() => this.load(true)}>⟳</button>
            </div>
          </div>
          ${multilist
            ? html`<div class="list-chip-row">${this._listChips(state)}</div>
                <div class="small">Tap the active list to manage it. Drag a chip to reorder, or long-press / right-click for reorder controls.</div>`
            : nothing}
          <div class="row quick-add-row">
            <input id="quickAdd" class="input" placeholder="Add item" .value=${live(this._drafts.quickAdd || "")}
              @input=${(e) => this.updateDraft("quickAdd", e.target.value)}
              @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.addItem(); } }} />
            <input id="quickAddQty" class="input qty-input" type="number" min="1" step="1" inputmode="numeric" placeholder="Qty"
              .value=${live(this._drafts.quickAddQty || "1")}
              @input=${(e) => this.updateDraft("quickAddQty", e.target.value)} />
            <button class="btn primary" @click=${() => this.addItem()}>Add</button>
          </div>
        </section>

        ${this._menuOpen ? this._menuTemplate(multilist) : nothing}
        ${this._configOpen ? this._appSettingsTemplate(state) : nothing}
        ${this._createListOpen && multilist ? this._createListTemplate(state) : nothing}
        ${this._listSettingsOpen && multilist ? this._listSettingsTemplate(state, activeListName, activeListColor) : nothing}
        ${this._reorderListId && multilist ? this._reorderTemplate(state) : nothing}

        ${this._error ? html`<section class="section"><div class="title">Error</div><div class="error">${this._error}</div></section>` : nothing}
        ${this._attentionTemplates(state)}

        ${this._view === "list"
          ? html`
              ${visibleGroups.length
                ? visibleGroups.map((group) => html`
                    <section class="section">
                      <div class="title">${group.title}</div>
                      ${repeat(group.items, (item) => item.item_ref, (item) => this._itemTemplate(item, state.categories || []))}
                    </section>`)
                : html`<section class="section"><div class="title">${activeListName}</div><div class="empty">No items in this list yet.</div></section>`}
              <section class="section">
                <div class="title">Completed</div>
                <div class="row" style="justify-content:space-between;">
                  <div class="small">Completed history stays visible until cleared.</div>
                  <button class="btn danger" @click=${() => this.clearCompleted()}>Clear Completed</button>
                </div>
                <div style="margin-top:10px;">
                  ${(state?.completed || []).length
                    ? repeat(state.completed, (item) => item.item_ref, (item) => this._completedItemTemplate(item))
                    : html`<div class="empty">No completed items.</div>`}
                </div>
              </section>`
          : html`<section class="section"><div class="title">Recent Activity</div>${this._activityTemplate(state)}</section>`}
      </div>
      ${this._undo ? html`
        <div class="undo-toast">
          <span>${this._undo.label}</span>
          <button class="btn" @click=${() => this.runUndo()}>Undo</button>
        </div>` : nothing}
    `;
  }

  _listChips(state) {
    return (state?.lists || []).map((list) => html`
      <button
        class=${"list-chip" + (list.active ? " active" : "") + (this._dragListId === list.id ? " dragging" : "") + (this._dragOverListId === list.id ? " drag-over" : "")}
        style=${styleMap({ "--chip-color": list.color || "#2c78ba" })}
        draggable="true"
        @dragstart=${(e) => this.onChipDragStart(list.id, e)}
        @dragover=${(e) => this.onChipDragOver(list.id, e)}
        @dragleave=${() => { if (this._dragOverListId === list.id) this._dragOverListId = ""; }}
        @dragend=${() => this.onChipDragEnd()}
        @drop=${(e) => this.onChipDrop(list.id, e)}
        @click=${() => this.onChipClick(list.id)}
        @pointerdown=${(e) => this.onChipPointerDown(list.id, e)}
        @pointerup=${() => this.clearChipLongPress()}
        @pointercancel=${() => this.clearChipLongPress()}
        @pointerleave=${() => this.clearChipLongPress()}
        @contextmenu=${(e) => { e.preventDefault(); this.openReorderPanel(list.id); }}
      >${list.name}</button>`);
  }

  onChipClick(listId) {
    if (this._suppressNextChipClick === listId) {
      this._suppressNextChipClick = "";
      return;
    }
    if (listId && listId === this._state?.system?.active_list_id) {
      this._listSettingsOpen = !this._listSettingsOpen;
      this._configOpen = false;
      this._createListOpen = false;
      this._menuOpen = false;
      return;
    }
    this.switchList(listId);
  }

  onChipPointerDown(listId, ev) {
    if (ev.pointerType === "mouse") return;
    this.clearChipLongPress();
    this._chipLongPressTimer = window.setTimeout(() => {
      this._suppressNextChipClick = listId;
      this.openReorderPanel(listId);
      this.clearChipLongPress();
    }, 550);
  }

  _onKeyDown(ev) {
    if (ev.key === "Escape" && (this._configOpen || this._createListOpen || this._listSettingsOpen || this._menuOpen || this._reorderListId)) {
      this.closePanels();
    }
  }

  openCreateList() {
    this._createListOpen = !this._createListOpen;
    this._configOpen = false;
    this._listSettingsOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
  }

  _itemTemplate(item, categories) {
    const key = this.editorKey(item);
    const editorOpen = this._openEditorKey === key;
    const qty = Number(item.quantity || 1);
    const dragClasses =
      (this._draggingItemRef === item.item_ref ? " dragging" : "") +
      (this._dragOverItemRef === item.item_ref ? " drag-over" : "");
    return html`
      <div class=${"item" + dragClasses}
        @dragover=${(e) => this.onItemDragOver(item, e)}
        @dragleave=${() => { if (this._dragOverItemRef === item.item_ref) this._dragOverItemRef = ""; }}
        @drop=${(e) => this.onItemDrop(item, e)}>
        <div class="item-main" @click=${() => this.toggleEditor(item)}>
          <div class="item-summary">
            <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag to reorder"
              @click=${(e) => e.stopPropagation()}
              @dragstart=${(e) => this.onItemDragStart(item, e)}
              @dragend=${() => this.onItemDragEnd()}>⠿</span>
            <input class="complete-toggle" type="checkbox" aria-label="Complete item"
              @click=${(e) => e.stopPropagation()}
              @change=${(e) => { if (e.target.checked) this.completeItem(item); }} />
            <strong>${item.summary}</strong>
          </div>
          <div class="item-pills">
            ${qty > 1 ? html`<span class="pill ghost-pill">Qty ${qty}</span>` : nothing}
            <span class="pill">${item.category_display}</span>
          </div>
        </div>
        <div class="small">${item.description || ""}</div>
        <div class=${"editor" + (editorOpen ? " open" : "")}>
          <input id="summary-${key}" class="input edit-summary" .value=${live(this._drafts[`summary:${key}`] ?? item.summary ?? "")}
            @click=${(e) => e.stopPropagation()}
            @input=${(e) => this.updateDraft(`summary:${key}`, e.target.value)}
            @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.saveItem(item); } }} />
          <input id="quantity-${key}" class="input edit-qty" type="number" min="1" step="1" inputmode="numeric"
            .value=${live(this._drafts[`quantity:${key}`] ?? String(item.quantity || 1))}
            @click=${(e) => e.stopPropagation()}
            @input=${(e) => this.updateDraft(`quantity:${key}`, e.target.value)} />
          <select class="select cat-select" .value=${live(this._drafts[`category:${key}`] || item.category || "")}
            @click=${(e) => e.stopPropagation()}
            @change=${(e) => this.updateDraft(`category:${key}`, e.target.value)}>
            ${categories.map((cat) => html`<option value=${cat}>${cat}</option>`)}
          </select>
          <button class="btn" @click=${(e) => { e.stopPropagation(); this.saveItem(item); }}>Save</button>
        </div>
      </div>`;
  }

  _completedItemTemplate(item) {
    const key = this.editorKey(item);
    const editorOpen = this._openEditorKey === key;
    const qty = Number(item.quantity || 1);
    return html`
      <div class="item completed-item">
        <div class="item-main completed-main" @click=${() => this.toggleEditor(item)}>
          <label class="completed-row" @click=${(e) => e.stopPropagation()}>
            <input class="completed-toggle" type="checkbox" checked aria-label="Restore item"
              @change=${(e) => { if (!e.target.checked) this.restoreCompleted(item); }} />
            <strong>${item.summary}</strong>
          </label>
          ${qty > 1 ? html`<span class="pill ghost-pill">Qty ${qty}</span>` : nothing}
        </div>
        <div class="small meta-line">${item.description || ""}</div>
        <div class=${"editor" + (editorOpen ? " open" : "")}>
          <input id="summary-${key}" class="input edit-summary" .value=${live(this._drafts[`summary:${key}`] ?? item.summary ?? "")}
            @click=${(e) => e.stopPropagation()}
            @input=${(e) => this.updateDraft(`summary:${key}`, e.target.value)}
            @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.saveCompletedItem(item); } }} />
          <input id="quantity-${key}" class="input edit-qty" type="number" min="1" step="1" inputmode="numeric"
            .value=${live(this._drafts[`quantity:${key}`] ?? String(item.quantity || 1))}
            @click=${(e) => e.stopPropagation()}
            @input=${(e) => this.updateDraft(`quantity:${key}`, e.target.value)} />
          <button class="btn" @click=${(e) => { e.stopPropagation(); this.saveCompletedItem(item); }}>Save</button>
        </div>
      </div>`;
  }

  _activityTemplate(state) {
    const activity = state?.activity || [];
    if (!activity.length) return html`<div class="empty">No recent activity.</div>`;
    return activity.map((entry) => html`
      <div class="item activity-item">
        <strong>${entry.title}</strong>
        <div class="small meta-line">
          ${entry.detail}${entry.list_name ? ` | ${entry.list_name}` : ""}${entry.source ? ` | ${entry.source}` : ""}${entry.when ? ` | ${entry.when}` : ""}
        </div>
      </div>`);
  }

  _attentionTemplates(state) {
    const parts = [];
    if (state?.pending_duplicate?.pending) {
      parts.push(html`
        <section class="section">
          <div class="title">Duplicate Needs Decision</div>
          <div class="small">${state.pending_duplicate.item} is already in ${state.pending_duplicate.target}.</div>
          <div class="row">
            <button class="btn primary" @click=${() => this.confirmDuplicate("add")}>Add Anyway</button>
            <button class="btn" @click=${() => this.confirmDuplicate("skip")}>Skip</button>
          </div>
        </section>`);
    }
    if (state?.pending_review?.pending) {
      parts.push(html`
        <section class="section">
          <div class="title">Review Needed</div>
          <div class="small">Item: <strong>${state.pending_review.item}</strong> (${state.pending_review.source_list})</div>
          <div class="row">
            ${(state.categories || []).map((cat) => html`<button class="btn" @click=${() => this.applyReview(cat, true)}>${cat.replaceAll("_", " ")}</button>`)}
            <button class="btn" @click=${() => this.applyReview("other", false)}>Keep Other</button>
          </div>
        </section>`);
    }
    return parts;
  }

  async confirmDuplicate(decision) {
    await this.act({
      action: "confirm_duplicate",
      decision,
      actor_user_id: this._hass?.user?.id || "",
      actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
    });
  }

  async applyReview(category, learn) {
    await this.act({ action: "apply_review", category, learn });
  }

  _menuTemplate(multilist) {
    return html`
      <div class="overlay-shell overlay-drawer" @click=${() => this.closePanels()}>
        <section class="side-drawer" role="dialog" aria-label="Menu" @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div class="section-label">Menu</div>
            <button class="btn icon-btn compact" aria-label="Close menu" @click=${() => this.closePanels()}>×</button>
          </div>
          <div class="drawer-stack">
            <button class="btn" @click=${() => { this._view = this._view === "activity" ? "list" : "activity"; this.closePanels(); }}>${this._view === "activity" ? "Back to List" : "Activity"}</button>
            <button class="btn" @click=${() => this.openAppSettings()}>App Settings</button>
            ${multilist ? html`<button class="btn" @click=${() => this.openListSettings()}>List Settings</button>` : nothing}
          </div>
        </section>
      </div>`;
  }

  openAppSettings() {
    this._configOpen = true;
    this._createListOpen = false;
    this._listSettingsOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
  }

  openListSettings() {
    this._listSettingsOpen = true;
    this._configOpen = false;
    this._createListOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
  }

  enterShopping() {
    this.closePanels();
    this._openEditorKey = "";
    this._view = "shopping";
  }

  exitShopping() {
    this._view = "list";
  }

  _shoppingTemplate(state, activeListName, activeListColor, visibleGroups) {
    const remaining = visibleGroups.reduce((sum, group) => sum + (group.items || []).length, 0);
    const completedCount = (state?.completed || []).length;
    const total = remaining + completedCount;
    const pct = total ? Math.round((completedCount / total) * 100) : 0;
    return html`
      <div class="shopping" style=${styleMap({ "--accent": activeListColor })}>
        <div class="shop-bar">
          <button class="btn shop-done" aria-label="Exit shopping mode" @click=${() => this.exitShopping()}>‹ Done</button>
          <div class="shop-heading">
            <div class="shop-title">${activeListName}</div>
            <div class="small">${remaining ? `${remaining} left${completedCount ? ` · ${completedCount} in cart` : ""}` : "All done"}</div>
          </div>
          <button class="btn icon-btn compact" aria-label="Refresh" title="Refresh" @click=${() => this.load(true)}>⟳</button>
        </div>
        <div class="shop-progress"><div class="shop-progress-fill" style=${styleMap({ width: pct + "%" })}></div></div>
        <div class="shop-add">
          <input id="shopAdd" class="input" placeholder="Add something you forgot" .value=${live(this._drafts.quickAdd || "")}
            @input=${(e) => this.updateDraft("quickAdd", e.target.value)}
            @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.addItem(); } }} />
          <button class="btn primary" @click=${() => this.addItem()}>Add</button>
        </div>
        ${remaining === 0
          ? html`<div class="shop-empty">🎉<div>Everything's checked off.</div>
              <button class="btn" @click=${() => this.exitShopping()}>Back to list</button></div>`
          : visibleGroups.map((group) => html`
              <div class="shop-section">
                <div class="shop-cat">${group.title}</div>
                ${repeat(group.items, (item) => item.item_ref, (item) => this._shoppingItem(item))}
              </div>`)}
      </div>
      ${this._undo ? html`
        <div class="undo-toast">
          <span>${this._undo.label}</span>
          <button class="btn" @click=${() => this.runUndo()}>Undo</button>
        </div>` : nothing}
    `;
  }

  _shoppingItem(item) {
    const qty = Number(item.quantity || 1);
    return html`
      <button class="shop-item" @click=${() => this.completeItem(item)} aria-label=${"Check off " + item.summary}>
        <span class="shop-check" aria-hidden="true"></span>
        <span class="shop-name">${item.summary}</span>
        ${qty > 1 ? html`<span class="pill ghost-pill">×${qty}</span>` : nothing}
      </button>`;
  }

  _appSettingsTemplate(state) {
    return html`
      <div class="overlay-shell" @click=${() => this.closePanels()}>
        <section class="modal-card" role="dialog" aria-label="App settings" @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div>
              <div class="title">Settings</div>
              <div class="small">Local-only mode. Lists, learned terms, dashboards, and routing stay inside Home Assistant.</div>
            </div>
            <button class="btn icon-btn compact" aria-label="Close settings" @click=${() => this.closePanels()}>×</button>
          </div>
          <div class="subsection">
            <div class="section-label">Local App</div>
            <div class="grid compact-grid">
              <div>
                <div class="label">Dashboard name</div>
                <input class="input" .value=${live(this._drafts.dashboardName || state?.settings?.dashboard_name || "Local List Assist")}
                  @input=${(e) => this.updateDraft("dashboardName", e.target.value)} />
                <div class="small">Used for the HA sidebar and generated dashboards. The panel refreshes after save.</div>
              </div>
            </div>
            ${this._categoryEditorTemplate("settingsCategories", "Default list categories", "Add a default category", "Add the categories new local lists should start with.")}
            <div class="row"><button class="btn primary" @click=${() => this.saveSettings()}>Save</button></div>
            <details class="advanced-box" ?open=${this._appToolsOpen} @toggle=${(e) => { this._appToolsOpen = e.target.open; }}>
              <summary>Tools</summary>
              <div class="row advanced-row">
                <button class="btn" @click=${() => this.act({ action: "install_voice_sentences", language: "en" })}>Install Voice Phrases</button>
                <button class="btn" @click=${() => this.act({ action: "repair_system" })}>Repair Local Setup</button>
                <label class="toggle-row"><input id="settingsDebugMode" type="checkbox" ?checked=${state?.settings?.debug_mode} /> Debug mode</label>
              </div>
            </details>
          </div>
        </section>
      </div>`;
  }

  _createListTemplate(state) {
    const templatePresets = state?.settings?.template_presets || state?.system?.template_presets || {};
    const templateIds = Array.from(new Set([...Object.keys(TEMPLATE_LABELS), ...Object.keys(templatePresets)]));
    return html`
      <div class="overlay-shell" @click=${() => this.closePanels()}>
        <section class="modal-card" role="dialog" aria-label="Create list" @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div>
              <div class="title">Create List</div>
              <div class="small">Use the plus button for a new local list.</div>
            </div>
            <button class="btn icon-btn compact" aria-label="Close create list" @click=${() => this.closePanels()}>×</button>
          </div>
          <div class="grid compact-grid">
            <input class="input" placeholder="New list name" .value=${live(this._drafts.newListName || "")}
              @input=${(e) => this.updateDraft("newListName", e.target.value)} />
            <select class="select" .value=${live(this._drafts.newListTemplate || "flat")}
              @change=${(e) => this.onTemplateChange(e.target.value, templatePresets)}>
              ${templateIds.map((id) => html`<option value=${id}>${TEMPLATE_LABELS[id] || id}</option>`)}
            </select>
            <input class="input" placeholder="Optional voice aliases (comma separated)" .value=${live(this._drafts.newListVoiceAliases || "")}
              @input=${(e) => this.updateDraft("newListVoiceAliases", e.target.value)} />
          </div>
          ${this._categoryEditorTemplate("newListCategories", "List categories", "Add a category for this list", "Leave it empty to use the selected template defaults.")}
          <div class="row">
            <button class="btn primary" @click=${() => this.createList()}>Create List</button>
            <button class="btn" @click=${() => this.closePanels()}>Cancel</button>
          </div>
        </section>
      </div>`;
  }

  onTemplateChange(templateId, presets) {
    this.updateDraft("newListTemplate", templateId || "flat");
    const categories = (presets[templateId] || []).join(", ");
    this.updateDraft("newListCategories", categories);
    this.requestUpdate();
  }

  _listSettingsTemplate(state, activeListName, activeListColor) {
    const activeCategories = (state?.system?.active_list_categories || []).filter(Boolean);
    const archived = state?.archived_lists || [];
    return html`
      <div class="overlay-shell" @click=${() => this.closePanels()}>
        <section class="modal-card" role="dialog" aria-label="List settings" @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div>
              <div class="title">List Settings</div>
              <div class="small">Tap the active list to manage it. Drag chips to reorder, or long-press / right-click for controls.</div>
            </div>
            <button class="btn icon-btn compact" aria-label="Close list settings" @click=${() => this.closePanels()}>×</button>
          </div>
          <div class="subsection">
            <div class="section-label">Current List</div>
            <div class="small">Editing ${activeListName}</div>
            <div class="grid compact-grid">
              <div>
                <div class="label">List name</div>
                <input class="input" placeholder="List name" .value=${live(this._drafts.activeListName || activeListName)}
                  @input=${(e) => this.updateDraft("activeListName", e.target.value)} />
              </div>
              <div>
                <div class="label">List color</div>
                <input class="color-input" type="color" .value=${live(this._drafts.activeListColor || activeListColor)}
                  @input=${(e) => this.updateDraft("activeListColor", e.target.value)} />
              </div>
            </div>
            ${this._categoryEditorTemplate("activeListCategories", "List categories", "Add a category for this list", activeCategories.length ? "" : "No categories yet. Add only the sections this list needs.")}
            <details class="advanced-box" ?open=${this._listToolsOpen} @toggle=${(e) => { this._listToolsOpen = e.target.open; }}>
              <summary>Advanced List Tools</summary>
              <div class="grid compact-grid" style="margin-top:12px;">
                <div>
                  <div class="label">Voice aliases</div>
                  <input class="input" placeholder="Optional voice aliases" .value=${live(this._drafts.activeListVoiceAliases || "")}
                    @input=${(e) => this.updateDraft("activeListVoiceAliases", e.target.value)} />
                </div>
              </div>
            </details>
            <div class="row">
              <button class="btn primary" @click=${() => this.saveActiveList()}>Save List</button>
              <button class="btn" @click=${() => { this._categoryRenameDrafts.activeListCategories = {}; this.updateDraft("activeListCategories", ""); this.requestUpdate(); }}>No Categories</button>
              <button class="btn danger" @click=${() => this.act({ action: "archive_list", list_id: this.currentListId() })}>Archive List</button>
            </div>
          </div>
          <div class="divider"></div>
          <div class="subsection">
            <div class="section-label">Archived Local Lists</div>
            ${archived.length
              ? archived.map((list) => html`
                  <div class="item">
                    <strong>${list.name}</strong>
                    <div class="row">
                      <button class="btn" @click=${() => this.act({ action: "restore_archived_list", list_id: list.id })}>Restore</button>
                      <button class="btn danger" @click=${() => this.actFast({ action: "delete_archived_list", list_id: list.id }, (s) => applyDeleteArchivedListLocal(s, list.id))}>Delete</button>
                    </div>
                  </div>`)
              : html`<div class="empty">No archived lists.</div>`}
          </div>
        </section>
      </div>`;
  }

  _reorderTemplate(state) {
    const target = (state?.lists || []).find((list) => list.id === this._reorderListId) || null;
    if (!target) return nothing;
    return html`
      <div class="overlay-shell" @click=${() => this.closePanels()}>
        <section class="modal-card modal-card-narrow" role="dialog" aria-label="Reorder list" @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div>
              <div class="title">Reorder ${target.name}</div>
              <div class="small">Drag chips on the main screen, or use these controls.</div>
            </div>
            <button class="btn icon-btn compact" aria-label="Close reorder" @click=${() => this.closePanels()}>×</button>
          </div>
          <div class="row">
            <button class="btn" @click=${() => this.reorderList("pin")}>Pin Near Front</button>
            <button class="btn" @click=${() => this.reorderList("left")}>Move Left</button>
            <button class="btn" @click=${() => this.reorderList("right")}>Move Right</button>
            <button class="btn" @click=${() => this.closePanels()}>Done</button>
          </div>
        </section>
      </div>`;
  }

  _categoryEditorTemplate(key, label, placeholder, helper = "") {
    const values = this.parseCategoryDraft(key);
    const inputKey = `${key}::new`;
    return html`
      <div class="category-editor">
        <div class="label">${label}</div>
        <div class="row category-add-row">
          <input class="input" placeholder=${placeholder} .value=${live(this._drafts[inputKey] || "")}
            @input=${(e) => this.updateDraft(inputKey, e.target.value)}
            @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.addCategoryFromInput(key, inputKey); } }} />
          <button class="btn" @click=${() => this.addCategoryFromInput(key, inputKey)}>Add Category</button>
        </div>
        <div class="category-chip-grid">
          ${values.length
            ? values.map((category, index) => html`
                <div class="category-chip-card">
                  <span class="pill ghost-pill">${this.categoryDisplay(category)}</span>
                  <div class="chip-actions">
                    <button class="chip-icon-btn" aria-label="Edit category" title="Edit category" @click=${() => this.editCategoryChip(key, index)}>✎</button>
                    <button class="chip-icon-btn" aria-label="Move category up" @click=${() => { this.moveCategoryDraft(key, index, -1); this.requestUpdate(); }}>↑</button>
                    <button class="chip-icon-btn" aria-label="Move category down" @click=${() => { this.moveCategoryDraft(key, index, 1); this.requestUpdate(); }}>↓</button>
                    <button class="chip-icon-btn danger" aria-label="Remove category" @click=${() => { this.removeCategoryDraft(key, index); this.requestUpdate(); }}>×</button>
                  </div>
                </div>`)
            : html`<div class="empty">${helper || "No categories added yet."}</div>`}
        </div>
      </div>`;
  }

  addCategoryFromInput(key, inputKey) {
    if (this.addCategoryDraft(key, this._drafts[inputKey] || "")) {
      this._drafts[inputKey] = "";
      this.requestUpdate();
    }
  }

  editCategoryChip(key, index) {
    const current = this.parseCategoryDraft(key);
    const existing = current[index] || "";
    if (!existing) return;
    const nextValue = window.prompt("Edit category", existing.replace(/_/g, " "));
    if (nextValue == null) return;
    if (this.renameCategoryDraft(key, index, nextValue)) {
      this.requestUpdate();
    }
  }

  static styles = css`
    :host {
      display: block;
      min-height: 100%;
      /* Theme-aware tokens: adopt the active Home Assistant theme, falling back
         to the original dark palette when a variable is unavailable. */
      --lla-bg-1: var(--primary-background-color, #0d1520);
      --lla-bg-2: var(--primary-background-color, #09111a);
      --lla-surface: var(--ha-card-background, var(--card-background-color, rgba(18, 31, 48, 0.94)));
      --lla-surface-2: var(--secondary-background-color, #0d1826);
      --lla-input-bg: var(--card-background-color, #08111b);
      --lla-text: var(--primary-text-color, #f3f7fb);
      --lla-text-dim: var(--secondary-text-color, #9fb4ca);
      --lla-border: var(--divider-color, #203a57);
      --lla-danger: var(--error-color, #d96b6b);
      background: var(--lla-bg-1);
      color: var(--lla-text);
      font-family: var(--paper-font-body1_-_font-family, "Segoe UI", system-ui, sans-serif);
    }
    * { box-sizing: border-box; }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 20px; --accent: #2c78ba; }
    .hero, .section {
      background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 10%, var(--lla-surface)), var(--lla-surface));
      border: 1px solid color-mix(in srgb, var(--accent) 32%, var(--lla-border));
      border-radius: 24px; padding: 20px; margin-bottom: 16px;
    }
    .title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
    .modal-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
    .hero-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
    .hero-title { font-size: 28px; font-weight: 800; margin: 0 0 8px; }
    .sub, .small, .label, .empty { color: var(--lla-text-dim); }
    .section-label { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
    .subsection { display: flex; flex-direction: column; gap: 12px; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 10px; align-items: center; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
    .compact-grid { align-items: end; }
    .toggle-row { display: flex; gap: 8px; align-items: center; color: var(--lla-text); }
    .input, .select {
      width: 100%; background: var(--lla-input-bg); color: var(--lla-text);
      border: 1px solid var(--lla-border); border-radius: 14px; padding: 12px 14px; font: inherit;
    }
    .quick-add-row { align-items: stretch; }
    .qty-input { width: 96px; flex: 0 0 96px; text-align: center; }
    .color-input { width: 100%; min-height: 48px; background: var(--lla-input-bg); border: 1px solid var(--lla-border); border-radius: 14px; padding: 6px; }
    .btn {
      border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--lla-border));
      background: color-mix(in srgb, var(--accent) 16%, var(--lla-surface-2));
      color: var(--lla-text); border-radius: 14px; padding: 12px 16px; cursor: pointer; font: inherit;
    }
    .btn:hover { border-color: color-mix(in srgb, var(--accent) 70%, var(--lla-border)); }
    .btn.primary { background: var(--accent); border-color: color-mix(in srgb, var(--accent) 60%, white); color: #fff; }
    .btn.danger { background: color-mix(in srgb, var(--lla-danger) 30%, var(--lla-surface-2)); border-color: var(--lla-danger); }
    .advanced-box { border: 1px solid var(--lla-border); border-radius: 16px; padding: 12px 14px; background: var(--lla-surface-2); }
    .advanced-box summary { cursor: pointer; color: var(--lla-text); font-weight: 600; }
    .advanced-row { margin-top: 12px; }
    .overlay-shell { position: fixed; inset: 0; background: rgba(3, 8, 14, 0.58); backdrop-filter: blur(4px); z-index: 30; display: flex; align-items: center; justify-content: center; padding: 24px; }
    .overlay-drawer { justify-content: flex-end; padding: 0; }
    .modal-card, .side-drawer {
      background: var(--lla-surface); color: var(--lla-text);
      border: 1px solid color-mix(in srgb, var(--accent) 36%, var(--lla-border)); border-radius: 24px;
      box-shadow: 0 24px 90px rgba(0, 0, 0, 0.44);
    }
    .modal-card { width: min(760px, calc(100vw - 48px)); max-height: calc(100vh - 48px); overflow: auto; padding: 20px; }
    .modal-card-narrow { width: min(560px, calc(100vw - 48px)); }
    .side-drawer { width: min(360px, 92vw); height: 100vh; border-radius: 0; padding: 22px 18px; }
    .drawer-stack { display: flex; flex-direction: column; gap: 10px; }
    .mobile-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .mobile-title { font-size: 14px; font-weight: 700; color: var(--lla-text-dim); letter-spacing: 0.04em; text-transform: uppercase; }
    .icon-btn { width: 44px; height: 44px; display: inline-flex; align-items: center; justify-content: center; font-size: 20px; padding: 0; }
    .icon-btn.compact { width: 42px; height: 42px; font-size: 18px; flex: 0 0 auto; }
    .list-chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .list-chip {
      border: 1px solid color-mix(in srgb, var(--chip-color) 55%, var(--lla-border));
      background: color-mix(in srgb, var(--chip-color) 20%, var(--lla-surface-2));
      color: var(--lla-text); border-radius: 999px; padding: 8px 12px; cursor: pointer; font: inherit;
      transition: transform 140ms ease, border-color 140ms ease, background 140ms ease;
    }
    .list-chip.active { box-shadow: 0 0 0 1px color-mix(in srgb, var(--chip-color) 70%, white) inset; }
    .list-chip:hover { transform: translateY(-1px); }
    .item { background: var(--lla-surface-2); border: 1px solid var(--lla-border); border-radius: 16px; padding: 12px; margin-bottom: 10px; }
    .activity-item, .completed-item { padding: 10px 12px; }
    .completed-row { display: flex; gap: 10px; align-items: flex-start; }
    .meta-line { line-height: 1.45; }
    .item-main { display: flex; justify-content: space-between; gap: 10px; align-items: center; cursor: pointer; }
    .item-pills { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .item-summary { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .drag-handle { cursor: grab; color: var(--lla-text-dim); font-size: 16px; line-height: 1; user-select: none; touch-action: none; padding: 0 2px; }
    .drag-handle:active { cursor: grabbing; }
    .item.dragging { opacity: 0.4; }
    .item.drag-over { box-shadow: inset 0 3px 0 -1px var(--accent); }
    .list-chip.dragging { opacity: 0.4; }
    .list-chip.drag-over { box-shadow: inset 3px 0 0 -1px var(--accent); }
    .editor { display: none; gap: 10px; margin-top: 10px; }
    .editor.open { display: flex; flex-wrap: wrap; }
    .edit-qty { width: 96px; flex: 0 0 96px; text-align: center; }
    .edit-summary { flex: 1 1 160px; }
    .pill { font-size: 11px; padding: 4px 10px; border-radius: 999px; background: color-mix(in srgb, var(--accent) 26%, var(--lla-surface-2)); color: var(--lla-text); }
    .ghost-pill { background: color-mix(in srgb, var(--lla-text-dim) 18%, var(--lla-surface-2)); }
    .category-chip-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
    .category-chip-card { display: flex; align-items: center; gap: 8px; border: 1px solid var(--lla-border); background: var(--lla-surface-2); border-radius: 16px; padding: 8px 10px; }
    .chip-actions { display: flex; gap: 6px; }
    .chip-icon-btn { width: 28px; height: 28px; border-radius: 999px; border: 1px solid var(--lla-border); background: color-mix(in srgb, var(--accent) 18%, var(--lla-surface-2)); color: var(--lla-text); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0; font-size: 14px; line-height: 1; }
    .chip-icon-btn.danger { background: color-mix(in srgb, var(--lla-danger) 30%, var(--lla-surface-2)); border-color: var(--lla-danger); }
    .hero-actions { display: flex; gap: 8px; align-items: center; }
    .divider { height: 1px; background: var(--lla-border); margin: 16px 0; }
    .error { color: var(--lla-danger); font-weight: 600; }
    .undo-toast {
      position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%);
      background: var(--lla-surface); color: var(--lla-text); border: 1px solid var(--lla-border);
      border-radius: 14px; padding: 10px 14px; display: flex; align-items: center; gap: 12px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4); z-index: 40;
    }
    .undo-toast .btn { padding: 6px 12px; }
    .shop-btn { font-size: 20px; }
    .shopping { max-width: 720px; margin: 0 auto; padding: 10px 12px 40px; min-height: 100%; --accent: #2c78ba; }
    .shop-bar { display: flex; align-items: center; gap: 10px; position: sticky; top: 0; z-index: 5; padding: 8px 0; background: var(--lla-bg-1); }
    .shop-done { padding: 10px 14px; }
    .shop-heading { flex: 1; text-align: center; min-width: 0; }
    .shop-title { font-size: 18px; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .shop-progress { height: 6px; border-radius: 999px; background: var(--lla-surface-2); overflow: hidden; margin: 4px 2px 14px; }
    .shop-progress-fill { height: 100%; background: var(--accent); transition: width 220ms ease; }
    .shop-add { display: flex; gap: 8px; margin-bottom: 16px; }
    .shop-section { margin-bottom: 18px; }
    .shop-cat { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--lla-text-dim); margin: 6px 4px 8px; }
    .shop-item { display: flex; align-items: center; gap: 14px; width: 100%; text-align: left; background: var(--lla-surface-2); border: 1px solid var(--lla-border); border-radius: 16px; padding: 16px; margin-bottom: 10px; color: var(--lla-text); font: inherit; font-size: 18px; cursor: pointer; transition: transform 80ms ease, opacity 120ms ease; }
    .shop-item:active { transform: scale(0.99); }
    .shop-check { width: 26px; height: 26px; flex: 0 0 26px; border-radius: 50%; border: 2px solid color-mix(in srgb, var(--accent) 70%, var(--lla-border)); }
    .shop-name { flex: 1; }
    .shop-empty { text-align: center; padding: 48px 16px; font-size: 44px; color: var(--lla-text-dim); display: flex; flex-direction: column; gap: 16px; align-items: center; }
    .shop-empty div { font-size: 16px; }
    @media (max-width: 720px) {
      .wrap { padding: 14px; }
      .hero, .section { border-radius: 20px; padding: 16px; }
      .hero-title { font-size: 24px; }
      .row { gap: 8px; }
      .qty-input { width: 84px; flex-basis: 84px; }
      .activity-item, .completed-item { padding: 10px; margin-bottom: 8px; }
      .meta-line { font-size: 13px; }
      .item-main { align-items: flex-start; }
      .overlay-shell { padding: 12px; }
      .modal-card { width: 100%; max-height: calc(100vh - 24px); padding: 16px; }
    }
  `;
}

customElements.define("local-list-assist-panel", LocalListAssistPanel);
