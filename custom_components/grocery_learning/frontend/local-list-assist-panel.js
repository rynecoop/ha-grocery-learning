// Entry wrapper for Local List Assist 0.35.5.
//
// The real panel implementation is kept in local-list-assist-panel-core.js.
// This wrapper loads it, then hardens retry behavior for writes that were
// queued during a transport failure but later reach the backend and receive a
// permanent rejection (for example item_not_found). Those requests must leave
// the retry queue or the error banner will remain forever and Retry will resend
// an operation that can never succeed.

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
