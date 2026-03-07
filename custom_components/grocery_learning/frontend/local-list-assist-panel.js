class LocalListAssistPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._panel = null;
    this._state = null;
    this._configOpen = false;
    this._loading = false;
    this._error = "";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this.load();
    } else {
      this.render();
    }
  }

  set panel(panel) {
    this._panel = panel;
    this.render();
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this.render();
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

  async load() {
    if (!this._hass || this._loading) {
      return;
    }
    this._loading = true;
    try {
      this._state = await this.api("dashboard");
      this._error = "";
    } catch (err) {
      this._error = err.message || String(err);
    } finally {
      this._loading = false;
      this.render();
    }
  }

  async act(payload) {
    await this.api("action", "POST", payload);
    await this.load();
  }

  esc(value) {
    return String(value ?? "").replace(/[&<>"]/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
    }[char]));
  }

  itemMarkup(item, categories) {
    const options = categories
      .map((cat) => `<option value="${this.esc(cat)}">${this.esc(cat)}</option>`)
      .join("");
    return `
      <div class="item" data-list-entity="${this.esc(item.list_entity)}" data-item-ref="${this.esc(item.item_ref)}">
        <div class="item-main">
          <div class="item-summary">
            <input class="complete-toggle" type="checkbox" />
            <strong>${this.esc(item.summary)}</strong>
          </div>
          <span class="pill">${this.esc(item.category_display)}</span>
        </div>
        <div class="small">${this.esc(item.description || "")}</div>
        <div class="editor">
          <select class="select cat-select">${options}</select>
          <button class="btn move-btn">Move</button>
        </div>
      </div>
    `;
  }

  bindEvents() {
    const root = this.shadowRoot;
    root.querySelector("#addBtn")?.addEventListener("click", async () => {
      const input = root.querySelector("#quickAdd");
      const item = input?.value?.trim();
      if (!item) return;
      input.value = "";
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
    root.querySelector("#configureBtn")?.addEventListener("click", () => {
      this._configOpen = !this._configOpen;
      this.render();
    });
    root.querySelector("#clearCompletedBtn")?.addEventListener("click", async () => {
      await this.act({ action: "clear_completed" });
    });
    root.querySelector("#activeListSelect")?.addEventListener("change", async (ev) => {
      await this.act({ action: "switch_list", list_id: ev.target.value });
    });
    root.querySelector("#saveSettingsBtn")?.addEventListener("click", async () => {
      await this.act({
        action: "save_settings",
        categories: root.querySelector("#settingsCategories")?.value || "",
        experimental_multilist: !!root.querySelector("#settingsExperimentalMultilist")?.checked,
        default_grocery_categories: !!root.querySelector("#settingsDefaultGroceryCategories")?.checked,
        debug_mode: !!root.querySelector("#settingsDebugMode")?.checked,
      });
      this._configOpen = false;
    });
    root.querySelector("#repairBtn")?.addEventListener("click", async () => {
      await this.act({ action: "repair_system" });
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
      const name = root.querySelector("#newListName")?.value?.trim();
      if (!name) return;
      const categories = root.querySelector("#newListCategories")?.value || "";
      await this.act({ action: "create_list", name, categories });
    });
    root.querySelector("#renameListBtn")?.addEventListener("click", async () => {
      const activeSelect = root.querySelector("#activeListSelect");
      if (!activeSelect?.value) return;
      const next = window.prompt("New list name");
      if (!next?.trim()) return;
      await this.act({ action: "rename_list", list_id: activeSelect.value, name: next.trim() });
    });
    root.querySelector("#archiveListBtn")?.addEventListener("click", async () => {
      const activeSelect = root.querySelector("#activeListSelect");
      if (!activeSelect?.value) return;
      await this.act({ action: "archive_list", list_id: activeSelect.value });
    });
    root.querySelector("#saveListCatsBtn")?.addEventListener("click", async () => {
      const activeSelect = root.querySelector("#activeListSelect");
      if (!activeSelect?.value) return;
      await this.act({
        action: "save_list_categories",
        list_id: activeSelect.value,
        categories: root.querySelector("#activeListCategories")?.value || "",
      });
    });
    root.querySelector("#clearListCatsBtn")?.addEventListener("click", async () => {
      const activeSelect = root.querySelector("#activeListSelect");
      if (!activeSelect?.value) return;
      await this.act({ action: "save_list_categories", list_id: activeSelect.value, categories: "" });
    });

    root.querySelectorAll(".item").forEach((row) => {
      const listEntity = row.dataset.listEntity || "";
      const itemRef = row.dataset.itemRef || "";
      const editor = row.querySelector(".editor");
      row.querySelector(".item-main")?.addEventListener("click", () => {
        editor?.classList.toggle("open");
      });
      row.querySelector(".complete-toggle")?.addEventListener("click", (ev) => ev.stopPropagation());
      row.querySelector(".complete-toggle")?.addEventListener("change", async (ev) => {
        if (ev.target.checked) {
          await this.act({ action: "set_status", list_entity: listEntity, item: itemRef, status: "completed" });
        }
      });
      row.querySelector(".move-btn")?.addEventListener("click", async () => {
        const target = row.querySelector(".cat-select")?.value || "";
        if (!target) return;
        await this.act({ action: "recategorize", from_list: listEntity, item: itemRef, target_category: target, learn: true });
      });
      row.querySelector(".cat-select")?.addEventListener("click", (ev) => ev.stopPropagation());
      row.querySelector(".cat-select")?.addEventListener("change", (ev) => ev.stopPropagation());
      row.querySelector(".move-btn")?.addEventListener("click", (ev) => ev.stopPropagation());
    });

    root.querySelectorAll(".completed-toggle").forEach((el) => {
      el.addEventListener("change", async (ev) => {
        if (!ev.target.checked) {
          await this.act({ action: "set_status", list_entity: "todo.grocery_completed", item: el.dataset.itemRef || "", status: "needs_action" });
        }
      });
    });
  }

  render() {
    const state = this._state;
    const multilist = !!state?.settings?.experimental_multilist;
    const active = state?.lists?.find((list) => list.active) || null;
    const groups = (state?.groups || [])
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
          .map((entry) => `<div class="item"><strong>${this.esc(entry.title)}</strong><div class="small">${this.esc(entry.detail)}${entry.list_name ? ` · ${this.esc(entry.list_name)}` : ""}${entry.source ? ` · ${this.esc(entry.source)}` : ""}${entry.when ? ` · ${this.esc(entry.when)}` : ""}</div></div>`)
          .join("")
      : `<div class="empty">No recent activity.</div>`;
    const completed = (state?.completed || []).length
      ? state.completed
          .map((item) => `<div class="item"><label><input class="completed-toggle" data-item-ref="${this.esc(item.item_ref)}" type="checkbox" checked /> <strong>${this.esc(item.summary)}</strong></label><div class="small">${this.esc(item.description || "")}</div></div>`)
          .join("")
      : `<div class="empty">No completed items.</div>`;
    const listOptions = (state?.lists || [])
      .map((list) => `<option value="${this.esc(list.id)}" ${list.active ? "selected" : ""}>${this.esc(list.name)}</option>`)
      .join("");
    const configPanel = this._configOpen
      ? `
        <section class="section">
          <div class="title">Configure</div>
          <div class="grid">
            <div>
              <div class="label">Default Grocery Categories</div>
              <input id="settingsCategories" class="input" value="${this.esc((state?.settings?.categories || []).join(", "))}" />
            </div>
          </div>
          <div class="row">
            <label><input id="settingsExperimentalMultilist" type="checkbox" ${state?.settings?.experimental_multilist ? "checked" : ""}/> Multi-list mode</label>
            <label><input id="settingsDefaultGroceryCategories" type="checkbox" ${state?.settings?.default_grocery_categories ? "checked" : ""}/> Default grocery categories</label>
            <label><input id="settingsDebugMode" type="checkbox" ${state?.settings?.debug_mode ? "checked" : ""}/> Debug mode</label>
          </div>
          <div class="row">
            <button id="saveSettingsBtn" class="btn primary">Save</button>
            <button id="repairBtn" class="btn">Repair</button>
          </div>
          ${multilist ? `
            <div class="divider"></div>
            <div class="grid">
              <input id="newListName" class="input" placeholder="New list name" />
              <input id="newListCategories" class="input" placeholder="Optional categories (comma separated)" />
            </div>
            <div class="row">
              <button id="createListBtn" class="btn">Create List</button>
              <button id="renameListBtn" class="btn">Rename Active</button>
              <button id="archiveListBtn" class="btn danger">Archive Active</button>
            </div>
            <div class="grid">
              <input id="activeListCategories" class="input" placeholder="Active list categories" value="${this.esc((state?.system?.active_list_categories || []).join(", "))}" />
            </div>
            <div class="row">
              <button id="saveListCatsBtn" class="btn">Save Categories</button>
              <button id="clearListCatsBtn" class="btn">No Categories</button>
            </div>
          ` : ""}
        </section>
      `
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-height:100%; background:linear-gradient(180deg,#0d1520,#09111a); color:#f3f7fb; }
        * { box-sizing:border-box; font-family: "Segoe UI", system-ui, sans-serif; }
        .wrap { max-width: 1120px; margin: 0 auto; padding: 20px; }
        .hero, .section { background: rgba(18,31,48,0.92); border:1px solid #203a57; border-radius: 24px; padding: 20px; margin-bottom: 16px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.03); }
        .title { font-size: 18px; font-weight: 700; margin-bottom: 10px; }
        .hero-title { font-size: 28px; font-weight: 800; margin: 0 0 8px; }
        .sub, .small, .label, .empty { color:#9fb4ca; }
        .row { display:flex; gap:10px; flex-wrap:wrap; margin-top: 10px; align-items:center; }
        .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
        .input, .select { width:100%; background:#08111b; color:#f3f7fb; border:1px solid #2e5276; border-radius:14px; padding: 12px 14px; }
        .btn { border:1px solid #416588; background:#27425f; color:#fff; border-radius:14px; padding: 12px 16px; cursor:pointer; }
        .btn.primary { background:#2c78ba; border-color:#57a3eb; }
        .btn.danger { background:#6a2d2d; border-color:#d96b6b; }
        .item { background:#0d1826; border:1px solid #1f3348; border-radius:16px; padding: 12px; margin-bottom: 10px; }
        .item-main { display:flex; justify-content:space-between; gap:10px; align-items:center; cursor:pointer; }
        .item-summary { display:flex; align-items:center; gap:10px; min-width:0; }
        .editor { display:none; gap:10px; margin-top:10px; }
        .editor.open { display:flex; }
        .pill { font-size:11px; padding:4px 10px; border-radius:999px; background:#1f3a57; color:#c4e0ff; }
        .divider { height:1px; background:#243c56; margin: 16px 0; }
        .error { color:#ffb0b0; font-weight:600; }
      </style>
      <div class="wrap">
        <section class="hero">
          <div class="hero-title">Local List Assist</div>
          <div class="sub">Local-first list app with smart grocery routing and flexible custom lists.</div>
          ${multilist ? `<div class="row"><select id="activeListSelect" class="select" style="max-width:360px;">${listOptions}</select><div class="small">Active list: <strong>${this.esc(active?.name || "Grocery List")}</strong></div></div>` : ""}
          <div class="row">
            <input id="quickAdd" class="input" placeholder="Add item" />
            <button id="addBtn" class="btn primary">Add</button>
            <button id="configureBtn" class="btn">Configure</button>
          </div>
        </section>
        ${configPanel}
        ${this._error ? `<section class="section"><div class="title">Error</div><div class="error">${this.esc(this._error)}</div></section>` : ""}
        ${attention.join("")}
        ${groups || ""}
        <section class="section"><div class="title">Completed</div><div class="row" style="justify-content:space-between;"><div class="small">Completed history stays visible until cleared.</div><button id="clearCompletedBtn" class="btn danger">Clear Completed</button></div><div style="margin-top:10px;">${completed}</div></section>
        <section class="section"><div class="title">Recent Activity</div>${activity}</section>
      </div>
    `;
    this.bindEvents();
  }
}

customElements.define("local-list-assist-panel", LocalListAssistPanel);
