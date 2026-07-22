import { LitElement, html, css, nothing } from "./vendor/lit.js";
import { repeat } from "./vendor/lit.js";
import { live } from "./vendor/lit.js";
import { styleMap } from "./vendor/lit.js";
import {
  categoryDisplay as displayCategory,
  createListLocal as applyCreateListLocal,
  deleteArchivedListLocal as applyDeleteArchivedListLocal,
  groupTitle as deriveGroupTitle,
  matchSuggestions,
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
    _mealEditorId: { state: true },
    _mealConfirmId: { state: true },
    _mealChecked: { state: true },
    _mealConfirmEdits: { state: true },
    _mealEditingKey: { state: true },
    _mealTab: { state: true },
    _mealSearch: { state: true },
    _recipeImporting: { state: true },
    _recipeImportError: { state: true },
    _stepsChecked: { state: true },
    _suggestOpen: { state: true },
    _suggestIndex: { state: true },
    _shopCollapsed: { state: true },
    _weekStart: { state: true },
    _confirmOpen: { state: true },
    _confirmItems: { state: true },
    _confirmChecked: { state: true },
    _confirmEdits: { state: true },
    _confirmEditingKey: { state: true },
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
    this._mealEditorId = "";
    this._mealConfirmId = "";
    this._mealChecked = {};
    this._mealConfirmEdits = {};
    this._mealEditingKey = "";
    this._mealTab = "add";
    this._mealSearch = "";
    this._recipeImporting = false;
    this._recipeImportError = "";
    this._stepsChecked = {};
    this._suggestOpen = false;
    this._suggestIndex = -1;
    this._shopCollapsed = {};
    this._suggestBlurTimer = null;
    this._weekStart = "";
    this._confirmOpen = false;
    this._confirmItems = [];
    this._confirmTitle = "";
    this._confirmMealName = "";
    this._confirmChecked = {};
    this._confirmEdits = {};
    this._confirmEditingKey = "";
    this._frequentLongPressTimer = null;
    this._suppressNextFrequentClick = "";
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
      mealName: "",
      mealIngredients: "",
      mealDirections: "",
      mealNotes: "",
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

  toggleStandardCategory(key, category) {
    const current = this.parseCategoryDraft(key);
    const index = current.indexOf(category);
    if (index >= 0) {
      current.splice(index, 1);
    } else {
      current.push(category);
    }
    this.writeCategoryDraft(key, current);
    this.requestUpdate();
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
    this._mealEditorId = "";
    this._mealConfirmId = "";
    this._confirmOpen = false;
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

  // --- quick-add autocomplete ---
  quickAddSuggestions() {
    return matchSuggestions(this._state?.suggestions || [], this._drafts.quickAdd || "", 6);
  }

  onQuickAddInput(value) {
    this.updateDraft("quickAdd", value);
    this._suggestOpen = true;
    this._suggestIndex = -1;
    // _drafts is a plain object, so mutating quickAdd does not by itself
    // re-render. Without this, the dropdown only refreshes when a reactive
    // property changes (e.g. _suggestOpen on the first character), leaving the
    // suggestions frozen on the first letter instead of narrowing as you type.
    this.requestUpdate();
  }

  onQuickAddFocus() {
    if ((this._drafts.quickAdd || "").trim()) this._suggestOpen = true;
    // On mobile the on-screen keyboard covers the lower half of the screen, so
    // the suggestion dropdown (rendered below the input) can be hidden behind it.
    // On the List tab, bring the field toward the top once the keyboard has had a
    // moment to open, so the dropdown lands in the visible band above the keyboard.
    //
    // We deliberately skip this on the Shop tab: its header is position:sticky, so
    // scrollIntoView({ block: "start" }) would scroll the field *behind* that
    // sticky header ("the page scrolls down and you lose the text box"). The Shop
    // layout keeps its own field visible without help. (List's .mobile-bar is not
    // sticky, so the scroll there is safe.)
    if (this._view === "shopping") return;
    window.setTimeout(() => {
      const field = this.renderRoot?.querySelector(".quick-add-field");
      if (field && typeof field.scrollIntoView === "function") {
        field.scrollIntoView({ block: "start", behavior: "smooth" });
      }
    }, 320);
  }

  toggleShopCategory(category) {
    const key = String(category || "");
    this._shopCollapsed = { ...this._shopCollapsed, [key]: !this._shopCollapsed[key] };
  }

  closeSuggest() {
    this._suggestOpen = false;
    this._suggestIndex = -1;
  }

  deferCloseSuggest() {
    if (this._suggestBlurTimer) window.clearTimeout(this._suggestBlurTimer);
    this._suggestBlurTimer = window.setTimeout(() => { this.closeSuggest(); this._suggestBlurTimer = null; }, 150);
  }

  onQuickAddKeydown(ev) {
    const matches = this.quickAddSuggestions();
    if (ev.key === "ArrowDown") {
      if (matches.length) {
        ev.preventDefault();
        this._suggestOpen = true;
        this._suggestIndex = Math.min(this._suggestIndex + 1, matches.length); // last index = "add new" row
      }
      return;
    }
    if (ev.key === "ArrowUp") {
      if (this._suggestOpen) {
        ev.preventDefault();
        this._suggestIndex = Math.max(this._suggestIndex - 1, -1);
      }
      return;
    }
    if (ev.key === "Escape") {
      if (this._suggestOpen) { ev.preventDefault(); this.closeSuggest(); }
      return;
    }
    if (ev.key === "Enter") {
      ev.preventDefault();
      if (this._suggestOpen && this._suggestIndex >= 0 && this._suggestIndex < matches.length) {
        this.selectSuggestion(matches[this._suggestIndex].item);
      } else {
        this.closeSuggest();
        this.addItem();
      }
    }
  }

  async selectSuggestion(item) {
    this.closeSuggest();
    this._drafts.quickAdd = String(item || "");
    this.requestUpdate();
    await this.addItem();
  }

  onSuggestionClick(s) {
    if (this._suppressNextSuggestClick) {
      this._suppressNextSuggestClick = false;
      return;
    }
    this.selectSuggestion(s.item);
  }

  onSuggestionPointerDown(s, ev) {
    if (ev.pointerType === "mouse" && ev.button !== 0) return;
    this.clearSuggestLongPress();
    this._suggestLongPressTimer = window.setTimeout(() => {
      this._suppressNextSuggestClick = true;
      this.dismissSuggestion(s);
      this.clearSuggestLongPress();
    }, 550);
  }

  clearSuggestLongPress() {
    if (this._suggestLongPressTimer) {
      window.clearTimeout(this._suggestLongPressTimer);
      this._suggestLongPressTimer = null;
    }
  }

  async dismissSuggestion(s) {
    if (this._suggestBlurTimer) { window.clearTimeout(this._suggestBlurTimer); this._suggestBlurTimer = null; }
    await this.act({
      action: "dismiss_suggestion",
      normalized: s?.normalized || "",
      item: s?.item || "",
      list_id: this.currentListId(),
    });
  }

  async quickAddItem(item) {
    const name = String(item || "").trim();
    if (!name) return;
    await this.act({
      action: "add_item",
      item: name,
      quantity: 1,
      list_id: this.currentListId(),
      actor_user_id: this._hass?.user?.id || "",
      actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
    });
  }

  onFrequentClick(item) {
    if (this._suppressNextFrequentClick === item) {
      this._suppressNextFrequentClick = "";
      return;
    }
    this.quickAddItem(item);
  }

  onFrequentPointerDown(item, ev) {
    if (ev.pointerType === "mouse" && ev.button !== 0) return;
    this.clearFrequentLongPress();
    this._frequentLongPressTimer = window.setTimeout(() => {
      this._suppressNextFrequentClick = item;
      this.dismissFrequent(item);
      this.clearFrequentLongPress();
    }, 550);
  }

  clearFrequentLongPress() {
    if (this._frequentLongPressTimer) {
      window.clearTimeout(this._frequentLongPressTimer);
      this._frequentLongPressTimer = null;
    }
  }

  async dismissFrequent(item) {
    const name = String(item || "").trim();
    if (!name) return;
    await this.act({ action: "dismiss_frequent", item: name, list_id: this.currentListId() });
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

  async exportData() {
    try {
      const result = await this.api("action", "POST", { action: "export_data" });
      const backup = result?.export;
      if (!backup) {
        this._error = "Export failed.";
        this.requestUpdate();
        return;
      }
      const stamp = (backup.exported_at || "").replace(/[:.]/g, "-").slice(0, 19) || "backup";
      const blob = new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `local-list-assist-${stamp}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      this._error = err.message || String(err);
      this.requestUpdate();
    }
  }

  async onImportFileChosen(ev) {
    const input = ev.target;
    const file = input?.files?.[0];
    input.value = "";
    if (!file) return;
    let parsed;
    try {
      parsed = JSON.parse(await file.text());
    } catch (_err) {
      this._error = "That file is not a valid Local List Assist backup.";
      this.requestUpdate();
      return;
    }
    const data = parsed && typeof parsed.data === "object" ? parsed.data : parsed;
    if (!data || typeof data !== "object") {
      this._error = "That file is not a valid Local List Assist backup.";
      this.requestUpdate();
      return;
    }
    if (!window.confirm("Import will replace your current lists, meals, and learned data with this backup. Continue?")) {
      return;
    }
    await this.act({ action: "import_data", data });
    this.closePanels();
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
      return html`<div class="app"><div class="app-scroll"><div class="wrap"><section class="hero"><div class="empty">Loading…</div></section></div></div></div>`;
    }
    const multilist = !!state?.settings?.experimental_multilist;
    const dashboardName = state?.settings?.dashboard_name || "Local List Assist";
    const active = state?.lists?.find((list) => list.active) || null;
    const activeListName = active?.name || "Grocery List";
    const activeListColor = state?.system?.active_list_color || active?.color || "#2c78ba";
    const visibleGroups = (state?.groups || []).filter((group) => (group.items || []).length > 0);

    let screen;
    if (this._view === "shopping") {
      screen = this._shoppingTemplate(state, activeListName, activeListColor, visibleGroups);
    } else if (this._view === "meals") {
      screen = this._mealsScreen(state);
    } else if (this._view === "plan") {
      screen = this._planScreen(state);
    } else {
      screen = this._listScreen(state, multilist, dashboardName, activeListName, visibleGroups);
    }

    return html`
      <div class="app" style=${styleMap({ "--accent": activeListColor })} @keydown=${(e) => this._onKeyDown(e)}>
        <div class="app-scroll">${screen}</div>
        ${this._menuOpen ? this._menuTemplate(multilist) : nothing}
        ${this._configOpen ? this._appSettingsTemplate(state) : nothing}
        ${this._createListOpen && multilist ? this._createListTemplate(state) : nothing}
        ${this._listSettingsOpen && multilist ? this._listSettingsTemplate(state, activeListName, activeListColor) : nothing}
        ${this._reorderListId && multilist ? this._reorderTemplate(state) : nothing}
        ${this._mealConfirmId ? this._mealDetailTemplate(state) : nothing}
        ${this._confirmOpen ? this._confirmAddTemplate() : nothing}
        ${this._bottomBar()}
        ${this._undo ? html`
          <div class="undo-toast">
            <span>${this._undo.label}</span>
            <button class="btn" @click=${() => this.runUndo()}>Undo</button>
          </div>` : nothing}
      </div>`;
  }

  _listScreen(state, multilist, dashboardName, activeListName, visibleGroups) {
    return html`
      <div class="wrap">
        ${this._narrow
          ? html`<div class="mobile-bar">
              <button id="menuBtn" class="btn icon-btn" aria-label="Open navigation" @click=${() => this.openNavigation()}>☰</button>
              <div class="mobile-title">${dashboardName}</div>
            </div>`
          : nothing}
        <section class="hero">
          <div class="hero-head">
            <div class="hero-headings">
              <div class="hero-title">${dashboardName}</div>
              <div class="sub">Local-only Home Assistant workspace. Current list: ${activeListName}.</div>
            </div>
            <div class="hero-actions">
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
            <div class="quick-add-field">
              <input id="quickAdd" class="input" placeholder="Add item" autocomplete="off" .value=${live(this._drafts.quickAdd || "")}
                @input=${(e) => this.onQuickAddInput(e.target.value)}
                @focus=${() => this.onQuickAddFocus()}
                @blur=${() => this.deferCloseSuggest()}
                @keydown=${(e) => this.onQuickAddKeydown(e)} />
              ${this._suggestOpen ? this._suggestDropdown() : nothing}
            </div>
            <input id="quickAddQty" class="input qty-input" type="number" min="1" step="1" inputmode="numeric" placeholder="Qty"
              .value=${live(this._drafts.quickAddQty || "1")}
              @input=${(e) => this.updateDraft("quickAddQty", e.target.value)} />
            <button class="btn primary" @click=${() => this.addItem()}>Add</button>
          </div>
          ${this._frequentTemplate(state)}
        </section>

        ${this._error ? html`<section class="section"><div class="title">Error</div><div class="error">${this._error}</div></section>` : nothing}
        ${this._attentionTemplates(state)}

        ${this._view === "activity"
          ? html`<section class="section"><div class="title">Recent Activity</div>${this._activityTemplate(state)}</section>`
          : html`
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
              </section>`}
      </div>`;
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
    if (ev.key === "Escape") {
      if (this._confirmOpen) { this.closeConfirmAdd(); return; }
      if (this._mealConfirmId) { this.closeMealDetail(); return; }
      if (this._configOpen || this._createListOpen || this._listSettingsOpen || this._menuOpen || this._reorderListId) {
        this.closePanels();
      }
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

  _suggestDropdown() {
    const typed = (this._drafts.quickAdd || "").trim();
    const matches = this.quickAddSuggestions();
    if (!typed || !matches.length) return nothing;
    return html`
      <div class="suggest-dropdown" @mousedown=${(e) => e.preventDefault()}>
        ${matches.map((s, i) => html`
          <button class=${"suggest-row" + (this._suggestIndex === i ? " active" : "")}
            title="Tap to add · long-press or right-click to remove"
            @click=${() => this.onSuggestionClick(s)}
            @contextmenu=${(e) => { e.preventDefault(); this.dismissSuggestion(s); }}
            @pointerdown=${(e) => this.onSuggestionPointerDown(s, e)}
            @pointerup=${() => this.clearSuggestLongPress()}
            @pointerleave=${() => this.clearSuggestLongPress()}>
            <span class="suggest-name">${s.item}</span>
            <span class="pill">${s.category_display}</span>
          </button>`)}
        <button class=${"suggest-row suggest-new" + (this._suggestIndex === matches.length ? " active" : "")}
          @click=${() => { this.closeSuggest(); this.addItem(); }}>
          <span class="suggest-name">+ Add “${typed}” as new item</span>
        </button>
      </div>`;
  }

  _frequentTemplate(state) {
    const frequent = (state?.frequent_items || []).filter((f) => f && f.item);
    if (!frequent.length) return nothing;
    return html`
      <div class="frequent-row" aria-label="Frequently added items">
        <span class="frequent-label">Frequent</span>
        ${frequent.map((f) => html`
          <button class="frequent-chip" title="Tap to add · long-press or right-click to hide"
            @click=${() => this.onFrequentClick(f.item)}
            @pointerdown=${(e) => this.onFrequentPointerDown(f.item, e)}
            @pointerup=${() => this.clearFrequentLongPress()}
            @pointerleave=${() => this.clearFrequentLongPress()}
            @contextmenu=${(e) => { e.preventDefault(); this.dismissFrequent(f.item); }}>
            <span class="frequent-plus">+</span>${f.item}
          </button>`)}
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
          <div class="small">This item didn't match a category. Pick where it belongs and the app <strong>learns</strong> it — future adds of <strong>${state.pending_review.item}</strong> will route there automatically. Or tap <em>Keep Other</em> to leave it uncategorized.</div>
          <div class="small" style="margin-top:8px;">Item: <strong>${state.pending_review.item}</strong> (${state.pending_review.source_list})</div>
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

  _mealsScreen(state) {
    const meals = state?.meals || [];
    const editing = !!this._mealEditorId;
    return html`
      <div class="wrap page meal-page">
        <section class="hero">
          <div class="page-head">
            <div class="hero-title">${editing ? (this._mealEditorId === "new" ? "New Meal" : "Edit Meal") : "Meals"}</div>
            <button class="btn icon-btn compact" aria-label="Refresh" title="Refresh" @click=${() => this.load(true)}>⟳</button>
          </div>
          <div class="sub">Save a meal once — ingredients and directions — then add it to your list or plan it into a day.</div>
          ${editing ? this._mealEditorTemplate() : this._mealListTemplate(meals)}
        </section>
      </div>`;
  }

  _planScreen(state) {
    const meals = state?.meals || [];
    return html`
      <div class="wrap page meal-page">
        <section class="hero">
          <div class="page-head">
            <div class="hero-title">Plan</div>
            <button class="btn icon-btn compact" aria-label="Refresh" title="Refresh" @click=${() => this.load(true)}>⟳</button>
          </div>
          <div class="sub">Plan meals onto dates, then add a day's or the whole week's ingredients to your list.</div>
          ${this._weekTemplate(state, meals)}
        </section>
      </div>`;
  }

  _weekTemplate(state, meals) {
    if (!meals.length) {
      return html`<div class="empty">Create a meal first, then you can plan it onto a day.</div>`;
    }
    const plan = state?.meal_plan || {};
    const dates = this.weekDates();
    const todayISO = this._toISODate(new Date());
    const thisMonday = this._toISODate(this._mondayOf(new Date()));
    const isCurrentWeek = this.weekStartISO() === thisMonday;
    const rangeStart = this._parseISODate(dates[0]);
    const rangeEnd = this._parseISODate(dates[6]);
    const fmt = (d) => d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const totalPlanned = dates.reduce((sum, key) => sum + ((plan[key] || []).length), 0);
    return html`
      <div class="week-nav">
        <button class="btn icon-btn compact" aria-label="Previous week" @click=${() => this.shiftWeek(-7)}>‹</button>
        <div class="week-range">
          <strong>${fmt(rangeStart)} – ${fmt(rangeEnd)}</strong>
          ${isCurrentWeek ? html`<span class="week-badge">This week</span>` : html`<button class="btn compact" @click=${() => this.goToday()}>Today</button>`}
        </div>
        <button class="btn icon-btn compact" aria-label="Next week" @click=${() => this.shiftWeek(7)}>›</button>
      </div>
      <div class="week-list">
        ${dates.map((key) => {
          const date = this._parseISODate(key);
          const weekday = date.toLocaleDateString(undefined, { weekday: "long" });
          const dayMeals = plan[key] || [];
          const isToday = key === todayISO;
          return html`
            <div class=${"week-day" + (isToday ? " today" : "")}>
              <div class="week-day-head">
                <strong>${weekday} <span class="week-day-date">${fmt(date)}${isToday ? " · Today" : ""}</span></strong>
                ${dayMeals.length
                  ? html`<button class="btn compact" @click=${() => this.addDayToList(key, weekday)}>Add day</button>`
                  : nothing}
              </div>
              <div class="week-day-meals">
                ${dayMeals.length
                  ? dayMeals.map((m) => html`
                    <span class="week-chip">
                      <button class="week-chip-name" title="Open ${m.name}" @click=${() => this.openMealDetail(m.meal_id, "directions")}>${m.name}</button>
                      <button class="week-chip-x" aria-label="Remove ${m.name}" @click=${() => this.unassignMeal(key, m.meal_id)}>×</button>
                    </span>`)
                  : html`<span class="small">No meals yet</span>`}
              </div>
              <select class="input week-select" .value=${live("")} @change=${(e) => { this.assignMeal(key, e.target.value); e.target.value = ""; }}>
                <option value="">+ Add a meal…</option>
                ${meals.map((meal) => html`<option value=${meal.id}>${meal.name}</option>`)}
              </select>
            </div>`;
        })}
      </div>
      <div class="row">
        <button class="btn primary" ?disabled=${totalPlanned === 0} @click=${() => this.addWeekToList()}>Add whole week to list</button>
        <button class="btn danger" ?disabled=${totalPlanned === 0} @click=${() => this.clearWeek()}>Clear week</button>
      </div>`;
  }

  mealMatchesSearch(meal, query) {
    if (!query) return true;
    if ((meal.name || "").toLowerCase().includes(query)) return true;
    return (meal.ingredients || []).some((ing) => (ing.item || "").toLowerCase().includes(query));
  }

  _mealListTemplate(meals) {
    // Favorites (for the current Home Assistant user) float to the top, keeping
    // the backend's name order within each group. A star marks favorited rows.
    const favs = new Set(this._state?.favorites || []);
    const query = (this._mealSearch || "").trim().toLowerCase();
    const filtered = meals.filter((m) => this.mealMatchesSearch(m, query));
    const ordered = [...filtered].sort((a, b) => (favs.has(b.id) ? 1 : 0) - (favs.has(a.id) ? 1 : 0));
    return html`
      <div class="row meal-actions">
        <button class="btn primary" @click=${() => this.openMealEditor("new")}>New Meal</button>
        <button class="btn" @click=${() => this.openMealFromList()}>From current list</button>
      </div>
      ${meals.length
        ? html`<div class="meal-search-row">
            <input class="input meal-search" type="search" inputmode="search" placeholder="Search meals by name or ingredient"
              .value=${live(this._mealSearch || "")}
              @input=${(e) => { this._mealSearch = e.target.value; }} />
            ${query ? html`<button class="btn compact" @click=${() => { this._mealSearch = ""; }}>Clear</button>` : nothing}
          </div>`
        : nothing}
      <div class="meal-list">
        ${ordered.length
          ? repeat(ordered, (m) => m.id, (m) => html`
            <button class="meal-row meal-row-button" @click=${() => this.openMealDetail(m.id, "add")}>
              <div class="meal-row-main">
                <strong>${favs.has(m.id) ? html`<span class="meal-fav-star" aria-label="Favorite" title="Favorite">★</span> ` : nothing}${m.name}</strong>
                <div class="small">${m.ingredient_count} ${m.ingredient_count === 1 ? "ingredient" : "ingredients"}${m.direction_count ? ` · ${m.direction_count} ${m.direction_count === 1 ? "step" : "steps"}` : ""}${(m.notes || "").trim() ? " · has notes" : ""}</div>
              </div>
              <span class="meal-row-open">Open ›</span>
            </button>`)
          : meals.length
            ? html`<div class="empty">No meals match “${this._mealSearch}”.</div>`
            : html`<div class="empty">No saved meals yet. Create one with ingredients and directions, then add it to your list with a tap.</div>`}
      </div>`;
  }

  _mealEditorTemplate() {
    const isNew = this._mealEditorId === "new";
    return html`
      ${isNew ? html`
        <div class="recipe-import">
          <div class="label">Import from a recipe link</div>
          <div class="row recipe-import-row">
            <input class="input" type="url" inputmode="url" autocomplete="off"
              placeholder="Paste a recipe URL" .value=${live(this._drafts.recipeUrl || "")}
              @input=${(e) => this.updateDraft("recipeUrl", e.target.value)}
              @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.importRecipe(); } }} />
            <button class="btn" ?disabled=${this._recipeImporting} @click=${() => this.importRecipe()}>
              ${this._recipeImporting ? "Importing…" : "Import"}
            </button>
          </div>
          ${this._recipeImportError ? html`<div class="error small">${this._recipeImportError}</div>` : nothing}
          <div class="small">Pulls the name, ingredients and directions off the page so you can review and tweak them below before saving. Your Home Assistant reads the recipe directly — nothing is sent to any cloud service.</div>
        </div>` : nothing}
      <div class="grid compact-grid">
        <input class="input" placeholder="Meal name (e.g. Taco Night)" .value=${live(this._drafts.mealName || "")}
          @input=${(e) => this.updateDraft("mealName", e.target.value)} />
      </div>
      <div class="label">Ingredients (one per line)</div>
      <textarea class="input meal-textarea" rows="7" placeholder="ground beef&#10;taco shells&#10;shredded cheese&#10;lettuce"
        .value=${live(this._drafts.mealIngredients || "")}
        @input=${(e) => this.updateDraft("mealIngredients", e.target.value)}></textarea>
      <div class="label">Directions (one step per line)</div>
      <textarea class="input meal-textarea" rows="7" placeholder="Brown the beef over medium heat&#10;Warm the shells&#10;Assemble with cheese and lettuce"
        .value=${live(this._drafts.mealDirections || "")}
        @input=${(e) => this.updateDraft("mealDirections", e.target.value)}></textarea>
      <div class="label">Notes</div>
      <textarea class="input meal-textarea" rows="4" placeholder="Anything you want to remember — swaps, who likes it, serving ideas, tweaks that worked."
        .value=${live(this._drafts.mealNotes || "")}
        @input=${(e) => this.updateDraft("mealNotes", e.target.value)}></textarea>
      <div class="row">
        <button class="btn primary" @click=${() => this.saveMeal()}>${isNew ? "Create Meal" : "Save Meal"}</button>
        <button class="btn" @click=${() => this.closeMealEditor()}>Cancel</button>
      </div>`;
  }

  _mealDetailTemplate(state) {
    const meal = (state?.meals || []).find((m) => m.id === this._mealConfirmId) || null;
    if (!meal) return nothing;
    const ingredients = meal.ingredients || [];
    const directions = meal.directions || [];
    const hasNotes = !!(meal.notes || "").trim();
    const tab = this._mealTab === "directions" ? "directions" : "add";
    const isFav = (state?.favorites || []).includes(meal.id);
    return html`
      <div class="overlay-shell" @click=${() => this.closeMealDetail()}>
        <section class="modal-card" role="dialog" aria-label=${meal.name} @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div class="meal-detail-head">
              <button class="btn compact" @click=${() => this.backToMeals()}>‹ Meals</button>
              <div class="title">${meal.name}</div>
            </div>
            <button class="btn icon-btn compact" aria-label="Close" @click=${() => this.closeMealDetail()}>×</button>
          </div>
          <div class="meal-tabs">
            <button class=${"meal-tab" + (tab === "add" ? " active" : "")} @click=${() => { this._mealTab = "add"; }}>Ingredients</button>
            <button class=${"meal-tab" + (tab === "directions" ? " active" : "")} @click=${() => { this._mealTab = "directions"; }}>Directions &amp; notes${directions.length ? ` (${directions.length})` : ""}${hasNotes ? " 📝" : ""}</button>
            <span class="meal-tab-spacer"></span>
            <button class=${"btn compact meal-fav-btn" + (isFav ? " fav-on" : "")}
              aria-pressed=${isFav ? "true" : "false"}
              title=${isFav ? "Remove from your favorites" : "Add to your favorites"}
              @click=${() => this.toggleFavorite(meal.id)}>${isFav ? "★ Favorited" : "☆ Favorite"}</button>
            <button class="btn compact" @click=${() => this.openMealEditor(meal.id)}>Edit</button>
            <button class="btn compact danger" @click=${() => this.deleteMeal(meal.id)}>Delete</button>
          </div>
          ${tab === "add"
            ? this._mealAddTab(meal, ingredients)
            : this._mealDirectionsTab(meal, directions)}
        </section>
      </div>`;
  }

  _mealAddTab(meal, ingredients) {
    if (!ingredients.length) {
      return html`<div class="empty">No ingredients on this meal yet. Use Edit to add some.</div>`;
    }
    const selectedCount = ingredients.filter((ing, idx) => {
      const key = this.mealIngKey(idx, ing.item);
      return this._mealChecked[key] && String(this.ingredientValue(key, ing.item)).trim();
    }).length;
    return html`
      <div class="small">Uncheck anything you already have (or grew), then add the rest.</div>
      <div class="row" style="justify-content:space-between; align-items:center;">
        <div class="small">${selectedCount} of ${ingredients.length} selected</div>
        <div class="row">
          <button class="btn compact" @click=${() => this.setAllMealIngredients(meal, true)}>All</button>
          <button class="btn compact" @click=${() => this.setAllMealIngredients(meal, false)}>None</button>
        </div>
      </div>
      <div class="meal-ingredients">
        ${ingredients.map((ing, idx) => {
          const key = this.mealIngKey(idx, ing.item);
          const checked = !!this._mealChecked[key];
          const editing = this._mealEditingKey === key;
          const value = this.ingredientValue(key, ing.item);
          return html`
            <div class=${"meal-ingredient" + (checked ? "" : " unchecked")}>
              <input type="checkbox" .checked=${live(checked)} @change=${() => this.toggleMealIngredient(key)} />
              ${editing
                ? html`<input id=${`meal-ing-${key}`} class="input meal-ing-input" .value=${live(value)}
                    @input=${(e) => this.updateIngredientEdit(key, e.target.value)}
                    @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.stopEditIngredient(); } }}
                    @blur=${() => this.stopEditIngredient()} />`
                : html`<span class="meal-ingredient-name" @click=${() => this.toggleMealIngredient(key)}>${value}</span>`}
              <button class="meal-ing-edit" aria-label="Edit ingredient" title="Edit" @click=${() => this.startEditIngredient(key, value)}>✎</button>
              ${editing ? nothing : html`<span class="pill">${ing.category_display}</span>`}
            </div>`;
        })}
      </div>
      <div class="row">
        <button class="btn primary" ?disabled=${selectedCount === 0} @click=${() => this.confirmAddMeal()}>Add ${selectedCount} to list</button>
        <button class="btn" @click=${() => this.closeMealDetail()}>Cancel</button>
      </div>`;
  }

  _confirmAddTemplate() {
    const items = this._confirmItems || [];
    const selectedCount = items.filter((it, idx) => this._confirmChecked[String(idx)] && String(this.confirmValueAt(idx, it.item)).trim()).length;
    return html`
      <div class="overlay-shell" @click=${() => this.closeConfirmAdd()}>
        <section class="modal-card" role="dialog" aria-label="Confirm ingredients" @click=${(e) => e.stopPropagation()}>
          <div class="modal-head">
            <div>
              <div class="title">${this._confirmTitle}</div>
              <div class="small">Uncheck anything you already have, then add the rest.</div>
            </div>
            <button class="btn icon-btn compact" aria-label="Close" @click=${() => this.closeConfirmAdd()}>×</button>
          </div>
          <div class="row" style="justify-content:space-between; align-items:center;">
            <div class="small">${selectedCount} of ${items.length} selected</div>
            <div class="row">
              <button class="btn compact" @click=${() => this.setAllConfirm(true)}>All</button>
              <button class="btn compact" @click=${() => this.setAllConfirm(false)}>None</button>
            </div>
          </div>
          <div class="meal-ingredients">
            ${items.map((it, idx) => {
              const k = String(idx);
              const checked = !!this._confirmChecked[k];
              const editing = this._confirmEditingKey === k;
              const value = this.confirmValueAt(idx, it.item);
              return html`
                <div class=${"meal-ingredient" + (checked ? "" : " unchecked")}>
                  <input type="checkbox" .checked=${live(checked)} @change=${() => this.toggleConfirm(idx)} />
                  ${editing
                    ? html`<input id=${`confirm-ing-${k}`} class="input meal-ing-input" .value=${live(value)}
                        @input=${(e) => this.updateConfirmEdit(idx, e.target.value)}
                        @keydown=${(e) => { if (e.key === "Enter") { e.preventDefault(); this.stopEditConfirm(); } }}
                        @blur=${() => this.stopEditConfirm()} />`
                    : html`<span class="meal-ingredient-name" @click=${() => this.toggleConfirm(idx)}>${value}</span>`}
                  <button class="meal-ing-edit" aria-label="Edit ingredient" title="Edit" @click=${() => this.startEditConfirm(idx, value)}>✎</button>
                  ${editing ? nothing : (it.category_display ? html`<span class="pill">${it.category_display}</span>` : nothing)}
                </div>`;
            })}
          </div>
          <div class="row">
            <button class="btn primary" ?disabled=${selectedCount === 0} @click=${() => this.submitConfirmAdd()}>Add ${selectedCount} to list</button>
            <button class="btn" @click=${() => this.closeConfirmAdd()}>Cancel</button>
          </div>
        </section>
      </div>`;
  }

  _mealDirectionsTab(meal, directions) {
    const done = directions.filter((_step, idx) => this._stepsChecked[idx]).length;
    return html`
      ${directions.length
        ? html`
          <div class="small">Tap a step to check it off as you cook. ${done} of ${directions.length} done.</div>
          <ol class="meal-steps">
            ${directions.map((step, idx) => html`
              <li class=${"meal-step" + (this._stepsChecked[idx] ? " done" : "")} @click=${() => this.toggleStep(idx)}>
                <span class="meal-step-num">${idx + 1}</span>
                <span class="meal-step-text">${step}</span>
              </li>`)}
          </ol>`
        : html`<div class="empty">No directions yet. Use Edit to add the steps, one per line.</div>`}
      <div class="meal-notes-inline">
        <div class="label">Notes</div>
        <textarea class="input meal-notes-edit" rows="3"
          placeholder="Jot a note — swaps, who likes it, a tweak that worked. Saves on its own."
          .value=${live(meal.notes || "")}
          @change=${(e) => this.saveMealNotes(meal.id, e.target.value)}></textarea>
      </div>`;
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

  // --- primary navigation (bottom bar) ---
  goList() {
    this.closePanels();
    this._mealEditorId = "";
    this._view = "list";
  }

  goShop() {
    this.enterShopping();
  }

  goMeals() {
    this.closePanels();
    this._mealEditorId = "";
    this._view = "meals";
  }

  goPlan() {
    this.closePanels();
    this._mealEditorId = "";
    this._weekStart = this._toISODate(this._mondayOf(new Date()));
    this._view = "plan";
  }

  _bottomBar() {
    const v = this._view;
    const tab = (icon, label, onClick, active) => html`
      <button class=${"nav-item" + (active ? " active" : "")} @click=${onClick}
        aria-label=${label} aria-current=${active ? "page" : "false"}>
        <span class="nav-icon">${icon}</span><span class="nav-label">${label}</span>
      </button>`;
    return html`
      <nav class="bottom-nav">
        ${tab("🧾", "List", () => this.goList(), v === "list" || v === "activity")}
        ${tab("🛒", "Shop", () => this.goShop(), v === "shopping")}
        ${tab("🍽", "Meals", () => this.goMeals(), v === "meals")}
        ${tab("📅", "Plan", () => this.goPlan(), v === "plan")}
      </nav>`;
  }

  openMealEditor(mealId) {
    const meal = (this._state?.meals || []).find((m) => m.id === mealId) || null;
    this._mealEditorId = mealId || "new";
    this._drafts.mealName = meal?.name || "";
    this._drafts.mealIngredients = (meal?.ingredients || []).map((i) => i.item).join("\n");
    this._drafts.mealDirections = (meal?.directions || []).join("\n");
    this._drafts.mealNotes = meal?.notes || "";
    this._mealConfirmId = "";
    this._view = "meals";
    this.requestUpdate();
  }

  openMealFromList() {
    const groups = this._state?.groups || [];
    const items = [];
    const seen = new Set();
    for (const group of groups) {
      for (const item of group.items || []) {
        const summary = (item.summary || "").trim();
        const key = summary.toLowerCase();
        if (summary && !seen.has(key)) {
          seen.add(key);
          items.push(summary);
        }
      }
    }
    this._mealEditorId = "new";
    this._drafts.mealName = "";
    this._drafts.mealIngredients = items.join("\n");
    this._drafts.mealDirections = "";
    this._drafts.mealNotes = "";
    this._mealConfirmId = "";
    this._view = "meals";
    this.requestUpdate();
    this.updateComplete.then(() => {
      const el = this.renderRoot?.querySelector(".meal-page .input");
      if (el) el.focus();
    });
  }

  closeMealEditor() {
    this._mealEditorId = "";
    this._drafts.mealName = "";
    this._drafts.mealIngredients = "";
    this._drafts.mealDirections = "";
    this._drafts.mealNotes = "";
    this.requestUpdate();
  }

  async saveMeal() {
    const name = (this._drafts.mealName || "").trim();
    if (!name) return;
    const ingredients = (this._drafts.mealIngredients || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
      .map((item) => ({ item }));
    const directions = (this._drafts.mealDirections || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const notes = (this._drafts.mealNotes || "").trim();
    const payload = { action: "save_meal", name, ingredients, directions, notes };
    if (this._mealEditorId && this._mealEditorId !== "new") payload.meal_id = this._mealEditorId;
    await this.act(payload);
    this.closeMealEditor();
  }

  async deleteMeal(mealId) {
    await this.act({ action: "delete_meal", meal_id: mealId });
  }

  async saveMealNotes(mealId, notes) {
    if (!mealId) return;
    const next = (notes || "").trim();
    const meal = (this._state?.meals || []).find((m) => m.id === mealId);
    // Only round-trip when the note actually changed (blur fires either way).
    if (meal && (meal.notes || "").trim() === next) return;
    await this.act({ action: "update_meal_notes", meal_id: mealId, notes: next });
  }

  _recipeImportErrorText(code) {
    switch (code) {
      case "missing_url": return "Paste a recipe link first.";
      case "invalid_url": return "That doesn't look like a public recipe link. Paste the recipe page's own web address (not a share or shortened link).";
      case "not_a_page": return "That link isn't a web page we can read.";
      case "too_large": return "That page is too big to read. Try a different recipe link.";
      case "blocked": return "That site blocked the import. Try a different recipe site, or type the ingredients and directions in below.";
      case "no_recipe": return "Couldn't find recipe data on that page. If you pasted a share or Google link, open it and copy the recipe page's own address instead. Otherwise you can type it in below.";
      case "fetch_failed":
      case "fetch_error":
      default: return "Couldn't reach that link. Check the address and try again.";
    }
  }

  async importRecipe() {
    const url = (this._drafts.recipeUrl || "").trim();
    if (!url) return;
    this._recipeImportError = "";
    this._recipeImporting = true;
    this.requestUpdate();
    try {
      // import_recipe returns {ok, recipe} (no dashboard), so call the API
      // directly rather than act(), which would trigger a needless reload.
      const res = await this.api("action", "POST", { action: "import_recipe", url });
      if (!res || res.ok === false) {
        this._recipeImportError = this._recipeImportErrorText(res && res.error);
        return;
      }
      const recipe = res.recipe || {};
      if (recipe.name) this.updateDraft("mealName", recipe.name);
      if (Array.isArray(recipe.ingredients) && recipe.ingredients.length) {
        this.updateDraft("mealIngredients", recipe.ingredients.join("\n"));
      }
      if (Array.isArray(recipe.directions) && recipe.directions.length) {
        this.updateDraft("mealDirections", recipe.directions.join("\n"));
      }
      this.updateDraft("recipeUrl", "");
    } catch (err) {
      this._recipeImportError = "Couldn't reach that link. Check the URL and try again.";
    } finally {
      this._recipeImporting = false;
      this.requestUpdate();
    }
  }

  async toggleFavorite(mealId) {
    if (!mealId) return;
    await this.act({ action: "toggle_favorite", meal_id: mealId });
  }

  // --- weekly planner (dated) ---
  _toISODate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  _parseISODate(iso) {
    const [y, m, d] = String(iso).split("-").map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
  }

  _mondayOf(date) {
    const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const offset = (d.getDay() + 6) % 7; // days since Monday
    d.setDate(d.getDate() - offset);
    return d;
  }

  weekStartISO() {
    return this._weekStart || this._toISODate(this._mondayOf(new Date()));
  }

  weekDates() {
    const start = this._parseISODate(this.weekStartISO());
    return Array.from({ length: 7 }, (_v, i) => {
      const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
      return this._toISODate(d);
    });
  }

  shiftWeek(deltaDays) {
    const start = this._parseISODate(this.weekStartISO());
    start.setDate(start.getDate() + deltaDays);
    this._weekStart = this._toISODate(start);
  }

  goToday() {
    this._weekStart = this._toISODate(this._mondayOf(new Date()));
  }

  async assignMeal(dateKey, mealId) {
    const id = String(mealId || "").trim();
    if (!id || !dateKey) return;
    await this.act({ action: "assign_meal", date: dateKey, meal_id: id });
  }

  async unassignMeal(dateKey, mealId) {
    await this.act({ action: "unassign_meal", date: dateKey, meal_id: mealId });
  }

  async clearWeek() {
    if (!window.confirm("Remove all meals from the days shown this week? Other weeks are untouched.")) return;
    await this.act({ action: "clear_meal_plan_dates", dates: this.weekDates() });
  }

  aggregateMealItems(mealIds) {
    const byId = new Map((this._state?.meals || []).map((m) => [m.id, m]));
    const items = [];
    const seen = new Set();
    for (const id of mealIds) {
      const meal = byId.get(id);
      if (!meal) continue;
      for (const ing of meal.ingredients || []) {
        const item = (ing.item || "").trim();
        const key = item.toLowerCase();
        if (item && !seen.has(key)) {
          seen.add(key);
          items.push({ item, category_display: ing.category_display || "" });
        }
      }
    }
    return items;
  }

  addDayToList(dateKey, label) {
    const dayMeals = (this._state?.meal_plan?.[dateKey]) || [];
    const items = this.aggregateMealItems(dayMeals.map((m) => m.meal_id));
    if (!items.length) return;
    this.openConfirmAdd(items, `${label} meals`, `${label} meals`);
  }

  addWeekToList() {
    const plan = this._state?.meal_plan || {};
    const ids = [];
    this.weekDates().forEach((dateKey) => (plan[dateKey] || []).forEach((m) => ids.push(m.meal_id)));
    const items = this.aggregateMealItems(ids);
    if (!items.length) return;
    this.openConfirmAdd(items, "This week's meals", "This week's meals");
  }

  // --- generic confirm-add checklist (used by the planner) ---
  openConfirmAdd(items, title, mealName) {
    const checked = {};
    items.forEach((_it, idx) => { checked[String(idx)] = true; });
    this._confirmItems = items;
    this._confirmTitle = title;
    this._confirmMealName = mealName || title;
    this._confirmChecked = checked;
    this._confirmEdits = {};
    this._confirmEditingKey = "";
    this._confirmOpen = true;
  }

  closeConfirmAdd() {
    this._confirmOpen = false;
    this._confirmEditingKey = "";
  }

  confirmValueAt(idx, fallback) {
    const edited = this._confirmEdits[String(idx)];
    return edited !== undefined ? edited : fallback;
  }

  toggleConfirm(idx) {
    const k = String(idx);
    this._confirmChecked = { ...this._confirmChecked, [k]: !this._confirmChecked[k] };
  }

  setAllConfirm(value) {
    const checked = {};
    (this._confirmItems || []).forEach((_it, idx) => { checked[String(idx)] = value; });
    this._confirmChecked = checked;
  }

  startEditConfirm(idx, value) {
    const k = String(idx);
    if (this._confirmEdits[k] === undefined) {
      this._confirmEdits = { ...this._confirmEdits, [k]: value };
    }
    this._confirmChecked = { ...this._confirmChecked, [k]: true };
    this._confirmEditingKey = k;
    this.updateComplete.then(() => {
      const el = this.renderRoot?.getElementById(`confirm-ing-${k}`);
      if (el) { el.focus(); el.select?.(); }
    });
  }

  updateConfirmEdit(idx, value) {
    this._confirmEdits = { ...this._confirmEdits, [String(idx)]: value };
  }

  stopEditConfirm() {
    this._confirmEditingKey = "";
  }

  async submitConfirmAdd() {
    const items = (this._confirmItems || [])
      .map((it, idx) => ({ item: String(this.confirmValueAt(idx, it.item)).trim(), checked: !!this._confirmChecked[String(idx)] }))
      .filter((entry) => entry.checked && entry.item)
      .map((entry) => ({ item: entry.item }));
    this._confirmOpen = false;
    this._confirmEditingKey = "";
    if (!items.length) return;
    await this.act({
      action: "add_meal_to_list",
      meal_name: this._confirmMealName,
      list_id: this.currentListId(),
      items,
      actor_user_id: this._hass?.user?.id || "",
      actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
    });
  }

  mealIngKey(index, item) {
    return `${index}:${item}`;
  }

  openMealDetail(mealId, tab = "add") {
    const meal = (this._state?.meals || []).find((m) => m.id === mealId) || null;
    if (!meal) return;
    const checked = {};
    (meal.ingredients || []).forEach((ing, idx) => { checked[this.mealIngKey(idx, ing.item)] = true; });
    this._mealChecked = checked;
    this._mealConfirmEdits = {};
    this._mealEditingKey = "";
    this._stepsChecked = {};
    const hasIngredients = (meal.ingredients || []).length > 0;
    const hasDirections = (meal.directions || []).length > 0;
    let nextTab = tab;
    if (nextTab === "add" && !hasIngredients && hasDirections) nextTab = "directions";
    if (nextTab === "directions" && !hasDirections) nextTab = "add";
    this._mealTab = nextTab;
    this._mealConfirmId = mealId;
    this._view = "meals";
    this._mealEditorId = "";
  }

  closeMealDetail() {
    this._mealConfirmId = "";
    this._mealEditingKey = "";
  }

  backToMeals() {
    this._mealConfirmId = "";
    this._mealEditingKey = "";
    this._view = "meals";
  }

  toggleStep(index) {
    this._stepsChecked = { ...this._stepsChecked, [index]: !this._stepsChecked[index] };
  }

  ingredientValue(key, fallback) {
    const edited = this._mealConfirmEdits[key];
    return (edited !== undefined ? edited : fallback);
  }

  startEditIngredient(key, currentValue) {
    if (this._mealConfirmEdits[key] === undefined) {
      this._mealConfirmEdits = { ...this._mealConfirmEdits, [key]: currentValue };
    }
    this._mealChecked = { ...this._mealChecked, [key]: true };
    this._mealEditingKey = key;
    this.updateComplete.then(() => {
      const el = this.renderRoot?.getElementById(`meal-ing-${key}`);
      if (el) { el.focus(); el.select?.(); }
    });
  }

  updateIngredientEdit(key, value) {
    this._mealConfirmEdits = { ...this._mealConfirmEdits, [key]: value };
  }

  stopEditIngredient() {
    this._mealEditingKey = "";
  }

  toggleMealIngredient(key) {
    this._mealChecked = { ...this._mealChecked, [key]: !this._mealChecked[key] };
  }

  setAllMealIngredients(meal, value) {
    const checked = {};
    (meal.ingredients || []).forEach((ing, idx) => { checked[this.mealIngKey(idx, ing.item)] = value; });
    this._mealChecked = checked;
  }

  async confirmAddMeal() {
    const meal = (this._state?.meals || []).find((m) => m.id === this._mealConfirmId) || null;
    if (!meal) { this._mealConfirmId = ""; return; }
    const items = (meal.ingredients || [])
      .map((ing, idx) => {
        const key = this.mealIngKey(idx, ing.item);
        return { key, item: String(this.ingredientValue(key, ing.item)).trim() };
      })
      .filter(({ key, item }) => this._mealChecked[key] && item)
      .map(({ item }) => ({ item }));
    this._mealConfirmId = "";
    this._mealEditingKey = "";
    if (!items.length) return;
    await this.act({
      action: "add_meal_to_list",
      meal_id: meal.id,
      meal_name: meal.name,
      list_id: this.currentListId(),
      items,
      actor_user_id: this._hass?.user?.id || "",
      actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
    });
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
          <div class="quick-add-field">
            <input id="shopAdd" class="input" placeholder="Add something you forgot" autocomplete="off" .value=${live(this._drafts.quickAdd || "")}
              @input=${(e) => this.onQuickAddInput(e.target.value)}
              @focus=${() => this.onQuickAddFocus()}
              @blur=${() => this.deferCloseSuggest()}
              @keydown=${(e) => this.onQuickAddKeydown(e)} />
            ${this._suggestOpen ? this._suggestDropdown() : nothing}
          </div>
          <button class="btn primary" @click=${() => this.addItem()}>Add</button>
        </div>
        ${remaining === 0
          ? html`<div class="shop-empty">🎉<div>Everything's checked off.</div>
              <button class="btn" @click=${() => this.exitShopping()}>Back to list</button></div>`
          : visibleGroups.map((group) => {
              const collapsed = !!this._shopCollapsed[group.category];
              return html`
              <div class="shop-section">
                <button class="shop-cat" aria-expanded=${collapsed ? "false" : "true"}
                  @click=${() => this.toggleShopCategory(group.category)}>
                  <span class="shop-cat-label">${group.title} (${group.items.length})</span>
                  <span class="shop-cat-chevron ${collapsed ? "collapsed" : ""}" aria-hidden="true">▾</span>
                </button>
                ${collapsed ? nothing : repeat(group.items, (item) => item.item_ref, (item) => this._shoppingItem(item))}
              </div>`;
            })}
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
              <div class="label" style="margin-top:14px;">Backup</div>
              <div class="small">Export a local JSON backup of your lists, meals, and learned data — or restore one. Import replaces your current data; run Repair Local Setup afterwards if you use voice.</div>
              <div class="row advanced-row">
                <button class="btn" @click=${() => this.exportData()}>Export backup</button>
                <button class="btn" @click=${() => this.renderRoot?.getElementById("importFileInput")?.click()}>Import backup</button>
                <input id="importFileInput" type="file" accept="application/json,.json" style="display:none"
                  @change=${(e) => this.onImportFileChosen(e)} />
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
    const currentSet = new Set(values);
    const standard = this._state?.settings?.standard_categories || [];
    const inputKey = `${key}::new`;
    return html`
      <div class="category-editor">
        <div class="label">${label}</div>
        ${standard.length ? html`
          <div class="small">Check the sections this list should use. Unchecking one hides its section and moves any items in it to Other.</div>
          <div class="category-check-grid">
            ${standard.map((category) => {
              const on = currentSet.has(category);
              return html`
                <label class=${"category-check" + (on ? " on" : "")}>
                  <input type="checkbox" .checked=${live(on)} @change=${() => this.toggleStandardCategory(key, category)} />
                  <span>${this.categoryDisplay(category)}</span>
                </label>`;
            })}
          </div>
          <div class="label" style="margin-top:14px;">Custom categories &amp; order</div>` : nothing}
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
    .app { --accent: #2c78ba; }
    .app-scroll { padding-bottom: 82px; }
    .page-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .bottom-nav {
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 30;
      display: flex; gap: 4px; justify-content: center; padding: 6px 8px calc(6px + env(safe-area-inset-bottom, 0px));
      background: var(--lla-surface); border-top: 1px solid var(--lla-border);
      box-shadow: 0 -6px 24px rgba(0, 0, 0, 0.14);
    }
    .nav-item {
      flex: 1 1 0; max-width: 160px; display: flex; flex-direction: column; align-items: center; gap: 3px;
      border: none; background: transparent; color: var(--lla-text-dim); cursor: pointer;
      font: inherit; padding: 7px 4px; border-radius: 12px; min-height: 52px; justify-content: center;
    }
    .nav-item .nav-icon { font-size: 21px; line-height: 1; }
    .nav-item .nav-label { font-size: 12px; font-weight: 600; }
    .nav-item.active { color: var(--accent); background: color-mix(in srgb, var(--accent) 15%, transparent); }
    .nav-item:hover { color: var(--lla-text); }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 20px; --accent: #2c78ba; }
    .hero, .section {
      background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 10%, var(--lla-surface)), var(--lla-surface));
      border: 1px solid color-mix(in srgb, var(--accent) 32%, var(--lla-border));
      border-radius: 24px; padding: 20px; margin-bottom: 16px;
    }
    .title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
    .modal-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 12px; }
    .hero-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .hero-headings { min-width: 0; flex: 1 1 60%; }
    .hero-title { font-size: 28px; font-weight: 800; margin: 0 0 8px; overflow-wrap: anywhere; }
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
    .quick-add-row { position: relative; align-items: stretch; }
    .quick-add-field { position: relative; flex: 1; min-width: 0; }
    .quick-add-field .input { width: 100%; }
    /* On the List tab the input shares its row with the Qty box and Add button,
       so anchor the suggestion dropdown to the whole row instead of the narrow
       input — it then spans the full width and item names aren't truncated. */
    .quick-add-row .quick-add-field { position: static; }
    .suggest-dropdown {
      position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 25;
      background: var(--lla-surface); border: 1px solid var(--lla-border); border-radius: 14px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.28); overflow: hidden; max-height: 320px; overflow-y: auto;
    }
    .suggest-row {
      display: flex; align-items: center; justify-content: space-between; gap: 10px; width: 100%;
      border: none; background: transparent; color: var(--lla-text); font: inherit; text-align: left;
      padding: 11px 14px; cursor: pointer; border-bottom: 1px solid var(--lla-border);
    }
    .suggest-row:last-child { border-bottom: none; }
    .suggest-row:hover, .suggest-row.active { background: color-mix(in srgb, var(--accent) 14%, var(--lla-surface-2)); }
    .suggest-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 auto; min-width: 0; }
    .suggest-row .pill { flex: 0 0 auto; max-width: 45%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .suggest-new .suggest-name { font-weight: 500; color: var(--lla-text-dim); }
    .qty-input { width: 96px; flex: 0 0 96px; text-align: center; }
    .frequent-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
    .frequent-label { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--lla-text-dim); margin-right: 2px; }
    .frequent-chip {
      display: inline-flex; align-items: center; gap: 4px;
      border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--lla-border));
      background: color-mix(in srgb, var(--accent) 12%, var(--lla-surface-2));
      color: var(--lla-text); border-radius: 999px; padding: 6px 12px; cursor: pointer; font: inherit; font-size: 13px;
    }
    .frequent-chip:hover { background: color-mix(in srgb, var(--accent) 22%, var(--lla-surface-2)); }
    .frequent-plus { font-weight: 700; color: var(--accent); }
    .meal-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; max-height: 52vh; overflow-y: auto; }
    .meal-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
      border: 1px solid var(--lla-border); border-radius: 14px; padding: 12px 14px; background: var(--lla-surface-2); }
    .meal-row-main { min-width: 120px; }
    .meal-row-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .meal-textarea { min-height: 168px; resize: vertical; font: inherit; line-height: 1.5; }
    .meal-actions { margin-bottom: 12px; }
    .meal-search-row { display: flex; gap: 8px; align-items: stretch; margin-bottom: 12px; }
    .meal-search { flex: 1 1 auto; min-width: 0; }
    .meal-notes { white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.55; padding: 6px 2px; }
    .meal-notes-inline { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--lla-border); }
    .meal-notes-edit { width: 100%; resize: vertical; font: inherit; line-height: 1.5; min-height: 64px; }
    .recipe-import { border: 1px solid var(--lla-border); border-radius: 14px; padding: 12px 14px; margin-bottom: 14px; background: var(--lla-surface-2); display: flex; flex-direction: column; gap: 6px; }
    .recipe-import-row { gap: 8px; align-items: stretch; }
    .recipe-import-row .input { flex: 1 1 auto; min-width: 0; }
    .meal-fav-star { color: #e0a12b; }
    .meal-fav-btn.fav-on { border-color: #e0a12b; color: #e0a12b; }
    .meal-ingredients { display: flex; flex-direction: column; gap: 8px; margin: 12px 0; max-height: 46vh; overflow-y: auto; }
    .meal-ingredient { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px;
      border: 1px solid var(--lla-border); background: var(--lla-surface-2); cursor: pointer; }
    .meal-ingredient input[type="checkbox"] { width: 22px; height: 22px; flex: 0 0 auto; accent-color: var(--accent); }
    .meal-ingredient-name { flex: 1; font-weight: 600; }
    .meal-ingredient.unchecked { opacity: 0.5; }
    .meal-ingredient.unchecked .meal-ingredient-name { text-decoration: line-through; }
    .meal-ing-input { flex: 1; padding: 8px 10px; border-radius: 10px; }
    .meal-ing-edit {
      flex: 0 0 auto; border: none; background: transparent; color: var(--lla-text-dim);
      cursor: pointer; font: inherit; font-size: 16px; padding: 4px 6px; border-radius: 8px;
    }
    .meal-ing-edit:hover { color: var(--lla-text); background: color-mix(in srgb, var(--accent) 14%, transparent); }
    .meal-row-button { width: 100%; text-align: left; font: inherit; color: var(--lla-text); cursor: pointer; }
    .meal-row-button:hover { border-color: color-mix(in srgb, var(--accent) 55%, var(--lla-border)); }
    .meal-row-open { flex: 0 0 auto; color: var(--lla-text-dim); font-weight: 600; }
    .meal-detail-head { display: flex; align-items: center; gap: 10px; min-width: 0; }
    .meal-tabs { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; border-bottom: 1px solid var(--lla-border); padding-bottom: 10px; margin-bottom: 12px; }
    .meal-tab { border: none; background: transparent; color: var(--lla-text-dim); font: inherit; font-weight: 600; cursor: pointer; padding: 8px 12px; border-radius: 10px; }
    .meal-tab.active { color: var(--lla-text); background: color-mix(in srgb, var(--accent) 16%, var(--lla-surface-2)); }
    .meal-tab-spacer { flex: 1; }
    .meal-steps { list-style: none; margin: 12px 0; padding: 0; display: flex; flex-direction: column; gap: 8px; max-height: 52vh; overflow-y: auto; }
    .meal-step { display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px; border-radius: 12px;
      border: 1px solid var(--lla-border); background: var(--lla-surface-2); cursor: pointer; line-height: 1.45; }
    .meal-step-num { flex: 0 0 auto; width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
      font-size: 13px; font-weight: 700; color: var(--accent); border: 2px solid color-mix(in srgb, var(--accent) 55%, var(--lla-border)); }
    .meal-step-text { flex: 1; padding-top: 2px; }
    .meal-step.done { opacity: 0.55; }
    .meal-step.done .meal-step-text { text-decoration: line-through; }
    .meal-step.done .meal-step-num { color: #fff; background: var(--accent); border-color: var(--accent); }
    .week-nav { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
    .week-range { display: flex; align-items: center; gap: 10px; flex: 1; justify-content: center; }
    .week-badge { font-size: 12px; color: var(--lla-text-dim); border: 1px solid var(--lla-border); border-radius: 999px; padding: 2px 10px; }
    .week-day-date { font-weight: 500; color: var(--lla-text-dim); font-size: 13px; }
    .week-day.today { border-color: color-mix(in srgb, var(--accent) 60%, var(--lla-border)); background: color-mix(in srgb, var(--accent) 8%, var(--lla-surface-2)); }
    .week-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; max-height: 52vh; overflow-y: auto; }
    .week-day { border: 1px solid var(--lla-border); border-radius: 14px; padding: 12px 14px; background: var(--lla-surface-2); }
    .week-day-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
    .week-day-meals { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
    .week-chip { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 5px 6px 5px 12px; font-size: 13px;
      border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--lla-border)); background: color-mix(in srgb, var(--accent) 14%, var(--lla-surface)); }
    .week-chip-name { border: none; background: transparent; color: inherit; font: inherit; cursor: pointer; padding: 0; text-align: left; }
    .week-chip-name:hover { text-decoration: underline; }
    .week-chip-x { border: none; background: transparent; color: var(--lla-text-dim); cursor: pointer; font-size: 16px; line-height: 1; padding: 0 4px; border-radius: 50%; }
    .week-chip-x:hover { color: var(--lla-danger); }
    .week-select { padding: 8px 10px; }
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
    /* Above .bottom-nav (z-index 30) so a modal and its backdrop cover the tab
       bar — otherwise the fixed nav paints over the bottom of the card and hides
       actions like "Add to list". */
    .overlay-shell { position: fixed; inset: 0; background: rgba(3, 8, 14, 0.58); backdrop-filter: blur(4px); z-index: 40; display: flex; align-items: center; justify-content: center; padding: 24px; }
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
    .btn.compact { padding: 6px 12px; font-size: 13px; }
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
    .category-check-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin-top: 10px; }
    .category-check {
      display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px;
      border: 1px solid var(--lla-border); background: var(--lla-surface-2); cursor: pointer; font-weight: 600;
    }
    .category-check input[type="checkbox"] { width: 20px; height: 20px; flex: 0 0 auto; accent-color: var(--accent); }
    .category-check.on { border-color: color-mix(in srgb, var(--accent) 45%, var(--lla-border)); background: color-mix(in srgb, var(--accent) 10%, var(--lla-surface-2)); }
    .category-chip-grid { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
    .category-chip-card { display: flex; align-items: center; gap: 8px; border: 1px solid var(--lla-border); background: var(--lla-surface-2); border-radius: 16px; padding: 8px 10px; }
    .chip-actions { display: flex; gap: 6px; }
    .chip-icon-btn { width: 28px; height: 28px; border-radius: 999px; border: 1px solid var(--lla-border); background: color-mix(in srgb, var(--accent) 18%, var(--lla-surface-2)); color: var(--lla-text); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0; font-size: 14px; line-height: 1; }
    .chip-icon-btn.danger { background: color-mix(in srgb, var(--lla-danger) 30%, var(--lla-surface-2)); border-color: var(--lla-danger); }
    .hero-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    .divider { height: 1px; background: var(--lla-border); margin: 16px 0; }
    .error { color: var(--lla-danger); font-weight: 600; }
    .undo-toast {
      position: fixed; left: 50%; bottom: 92px; transform: translateX(-50%);
      background: var(--lla-surface); color: var(--lla-text); border: 1px solid var(--lla-border);
      border-radius: 14px; padding: 10px 14px; display: flex; align-items: center; gap: 12px;
      box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4); z-index: 40;
    }
    .undo-toast .btn { padding: 6px 12px; }
    .shopping { max-width: 720px; margin: 0 auto; padding: 10px 12px 40px; min-height: 100%; --accent: #2c78ba; }
    .shop-bar { display: flex; align-items: center; gap: 10px; position: sticky; top: 0; z-index: 5; padding: 8px 0; background: var(--lla-bg-1); }
    .shop-done { padding: 10px 14px; }
    .shop-heading { flex: 1; text-align: center; min-width: 0; }
    .shop-title { font-size: 18px; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .shop-progress { height: 6px; border-radius: 999px; background: var(--lla-surface-2); overflow: hidden; margin: 4px 2px 14px; }
    .shop-progress-fill { height: 100%; background: var(--accent); transition: width 220ms ease; }
    .shop-add { display: flex; gap: 8px; margin-bottom: 16px; }
    .shop-section { margin-bottom: 14px; }
    .shop-cat { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%;
      background: transparent; border: none; text-align: left; cursor: pointer; font: inherit;
      font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--lla-text-dim); padding: 8px 4px 6px; }
    .shop-cat-chevron { transition: transform 160ms ease; font-size: 12px; }
    .shop-cat-chevron.collapsed { transform: rotate(-90deg); }
    .shop-item { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; background: var(--lla-surface-2); border: 1px solid var(--lla-border); border-radius: 12px; padding: 10px 12px; margin-bottom: 6px; color: var(--lla-text); font: inherit; font-size: 16px; cursor: pointer; transition: transform 80ms ease, opacity 120ms ease; }
    .shop-item:active { transform: scale(0.99); }
    .shop-check { width: 22px; height: 22px; flex: 0 0 22px; border-radius: 50%; border: 2px solid color-mix(in srgb, var(--accent) 70%, var(--lla-border)); }
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
