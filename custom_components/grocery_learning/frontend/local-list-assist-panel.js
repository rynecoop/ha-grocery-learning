import { categoryDisplay as displayCategory, createListLocal as applyCreateListLocal, deleteArchivedListLocal as applyDeleteArchivedListLocal, groupTitle as deriveGroupTitle, moveItemToCompleted as applyMoveItemToCompleted, recategorizeItemLocal as applyRecategorizeItemLocal, renameListLocal as applyRenameListLocal, switchListLocal as applySwitchListLocal, updateItemLocal as applyUpdateItemLocal } from "./state-helpers.js";

const TEMPLATE_LABELS = {
  flat: "Flat List",
  grocery: "Grocery",
  todo: "To-do",
  camping: "Camping",
  travel: "Travel",
};

class LocalListAssistPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._state = null;
    this._configOpen = false;
    this._createListOpen = false;
    this._listSettingsOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
    this._view = "list";
    this._loading = false;
    this._error = "";
    this._chipLongPressTimer = null;
    this._suppressNextChipClick = "";
    this._appToolsOpen = false;
    this._listToolsOpen = false;
    this._categoryRenameDrafts = {
      activeListCategories: {},
    };
    this._drafts = {
      quickAdd: "",
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
    this._focusTarget = "";
    this._openEditorKey = "";
    this._pendingRender = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this.load();
    } else {
      this.requestRender();
    }
  }

  set panel(panel) {
    this._panel = panel;
    this.requestRender();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this.requestRender();
  }

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

  async load(forceRender = false) {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    try {
      this._state = await this.api("dashboard");
      this.syncDrafts();
      this._error = "";
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._loading = false;
      this.requestRender(forceRender);
    }
  }

  async act(payload) {
    const result = await this.api("action", "POST", payload);
    if (result?.dashboard && typeof result.dashboard === "object") {
      this._state = result.dashboard;
      this.syncDrafts();
      this._error = "";
      this.requestRender(true);
      return result;
    }
    await this.load(true);
    return result;
  }

  async actFast(payload, updater = null) {
    const result = await this.api("action", "POST", payload);
    if (result?.dashboard && typeof result.dashboard === "object") {
      this._state = result.dashboard;
      this.syncDrafts();
      this._error = "";
      this.render();
      return result;
    }
    if (typeof updater === "function" && this._state) {
      updater(this._state);
      this.syncDrafts();
      this.requestRender();
      return result;
    }
    await this.load();
    return result;
  }

  updateDraft(key, value) {
    this._drafts[key] = value;
  }

  isInteractive() {
    return Boolean(
      this._focusTarget ||
      this._openEditorKey ||
      this._configOpen ||
      this._createListOpen ||
      this._listSettingsOpen ||
      this._menuOpen ||
      this._reorderListId
    );
  }

  requestRender(force = false) {
    if (!force && this.isInteractive()) {
      this._pendingRender = true;
      return;
    }
    this._pendingRender = false;
    this.render();
  }

  flushPendingRender() {
    if (this._pendingRender && !this.isInteractive()) {
      this._pendingRender = false;
      this.render();
    }
  }

  rememberFocus(target) {
    this._focusTarget = target || "";
  }

  restoreFocus() {
    if (!this._focusTarget) return;
    const element = this.shadowRoot?.getElementById(this._focusTarget);
    if (!element) return;
    requestAnimationFrame(() => {
      try {
        element.focus();
        if (typeof element.value === "string" && typeof element.setSelectionRange === "function") {
          const end = element.value.length;
          element.setSelectionRange(end, end);
        }
      } catch (_err) {}
    });
  }

  openNavigation() {
    const toggleEvent = new CustomEvent("hass-toggle-menu", {
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(toggleEvent);
    window.dispatchEvent(toggleEvent);

    const homeAssistant = document.querySelector("home-assistant");
    const root = homeAssistant?.shadowRoot;
    const main = root?.querySelector("home-assistant-main");
    if (main && typeof main._toggleSidebar === "function") {
      main._toggleSidebar();
      return;
    }
    if (window.history.length > 1) {
      window.history.back();
    }
  }

  esc(value) {
    return String(value ?? "").replace(/[&<>"]/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
    }[char]));
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
    const next = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
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
    const next = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
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

  categoryEditorMarkup(key, label, placeholder, helper = "") {
    const values = this.parseCategoryDraft(key);
    const chips = values.length
      ? values
          .map((category, index) => `
            <div class="category-chip-card">
              <span class="pill ghost-pill">${this.esc(this.categoryDisplay(category))}</span>
              <div class="chip-actions">
                <button class="chip-icon-btn edit-chip-btn" data-chip-edit="${this.esc(key)}:${index}" aria-label="Edit category" title="Edit category">&#9998;</button>
                <button class="chip-icon-btn" data-chip-move="${this.esc(key)}:${index}:-1" aria-label="Move category left">↑</button>
                <button class="chip-icon-btn" data-chip-move="${this.esc(key)}:${index}:1" aria-label="Move category right">↓</button>
                <button class="chip-icon-btn danger" data-chip-remove="${this.esc(key)}:${index}" aria-label="Remove category">×</button>
              </div>
            </div>
          `)
          .join("")
      : `<div class="empty">${this.esc(helper || "No categories added yet.")}</div>`;
    return `
      <div class="category-editor">
        <div class="label">${this.esc(label)}</div>
        <div class="row category-add-row">
          <input id="${this.esc(key)}Input" class="input" placeholder="${this.esc(placeholder)}" />
          <button class="btn" data-chip-add="${this.esc(key)}">Add Category</button>
        </div>
        <div class="category-chip-grid">${chips}</div>
      </div>
    `;
  }

  closePanels() {
    this._configOpen = false;
    this._createListOpen = false;
    this._listSettingsOpen = false;
    this._menuOpen = false;
    this._reorderListId = "";
    this._appToolsOpen = false;
    this._listToolsOpen = false;
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
    this.requestRender(true);
  }

  moveItemToCompleted(itemRef) {
    applyMoveItemToCompleted(this._state, itemRef);
  }

  recategorizeItemLocal(itemRef, targetCategory) {
    applyRecategorizeItemLocal(this._state, itemRef, targetCategory);
  }

  updateItemLocal(itemRef, summary, targetCategory) {
    applyUpdateItemLocal(this._state, itemRef, { summary, targetCategory });
  }

  switchListLocal(listId) {
    return applySwitchListLocal(this._state, listId);
  }

  itemMarkup(item, categories) {
    const editorKey = this.editorKey(item);
    const summaryDraft = this._drafts[`summary:${editorKey}`] ?? item.summary ?? "";
    const selectedCategory = this._drafts[`category:${editorKey}`] || item.category || "";
    const editorOpen = this._openEditorKey === editorKey;
    const options = categories
      .map((cat) => `<option value="${this.esc(cat)}" ${cat === selectedCategory ? "selected" : ""}>${this.esc(cat)}</option>`)
      .join("");
    return `
      <div class="item" data-editor-key="${this.esc(editorKey)}" data-list-entity="${this.esc(item.list_entity)}" data-item-ref="${this.esc(item.item_ref)}">
        <div class="item-main">
          <div class="item-summary">
            <input class="complete-toggle" type="checkbox" />
            <strong>${this.esc(item.summary)}</strong>
          </div>
          <span class="pill">${this.esc(item.category_display)}</span>
        </div>
        <div class="small">${this.esc(item.description || "")}</div>
        <div class="editor ${editorOpen ? "open" : ""}">
          <input id="summary-${this.esc(editorKey)}" class="input edit-summary" data-draft="summary:${this.esc(editorKey)}" value="${this.esc(summaryDraft)}" />
          <select id="editor-${this.esc(editorKey)}" class="select cat-select" data-draft="category:${this.esc(editorKey)}">${options}</select>
          <button class="btn save-item-btn">Save</button>
        </div>
      </div>
    `;
  }

  completedItemMarkup(item) {
    const editorKey = this.editorKey(item);
    const summaryDraft = this._drafts[`summary:${editorKey}`] ?? item.summary ?? "";
    const editorOpen = this._openEditorKey === editorKey;
    return `
      <div class="item completed-item" data-editor-key="${this.esc(editorKey)}" data-list-entity="${this.esc(item.list_entity)}" data-item-ref="${this.esc(item.item_ref)}" data-completed-item="true">
        <div class="item-main completed-main">
          <label class="completed-row"><input class="completed-toggle" data-item-ref="${this.esc(item.item_ref)}" type="checkbox" checked /> <strong>${this.esc(item.summary)}</strong></label>
        </div>
        <div class="small meta-line">${this.esc(item.description || "")}</div>
        <div class="editor ${editorOpen ? "open" : ""}">
          <input id="summary-${this.esc(editorKey)}" class="input edit-summary" data-draft="summary:${this.esc(editorKey)}" value="${this.esc(summaryDraft)}" />
          <button class="btn save-completed-item-btn">Save</button>
        </div>
      </div>
    `;
  }

  bindEvents() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-close-overlay]").forEach((el) => {
      el.addEventListener("click", () => {
        this.closePanels();
        this.requestRender(true);
      });
    });
    root.querySelectorAll(".modal-card,.side-drawer").forEach((el) => {
      el.addEventListener("click", (ev) => ev.stopPropagation());
    });
    root.querySelectorAll("[data-chip-add]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.chipAdd || "";
        const input = root.querySelector(`#${key}Input`);
        if (!input) return;
        if (this.addCategoryDraft(key, input.value || "")) {
          input.value = "";
          this.requestRender(true);
        }
      });
    });
    root.querySelectorAll("[data-chip-move]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [key, index, direction] = String(btn.dataset.chipMove || "").split(":");
        this.moveCategoryDraft(key, Number(index), Number(direction));
        this.requestRender(true);
      });
    });
    root.querySelectorAll("[data-chip-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [key, index] = String(btn.dataset.chipEdit || "").split(":");
        const current = this.parseCategoryDraft(key);
        const existing = current[Number(index)] || "";
        if (!existing) return;
        const nextValue = window.prompt("Edit category", existing.replace(/_/g, " "));
        if (nextValue == null) return;
        if (this.renameCategoryDraft(key, Number(index), nextValue)) {
          this.requestRender(true);
        }
      });
    });
    root.querySelectorAll("[data-chip-remove]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [key, index] = String(btn.dataset.chipRemove || "").split(":");
        this.removeCategoryDraft(key, Number(index));
        this.requestRender(true);
      });
    });
    root.querySelectorAll(".category-editor .input").forEach((input) => {
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          root.querySelector(`[data-chip-add="${input.id.replace(/Input$/, "")}"]`)?.click();
        }
      });
    });
    root.querySelector("#appToolsDetails")?.addEventListener("toggle", (ev) => {
      this._appToolsOpen = !!ev.target.open;
    });
    root.querySelector("#listToolsDetails")?.addEventListener("toggle", (ev) => {
      this._listToolsOpen = !!ev.target.open;
    });
    root.querySelector("#menuBtn")?.addEventListener("click", () => {
      this.openNavigation();
    });
    root.querySelector("#addBtn")?.addEventListener("click", async () => {
      const input = root.querySelector("#quickAdd");
      const item = (this._drafts.quickAdd || input?.value || "").trim();
      if (!item) return;
      this._drafts.quickAdd = "";
      this._focusTarget = "quickAdd";
      if (input) input.value = "";
      await this.act({
        action: "add_item",
        item,
        actor_user_id: this._hass?.user?.id || "",
        actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
      });
    });
    root.querySelector("#quickAdd")?.addEventListener("keydown", async (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        root.querySelector("#addBtn")?.click();
      }
    });
    root.querySelector("#quickAdd")?.addEventListener("focus", () => {
      this.rememberFocus("quickAdd");
    });
    root.querySelector("#quickAdd")?.addEventListener("blur", () => {
      if (this._focusTarget === "quickAdd") {
        requestAnimationFrame(() => {
          const active = this.shadowRoot?.activeElement;
          if (!active || active.id !== "quickAdd") {
            this._focusTarget = "";
            this.flushPendingRender();
          }
        });
      }
    });
    root.querySelector("#settingsBtn")?.addEventListener("click", () => {
      this._configOpen = !this._configOpen;
      this._createListOpen = false;
      this._listSettingsOpen = false;
      this._menuOpen = false;
      this._reorderListId = "";
      this.requestRender(true);
    });
    root.querySelector("#menuToggleBtn")?.addEventListener("click", () => {
      this._menuOpen = !this._menuOpen;
      this.requestRender(true);
    });
    root.querySelector("#heroCreateListBtn")?.addEventListener("click", () => {
      this._createListOpen = !this._createListOpen;
      this._configOpen = false;
      this._listSettingsOpen = false;
      this._menuOpen = false;
      this._reorderListId = "";
      this.requestRender(true);
    });
    root.querySelector("#refreshBtn")?.addEventListener("click", async () => {
      this._focusTarget = "";
      this._openEditorKey = "";
      await this.load(true);
    });
    root.querySelector("#clearCompletedBtn")?.addEventListener("click", async () => {
      await this.actFast({ action: "clear_completed" }, (state) => {
        state.completed = [];
      });
    });
    root.querySelector("#saveSettingsBtn")?.addEventListener("click", async () => {
      const nextDashboardName = (this._drafts.dashboardName || "Local List Assist").trim() || "Local List Assist";
      const previousDashboardName = this._state?.settings?.dashboard_name || "Local List Assist";
      await this.act({
        action: "save_settings",
        dashboard_name: nextDashboardName,
        categories: this._drafts.settingsCategories || "",
        default_grocery_categories: !!root.querySelector("#settingsDefaultGroceryCategories")?.checked,
        debug_mode: !!root.querySelector("#settingsDebugMode")?.checked,
      });
      if (this._panel) {
        this._panel = {
          ...this._panel,
          title: nextDashboardName,
          config: {
            ...(this._panel.config || {}),
            title: nextDashboardName,
          },
        };
      }
      document.title = nextDashboardName;
      this.closePanels();
      if (nextDashboardName !== previousDashboardName) {
        window.setTimeout(() => window.location.reload(), 450);
      }
    });
    root.querySelector("#repairBtn")?.addEventListener("click", async () => {
      await this.act({ action: "repair_system" });
    });
    root.querySelector("#installVoiceBtn")?.addEventListener("click", async () => {
      await this.act({ action: "install_voice_sentences", language: "en" });
    });
    root.querySelector("#activityToggleBtn")?.addEventListener("click", () => {
      this._view = this._view === "activity" ? "list" : "activity";
      this.closePanels();
      this.requestRender(true);
    });
    root.querySelector("#activeListSettingsBtn")?.addEventListener("click", () => {
      this._listSettingsOpen = !this._listSettingsOpen;
      this._configOpen = false;
      this._createListOpen = false;
      this._menuOpen = false;
      this._reorderListId = "";
      this.requestRender(true);
    });
    root.querySelector("#cancelCreateListBtn")?.addEventListener("click", () => {
      this.closePanels();
      this.requestRender(true);
    });
    root.querySelector("#closeReorderBtn")?.addEventListener("click", () => {
      this.closePanels();
      this.requestRender(true);
    });
    root.querySelector("#dupAddBtn")?.addEventListener("click", async () => {
      await this.act({
        action: "confirm_duplicate",
        decision: "add",
        actor_user_id: this._hass?.user?.id || "",
        actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
      });
    });
    root.querySelector("#dupSkipBtn")?.addEventListener("click", async () => {
      await this.act({
        action: "confirm_duplicate",
        decision: "skip",
        actor_user_id: this._hass?.user?.id || "",
        actor_name: this._hass?.user?.display_name || this._hass?.user?.name || "",
      });
    });
    root.querySelectorAll(".review-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await this.act({ action: "apply_review", category: btn.dataset.category || "", learn: true });
      });
    });
    root.querySelector("#keepOtherBtn")?.addEventListener("click", async () => {
      await this.act({ action: "apply_review", category: "other", learn: false });
    });
    root.querySelector("#createListBtn")?.addEventListener("click", async () => {
      const name = (this._drafts.newListName || "").trim();
      if (!name) return;
      const template = this._drafts.newListTemplate || "flat";
      const categories = this._drafts.newListCategories || "";
      const voiceAliases = this._drafts.newListVoiceAliases || "";
      const listId = name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "") || "list";
      const nextColor = "#" + ((Array.from(listId).reduce((sum, char) => sum + char.charCodeAt(0), 0) % 0xffffff).toString(16).padStart(6, "0"));
      await this.actFast({ action: "create_list", name, template, categories, voice_aliases: voiceAliases }, (state) => {
        applyCreateListLocal(state, { id: listId, name, color: nextColor });
      });
      this._drafts.newListName = "";
      this._drafts.newListTemplate = "flat";
      this._drafts.newListCategories = "";
      this._drafts.newListVoiceAliases = "";
      this.closePanels();
      this.requestRender(true);
    });
    root.querySelector("#newListTemplate")?.addEventListener("change", (ev) => {
      const templateId = ev.target.value || "flat";
      this.updateDraft("newListTemplate", templateId);
      const presets = this._state?.settings?.template_presets || {};
      const categories = (presets[templateId] || []).join(", ");
      this.updateDraft("newListCategories", categories);
      this.requestRender(true);
    });
    root.querySelector("#archiveListBtn")?.addEventListener("click", async () => {
      const listId = this._state?.system?.active_list_id || "";
      if (!listId) return;
      await this.act({ action: "archive_list", list_id: listId });
    });
    root.querySelectorAll(".restore-archive-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await this.act({ action: "restore_archived_list", list_id: btn.dataset.listId || "" });
      });
    });
    root.querySelector("#pinListBtn")?.addEventListener("click", async () => {
      const listId = this._state?.system?.active_list_id || "";
      if (!listId || listId === "default") return;
      await this.act({ action: "reorder_list", list_id: listId, direction: "pin" });
    });
    root.querySelector("#moveListLeftBtn")?.addEventListener("click", async () => {
      const listId = this._state?.system?.active_list_id || "";
      if (!listId || listId === "default") return;
      await this.act({ action: "reorder_list", list_id: listId, direction: "left" });
    });
    root.querySelector("#moveListRightBtn")?.addEventListener("click", async () => {
      const listId = this._state?.system?.active_list_id || "";
      if (!listId || listId === "default") return;
      await this.act({ action: "reorder_list", list_id: listId, direction: "right" });
    });
    root.querySelectorAll(".delete-archive-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const listId = btn.dataset.listId || "";
        await this.actFast({ action: "delete_archived_list", list_id: listId }, (state) => {
          applyDeleteArchivedListLocal(state, listId);
        });
      });
    });
    root.querySelector("#saveActiveListBtn")?.addEventListener("click", async () => {
      const listId = this._state?.system?.active_list_id || "";
      if (!listId) return;
      const nextName = (this._drafts.activeListName || "").trim();
      await this.act({
        action: "save_active_list",
        list_id: listId,
        name: nextName,
        categories: this._drafts.activeListCategories || "",
        renamed_categories: this._categoryRenameDrafts.activeListCategories || {},
        voice_aliases: this._drafts.activeListVoiceAliases || "",
        color: this._drafts.activeListColor || "#2c78ba",
      });
      this._categoryRenameDrafts.activeListCategories = {};
      this.closePanels();
      this.requestRender(true);
    });
    root.querySelector("#clearListCatsBtn")?.addEventListener("click", () => {
      this._categoryRenameDrafts.activeListCategories = {};
      this.updateDraft("activeListCategories", "");
      this.requestRender(true);
    });

    root.querySelectorAll("[data-draft]").forEach((input) => {
      input.addEventListener("input", (ev) => {
        this.updateDraft(input.dataset.draft, ev.target.value);
      });
      input.addEventListener("focus", () => {
        if (input.id) this.rememberFocus(input.id);
      });
      input.addEventListener("blur", () => {
        if (this._focusTarget === input.id) {
          requestAnimationFrame(() => {
            const active = this.shadowRoot?.activeElement;
            if (!active || active.id !== input.id) {
              this._focusTarget = "";
              this.flushPendingRender();
            }
          });
        }
      });
    });

    root.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && (this._configOpen || this._createListOpen || this._listSettingsOpen || this._menuOpen || this._reorderListId)) {
        this.closePanels();
        this.requestRender(true);
      }
    });

    root.querySelectorAll(".item").forEach((row) => {
      if (row.dataset.completedItem === "true") {
        return;
      }
      const editorKey = row.dataset.editorKey || "";
      const listEntity = row.dataset.listEntity || "";
      const itemRef = row.dataset.itemRef || "";
      const editor = row.querySelector(".editor");
      row.querySelector(".item-main")?.addEventListener("click", () => {
        const currentSummary = row.querySelector("strong")?.textContent || "";
        const currentCategory = row.querySelector(".cat-select")?.value || "";
        this._drafts[`summary:${editorKey}`] = this._drafts[`summary:${editorKey}`] ?? currentSummary;
        this._drafts[`category:${editorKey}`] = this._drafts[`category:${editorKey}`] ?? currentCategory;
        const nextOpen = this._openEditorKey === editorKey ? "" : editorKey;
        this._openEditorKey = nextOpen;
        this._focusTarget = nextOpen ? `summary-${editorKey}` : "";
        this.requestRender(true);
      });
      row.querySelector(".complete-toggle")?.addEventListener("click", (ev) => ev.stopPropagation());
      row.querySelector(".complete-toggle")?.addEventListener("change", async (ev) => {
        if (ev.target.checked) {
          this._openEditorKey = "";
          this._focusTarget = "";
          await this.actFast({ action: "set_status", list_entity: listEntity, item: itemRef, status: "completed" }, () => {
            this.moveItemToCompleted(itemRef);
          });
        }
      });
      row.querySelector(".save-item-btn")?.addEventListener("click", async () => {
        const nextSummary = (this._drafts[`summary:${editorKey}`] || row.querySelector(".edit-summary")?.value || "").trim();
        const target = this._drafts[`category:${editorKey}`] || row.querySelector(".cat-select")?.value || "";
        if (!target || !nextSummary) return;
        this._openEditorKey = "";
        this._focusTarget = "";
        await this.actFast({ action: "update_item", list_entity: listEntity, item: itemRef, summary: nextSummary, target_category: target, learn: true }, () => {
          this.updateItemLocal(itemRef, nextSummary, target);
        });
      });
      row.querySelector(".edit-summary")?.addEventListener("click", (ev) => ev.stopPropagation());
      row.querySelector(".edit-summary")?.addEventListener("keydown", async (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          row.querySelector(".save-item-btn")?.click();
        }
      });
      row.querySelector(".cat-select")?.addEventListener("click", (ev) => ev.stopPropagation());
      row.querySelector(".cat-select")?.addEventListener("change", (ev) => ev.stopPropagation());
      row.querySelector(".save-item-btn")?.addEventListener("click", (ev) => ev.stopPropagation());
    });

    root.querySelectorAll(".completed-toggle").forEach((el) => {
      el.addEventListener("change", async (ev) => {
        if (!ev.target.checked) {
          await this.act({ action: "set_status", list_entity: "todo.grocery_completed", item: el.dataset.itemRef || "", status: "needs_action" });
        }
      });
      el.addEventListener("click", (ev) => ev.stopPropagation());
    });

    root.querySelectorAll('[data-completed-item="true"]').forEach((row) => {
      const editorKey = row.dataset.editorKey || "";
      const listEntity = row.dataset.listEntity || "";
      const itemRef = row.dataset.itemRef || "";
      row.querySelector(".completed-main")?.addEventListener("click", () => {
        const currentSummary = row.querySelector("strong")?.textContent || "";
        this._drafts[`summary:${editorKey}`] = this._drafts[`summary:${editorKey}`] ?? currentSummary;
        const nextOpen = this._openEditorKey === editorKey ? "" : editorKey;
        this._openEditorKey = nextOpen;
        this._focusTarget = nextOpen ? `summary-${editorKey}` : "";
        this.requestRender(true);
      });
      row.querySelector(".edit-summary")?.addEventListener("click", (ev) => ev.stopPropagation());
      row.querySelector(".edit-summary")?.addEventListener("keydown", async (ev) => {
        if (ev.key === "Enter") {
          ev.preventDefault();
          row.querySelector(".save-completed-item-btn")?.click();
        }
      });
      row.querySelector(".save-completed-item-btn")?.addEventListener("click", async (ev) => {
        ev.stopPropagation();
        const nextSummary = (this._drafts[`summary:${editorKey}`] || row.querySelector(".edit-summary")?.value || "").trim();
        if (!nextSummary) return;
        this._openEditorKey = "";
        this._focusTarget = "";
        await this.actFast({ action: "update_item", list_entity: listEntity, item: itemRef, summary: nextSummary }, () => {
          this.updateItemLocal(itemRef, nextSummary, "");
        });
      });
    });
  }

  render() {
    const state = this._state;
    this.syncDrafts();
    const multilist = !!state?.settings?.experimental_multilist;
    const dashboardName = state?.settings?.dashboard_name || "Local List Assist";
    const active = state?.lists?.find((list) => list.active) || null;
    const activeListName = active?.name || "Grocery List";
    const activeListColor = state?.system?.active_list_color || active?.color || "#2c78ba";
    const visibleGroups = (state?.groups || []).filter((group) => (group.items || []).length > 0);
    const groups = visibleGroups
      .map((group) => {
        const items = group.items?.length
          ? group.items.map((item) => this.itemMarkup(item, state.categories || [])).join("")
          : `<div class="empty">No items.</div>`;
        return `<section class="section"><div class="title">${this.esc(group.title)}</div>${items}</section>`;
      })
      .join("");
    const attention = [];
    if (state?.pending_duplicate?.pending) {
      attention.push(`
        <section class="section">
          <div class="title">Duplicate Needs Decision</div>
          <div class="small">${this.esc(state.pending_duplicate.item)} is already in ${this.esc(state.pending_duplicate.target)}.</div>
          <div class="row">
            <button id="dupAddBtn" class="btn primary">Add Anyway</button>
            <button id="dupSkipBtn" class="btn">Skip</button>
          </div>
        </section>
      `);
    }
    if (state?.pending_review?.pending) {
      const reviewButtons = (state.categories || [])
        .map((cat) => `<button class="btn review-btn" data-category="${this.esc(cat)}">${this.esc(cat.replaceAll("_", " "))}</button>`)
        .join("");
      attention.push(`
        <section class="section">
          <div class="title">Review Needed</div>
          <div class="small">Item: <strong>${this.esc(state.pending_review.item)}</strong> (${this.esc(state.pending_review.source_list)})</div>
          <div class="row">${reviewButtons}<button id="keepOtherBtn" class="btn">Keep Other</button></div>
        </section>
      `);
    }
    const activity = (state?.activity || []).length
      ? state.activity
          .map((entry) => `<div class="item activity-item"><strong>${this.esc(entry.title)}</strong><div class="small meta-line">${this.esc(entry.detail)}${entry.list_name ? ` | ${this.esc(entry.list_name)}` : ""}${entry.source ? ` | ${this.esc(entry.source)}` : ""}${entry.when ? ` | ${this.esc(entry.when)}` : ""}</div></div>`)
          .join("")
      : `<div class="empty">No recent activity.</div>`;
    const completed = (state?.completed || []).length
      ? state.completed
          .map((item) => this.completedItemMarkup(item))
          .join("")
      : `<div class="empty">No completed items.</div>`;
    const listChips = (state?.lists || [])
      .map((list) => `<button class="list-chip ${list.active ? "active" : ""}" data-list-id="${this.esc(list.id)}" style="--chip-color:${this.esc(list.color || "#2c78ba")}">${this.esc(list.name)}</button>`)
      .join("");
    const archivedLists = (state?.archived_lists || []).length
      ? state.archived_lists
          .map((list) => `
            <div class="item">
              <strong>${this.esc(list.name)}</strong>
              <div class="row">
                <button class="btn restore-archive-btn" data-list-id="${this.esc(list.id)}">Restore</button>
                <button class="btn danger delete-archive-btn" data-list-id="${this.esc(list.id)}">Delete</button>
              </div>
            </div>
          `)
          .join("")
      : `<div class="empty">No archived lists.</div>`;
    const currentListLabel = this.esc(activeListName || "Grocery List");
    const templatePresets = state?.settings?.template_presets || {};
    const templateIds = Array.from(new Set([...Object.keys(TEMPLATE_LABELS), ...Object.keys(templatePresets)]));
    const activeCategories = (state?.system?.active_list_categories || []).filter(Boolean);
    const appSettingsPanel = this._configOpen
      ? `
        <div class="overlay-shell" data-close-overlay="true">
          <section class="modal-card" role="dialog" aria-label="App settings">
          <div class="modal-head">
            <div>
              <div class="title">Settings</div>
              <div class="small">Local-only mode. Lists, learned terms, dashboards, and routing stay inside Home Assistant.</div>
            </div>
            <button class="btn icon-btn compact" data-close-overlay="true" aria-label="Close settings">×</button>
          </div>
          <div class="subsection">
            <div class="section-label">Local App</div>
            <div class="grid compact-grid">
              <div>
                <div class="label">Dashboard name</div>
                <input id="settingsDashboardName" data-draft="dashboardName" class="input" value="${this.esc(this._drafts.dashboardName || dashboardName)}" />
                <div class="small">Used for the HA sidebar and generated dashboards. The panel refreshes after save.</div>
              </div>
            </div>
            ${this.categoryEditorMarkup("settingsCategories", "Default list categories", "Add a default category", "Add the categories new local lists should start with.")}
            <div class="row">
              <button id="saveSettingsBtn" class="btn primary">Save</button>
            </div>
            <details id="appToolsDetails" class="advanced-box" ${this._appToolsOpen ? "open" : ""}>
              <summary>Tools</summary>
              <div class="row advanced-row">
                <button id="installVoiceBtn" class="btn">Install Voice Phrases</button>
                <button id="repairBtn" class="btn">Repair Local Setup</button>
                <label class="toggle-row"><input id="settingsDebugMode" type="checkbox" ${state?.settings?.debug_mode ? "checked" : ""}/> Debug mode</label>
              </div>
            </details>
          </div>
          </section>
        </div>
      `
      : "";
    const createListPanel = this._createListOpen && multilist
      ? `
        <div class="overlay-shell" data-close-overlay="true">
          <section class="modal-card" role="dialog" aria-label="Create list">
          <div class="modal-head">
            <div>
              <div class="title">Create List</div>
              <div class="small">Use the plus button for a new local list, just like the Android app.</div>
            </div>
            <button class="btn icon-btn compact" data-close-overlay="true" aria-label="Close create list">×</button>
          </div>
          <div class="grid compact-grid">
            <input id="newListName" data-draft="newListName" class="input" placeholder="New list name" value="${this.esc(this._drafts.newListName || "")}" />
            <select id="newListTemplate" data-draft="newListTemplate" class="select">
              ${templateIds.map((templateId) => `<option value="${this.esc(templateId)}" ${this._drafts.newListTemplate === templateId ? "selected" : ""}>${this.esc(TEMPLATE_LABELS[templateId] || templateId)}</option>`).join("")}
            </select>
            <input id="newListVoiceAliases" data-draft="newListVoiceAliases" class="input" placeholder="Optional voice aliases (comma separated)" value="${this.esc(this._drafts.newListVoiceAliases || "")}" />
          </div>
          ${this.categoryEditorMarkup("newListCategories", "List categories", "Add a category for this list", "Leave it empty to use the selected template defaults.")}
          <div class="row">
            <button id="createListBtn" class="btn primary">Create List</button>
            <button id="cancelCreateListBtn" class="btn">Cancel</button>
          </div>
          </section>
        </div>
      `
      : "";
    const listSettingsPanel = this._listSettingsOpen && multilist
      ? `
        <div class="overlay-shell" data-close-overlay="true">
          <section class="modal-card" role="dialog" aria-label="List settings">
          <div class="modal-head">
            <div>
              <div class="title">List Settings</div>
              <div class="small">Tap the active list to manage it. Long-press on touch devices or right-click on desktop to reorder list chips.</div>
            </div>
            <button class="btn icon-btn compact" data-close-overlay="true" aria-label="Close list settings">×</button>
          </div>
          <div class="subsection">
            <div class="section-label">Current List</div>
            <div class="small">Editing ${currentListLabel}</div>
            <div class="grid compact-grid">
              <div>
                <div class="label">List name</div>
                <input id="activeListName" data-draft="activeListName" class="input" placeholder="List name" value="${this.esc(this._drafts.activeListName || activeListName)}" />
              </div>
              <div>
                <div class="label">List color</div>
                <input id="activeListColor" data-draft="activeListColor" class="color-input" type="color" value="${this.esc(this._drafts.activeListColor || activeListColor)}" />
              </div>
            </div>
            ${this.categoryEditorMarkup("activeListCategories", "List categories", "Add a category for this list", activeCategories.length ? "" : "No categories yet. Add only the sections this list needs.")}
            <details id="listToolsDetails" class="advanced-box" ${this._listToolsOpen ? "open" : ""}>
              <summary>Advanced List Tools</summary>
              <div class="grid compact-grid" style="margin-top:12px;">
                <div>
                  <div class="label">Voice aliases</div>
                  <input id="activeListVoiceAliases" data-draft="activeListVoiceAliases" class="input" placeholder="Optional voice aliases" value="${this.esc(this._drafts.activeListVoiceAliases || "")}" />
                </div>
              </div>
            </details>
            <div class="row">
              <button id="saveActiveListBtn" class="btn primary">Save List</button>
              <button id="clearListCatsBtn" class="btn">No Categories</button>
              <button id="archiveListBtn" class="btn danger">Archive List</button>
            </div>
          </div>
          <div class="divider"></div>
          <div class="subsection">
            <div class="section-label">Archived Local Lists</div>
            ${archivedLists}
          </div>
          </section>
        </div>
      `
      : "";
    const reorderTarget = (state?.lists || []).find((list) => list.id === this._reorderListId) || null;
    const reorderPanel = reorderTarget && multilist
      ? `
        <div class="overlay-shell" data-close-overlay="true">
          <section class="modal-card modal-card-narrow" role="dialog" aria-label="Reorder list">
          <div class="modal-head">
            <div>
              <div class="title">Reorder ${this.esc(reorderTarget.name)}</div>
              <div class="small">This follows the Android flow: press and hold on phones and tablets, or right-click on desktop.</div>
            </div>
            <button class="btn icon-btn compact" data-close-overlay="true" aria-label="Close reorder">×</button>
          </div>
          <div class="row">
            <button id="pinListBtn" class="btn">Pin Near Front</button>
            <button id="moveListLeftBtn" class="btn">Move Left</button>
            <button id="moveListRightBtn" class="btn">Move Right</button>
            <button id="closeReorderBtn" class="btn">Done</button>
          </div>
          </section>
        </div>
      `
      : "";
    const actionMenu = this._menuOpen
      ? `
        <div class="overlay-shell overlay-drawer" data-close-overlay="true">
        <section class="side-drawer" role="dialog" aria-label="Menu">
          <div class="modal-head">
            <div class="section-label">Menu</div>
            <button class="btn icon-btn compact" data-close-overlay="true" aria-label="Close menu">×</button>
          </div>
          <div class="drawer-stack">
            <button id="activityToggleBtn" class="btn">${this._view === "activity" ? "Back to List" : "Activity"}</button>
            <button id="settingsBtn" class="btn">App Settings</button>
            ${multilist ? `<button id="activeListSettingsBtn" class="btn">List Settings</button>` : ""}
          </div>
        </section>
        </div>
      `
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-height:100%; background:linear-gradient(180deg,#0d1520,#09111a); color:#f3f7fb; --accent:${this.esc(activeListColor)}; }
        * { box-sizing:border-box; font-family: "Segoe UI", system-ui, sans-serif; }
        .wrap { max-width: 1120px; margin: 0 auto; padding: 20px; }
        .hero, .section { background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 12%, rgba(18,31,48,0.96)), rgba(18,31,48,0.92)); border:1px solid color-mix(in srgb, var(--accent) 38%, #203a57); border-radius: 24px; padding: 20px; margin-bottom: 16px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.03); }
        .title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
        .modal-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:12px; }
        .hero-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
        .hero-title { font-size: 28px; font-weight: 800; margin: 0 0 8px; }
        .sub, .small, .label, .empty { color:#9fb4ca; }
        .section-label { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
        .subsection { display:flex; flex-direction:column; gap:12px; }
        .row { display:flex; gap:10px; flex-wrap:wrap; margin-top: 10px; align-items:center; }
        .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
        .compact-grid { align-items:end; }
        .toggle-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }
        .toggle-row { display:flex; gap:8px; align-items:center; color:#d5e6f8; }
        .input, .select { width:100%; background:#08111b; color:#f3f7fb; border:1px solid #2e5276; border-radius:14px; padding: 12px 14px; }
        .color-input { width:100%; min-height:48px; background:#08111b; border:1px solid #2e5276; border-radius:14px; padding: 6px; }
        .btn { border:1px solid #416588; background:#27425f; color:#fff; border-radius:14px; padding: 12px 16px; cursor:pointer; }
        .btn.primary { background:var(--accent); border-color:color-mix(in srgb, var(--accent) 60%, white); }
        .btn.danger { background:#6a2d2d; border-color:#d96b6b; }
        .advanced-box { border:1px solid #29435f; border-radius:16px; padding:12px 14px; background:#0d1826; }
        .advanced-box summary { cursor:pointer; color:#d5e6f8; font-weight:600; }
        .advanced-row { margin-top:12px; }
        .overlay-shell { position:fixed; inset:0; background:rgba(3,8,14,0.58); backdrop-filter:blur(4px); z-index:30; display:flex; align-items:center; justify-content:center; padding:24px; }
        .overlay-drawer { justify-content:flex-end; padding:0; }
        .modal-card, .side-drawer { background:linear-gradient(180deg, rgba(18,31,48,0.98), rgba(12,22,34,0.98)); border:1px solid color-mix(in srgb, var(--accent) 42%, #28405a); border-radius:24px; box-shadow:0 24px 90px rgba(0,0,0,0.44); }
        .modal-card { width:min(760px, calc(100vw - 48px)); max-height:calc(100vh - 48px); overflow:auto; padding:20px; }
        .modal-card-narrow { width:min(560px, calc(100vw - 48px)); }
        .side-drawer { width:min(360px, 92vw); height:100vh; border-radius:0; padding:22px 18px; border-left:1px solid color-mix(in srgb, var(--accent) 42%, #28405a); }
        .drawer-stack { display:flex; flex-direction:column; gap:10px; }
        .mobile-bar { display:flex; align-items:center; gap:10px; margin-bottom: 12px; }
        .mobile-title { font-size:14px; font-weight:700; color:#9fb4ca; letter-spacing:0.04em; text-transform:uppercase; }
        .icon-btn { width:44px; height:44px; display:inline-flex; align-items:center; justify-content:center; font-size:20px; padding:0; }
        .icon-btn.compact { width:42px; height:42px; font-size:18px; flex:0 0 auto; }
        .list-chip-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
        .list-chip { border:1px solid color-mix(in srgb, var(--chip-color) 60%, #284766); background:color-mix(in srgb, var(--chip-color) 20%, #122132); color:#fff; border-radius:999px; padding:8px 12px; cursor:pointer; transition:transform 140ms ease, border-color 140ms ease, background 140ms ease; }
        .list-chip.active { box-shadow:0 0 0 1px rgba(255,255,255,0.12) inset; }
        .list-chip:hover { transform:translateY(-1px); }
        .item { background:#0d1826; border:1px solid #1f3348; border-radius:16px; padding: 12px; margin-bottom: 10px; }
        .activity-item, .completed-item { padding: 10px 12px; }
        .completed-row { display:flex; gap:10px; align-items:flex-start; }
        .meta-line { line-height:1.45; }
        .item-main { display:flex; justify-content:space-between; gap:10px; align-items:center; cursor:pointer; }
        .item-summary { display:flex; align-items:center; gap:10px; min-width:0; }
        .editor { display:none; gap:10px; margin-top:10px; }
        .editor.open { display:flex; }
        .pill { font-size:11px; padding:4px 10px; border-radius:999px; background:color-mix(in srgb, var(--accent) 28%, #1f3a57); color:#c4e0ff; }
        .ghost-pill { background:#142538; color:#d4e6f8; }
        .chip-row { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
        .category-chip-grid { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
        .category-chip-card { display:flex; align-items:center; gap:8px; border:1px solid #29435f; background:#0d1826; border-radius:16px; padding:8px 10px; }
        .chip-actions { display:flex; gap:6px; }
        .chip-icon-btn { width:28px; height:28px; border-radius:999px; border:1px solid #3a597a; background:#17304a; color:#fff; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; padding:0; font-size:14px; line-height:1; }
        .chip-icon-btn.edit-chip-btn { font-size:15px; }
        .chip-icon-btn.danger { background:#5d2b2b; border-color:#a75f5f; }
        .hero-actions { display:flex; gap:8px; align-items:center; }
        .action-menu { padding-top:16px; }
        .divider { height:1px; background:#243c56; margin: 16px 0; }
        .error { color:#ffb0b0; font-weight:600; }
        @media (max-width: 720px) {
          .wrap { padding: 14px; }
          .hero, .section { border-radius: 20px; padding: 16px; }
          .hero-head { align-items:flex-start; }
          .hero-title { font-size: 24px; }
          .row { gap:8px; }
          .activity-item, .completed-item { padding: 10px; margin-bottom: 8px; }
          .meta-line { font-size: 13px; }
          .item-main { align-items:flex-start; }
          .pill { margin-top: 2px; }
          .overlay-shell { padding:12px; }
          .modal-card { width:100%; max-height:calc(100vh - 24px); padding:16px; }
        }
      </style>
      <div class="wrap">
        ${this._narrow ? `<div class="mobile-bar"><button id="menuBtn" class="btn icon-btn" aria-label="Open navigation">☰</button><div class="mobile-title">${this.esc(dashboardName)}</div></div>` : ""}
        <section class="hero">
          <div class="hero-head">
            <div>
              <div class="hero-title">${this.esc(dashboardName)}</div>
              <div class="sub">Local-only Home Assistant workspace. Current list: ${this.esc(activeListName)}.</div>
            </div>
            <div class="hero-actions">
              <button id="heroCreateListBtn" class="btn icon-btn compact" aria-label="Create list" title="Create list">+</button>
              <button id="menuToggleBtn" class="btn icon-btn compact" aria-label="Open menu" title="Menu">...</button>
              <button id="refreshBtn" class="btn icon-btn compact" aria-label="Refresh list data" title="Refresh">R</button>
            </div>
          </div>
          ${multilist ? `<div class="list-chip-row">${listChips}</div><div class="small">Tap the active list to manage it. Long-press on touch devices or right-click on desktop to reorder it.</div>` : ""}
          <div class="row">
            <input id="quickAdd" data-draft="quickAdd" class="input" placeholder="Add item" value="${this.esc(this._drafts.quickAdd || "")}" />
            <button id="addBtn" class="btn primary">Add</button>
          </div>
        </section>
        ${actionMenu}${appSettingsPanel}${createListPanel}${listSettingsPanel}${reorderPanel}
        ${this._error ? `<section class="section"><div class="title">Error</div><div class="error">${this.esc(this._error)}</div></section>` : ""}
        ${attention.join("")}
        ${this._view === "list" ? `${groups || `<section class="section"><div class="title">${this.esc(activeListName)}</div><div class="empty">No items in this list yet.</div></section>`}<section class="section"><div class="title">Completed</div><div class="row" style="justify-content:space-between;"><div class="small">Completed history stays visible until cleared.</div><button id="clearCompletedBtn" class="btn danger">Clear Completed</button></div><div style="margin-top:10px;">${completed}</div></section>` : `<section class="section"><div class="title">Recent Activity</div>${activity}</section>`}
      </div>
    `;
    this.shadowRoot.querySelectorAll(".list-chip").forEach((chip) => {
      chip.addEventListener("click", async () => {
        const listId = chip.dataset.listId || "";
        if (this._suppressNextChipClick === listId) {
          this._suppressNextChipClick = "";
          return;
        }
        if (listId && listId === this._state?.system?.active_list_id) {
          this._listSettingsOpen = !this._listSettingsOpen;
          this._configOpen = false;
          this._createListOpen = false;
          this._menuOpen = false;
          this.requestRender(true);
          return;
        }
        await this.actFast({ action: "switch_list", list_id: listId }, () => {
          this.switchListLocal(listId);
        });
      });
      chip.addEventListener("pointerdown", (ev) => {
        if (ev.pointerType === "mouse") return;
        const listId = chip.dataset.listId || "";
        this.clearChipLongPress();
        this._chipLongPressTimer = window.setTimeout(() => {
          this._suppressNextChipClick = listId;
          this.openReorderPanel(listId);
          this.clearChipLongPress();
        }, 550);
      });
      chip.addEventListener("pointerup", () => this.clearChipLongPress());
      chip.addEventListener("pointercancel", () => this.clearChipLongPress());
      chip.addEventListener("pointerleave", () => this.clearChipLongPress());
      chip.addEventListener("contextmenu", (ev) => {
        ev.preventDefault();
        this.openReorderPanel(chip.dataset.listId || "");
      });
    });
    this.bindEvents();
    this.restoreFocus();
  }
}

customElements.define("local-list-assist-panel", LocalListAssistPanel);
