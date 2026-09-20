// Entry wrapper for Local List Assist 0.35.7.
//
// Keep panel reads/writes on REST so a frontend WebSocket outage does not take
// the list down, but use Home Assistant's live Auth object whenever the custom
// panel hass object does not expose hass.callApi directly.

const _moduleQuery = (() => {
  try {
    const version = new URL(import.meta.url).searchParams.get("v");
    return version ? `?v=${encodeURIComponent(version)}` : "";
  } catch (_err) {
    return "";
  }
})();

await import(`./local-list-assist-panel-core.js${_moduleQuery}`);

const TERMINAL_ACTION_ERRORS = new Set([
  "missing_url", "invalid_url", "no_recipe", "not_a_page", "too_large", "blocked",
  "no_items", "too_many",
  "list_not_found", "list_exists", "multilist_disabled", "cannot_move_default",
  "invalid_color", "invalid_order", "missing_name",
  "missing_item_reference", "item_not_found", "item_summary_missing",
  "unknown_meal", "missing_label", "duplicate", "invalid", "unknown_category",
  "no_user", "invalid_backup", "unknown_action",
]);

const Panel = customElements.get("local-list-assist-panel");
if (Panel) {
  Panel.prototype.api = async function (path, method = "GET", body = null, retryOn401 = true) {
    const hass = this._hass;
    if (!hass) {
      throw new Error("Home Assistant connection not ready");
    }

    // Full Home Assistant objects expose callApi. Prefer it when available.
    if (typeof hass.callApi === "function") {
      try {
        return await hass.callApi(
          method,
          `grocery_learning/${path}`,
          body == null ? undefined : body
        );
      } catch (err) {
        const message =
          err?.message ||
          err?.body?.message ||
          err?.body?.error ||
          err?.error ||
          (typeof err === "string" ? err : "Home Assistant API request failed");
        throw new Error(message);
      }
    }

    // Custom-panel hass objects in some HA/companion-app contexts omit callApi
    // but still carry the live Auth object on the connection. Mirror HA's own
    // fetchWithAuth behavior using that object instead of caching a bearer token.
    const auth = hass.auth || hass.connection?.options?.auth;
    if (!auth) {
      throw new Error("Home Assistant authentication unavailable");
    }

    if (auth.expired && typeof auth.refreshAccessToken === "function") {
      await auth.refreshAccessToken();
    }

    const headers = { "Content-Type": "application/json;charset=UTF-8" };
    if (auth.accessToken) {
      headers.Authorization = `Bearer ${auth.accessToken}`;
    }

    const res = await fetch(`/api/grocery_learning/${path}`, {
      method,
      headers,
      body: body == null ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });

    if (res.status === 401 && retryOn401 && typeof auth.refreshAccessToken === "function") {
      await auth.refreshAccessToken();
      return this.api(path, method, body, false);
    }

    const text = await res.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_err) {
      data = { error: text || `HTTP ${res.status}` };
    }

    if (!res.ok) {
      throw new Error(data?.error || data?.message || text || `HTTP ${res.status}`);
    }
    return data;
  };

  Panel.prototype._isTerminalActionError = function (result) {
    return TERMINAL_ACTION_ERRORS.has(String(result?.error || ""));
  };

  Panel.prototype.retryPending = async function () {
    const items = [...this._pendingWrites];
    this._error = "";
    for (const item of items) {
      const result = await this.act(item.payload);
      if (result && result.ok === false && this._isTerminalActionError(result)) {
        this._removePending(item.id);
      }
    }
    this.requestUpdate();
  };
}
