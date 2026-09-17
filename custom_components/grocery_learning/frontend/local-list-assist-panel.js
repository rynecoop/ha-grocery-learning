// Entry wrapper for Local List Assist 0.35.6.
//
// The real panel implementation is kept in local-list-assist-panel-core.js.
// This wrapper keeps REST reads/writes independent of the frontend WebSocket,
// but delegates authentication to Home Assistant's official hass.callApi helper.
// That helper owns token refresh and authenticated request construction inside
// both the browser and companion-app webviews, avoiding stale/manual bearer
// token handling that can otherwise produce intermittent 401 responses.

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
  // Do not manually read Home Assistant's access token. The companion app and
  // long-lived browser sessions may refresh/replace it behind the panel. Using
  // hass.callApi follows the same authenticated REST path as HA's own frontend.
  Panel.prototype.api = async function (path, method = "GET", body = null) {
    const hass = this._hass;
    if (!hass || typeof hass.callApi !== "function") {
      throw new Error("Home Assistant API unavailable");
    }

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
        (typeof err === "string" ? err : "Home Assistant API request failed");
      throw new Error(message);
    }
  };

  Panel.prototype._isTerminalActionError = function (result) {
    return TERMINAL_ACTION_ERRORS.has(String(result?.error || ""));
  };

  // The core REST transport intentionally keeps failed writes queued so they can
  // be retried safely using the same request_id. A later retry that reaches the
  // server can still be rejected permanently because state changed while the
  // client was offline (e.g. another client already removed the item). Clear
  // only those terminal failures; transient runtime/startup errors stay queued.
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
