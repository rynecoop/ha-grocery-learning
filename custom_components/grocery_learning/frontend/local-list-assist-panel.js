// Entry wrapper for Local List Assist 0.35.9.
//
// Transport strategy:
// 1) Prefer Home Assistant's authenticated WebSocket for reads/writes.
// 2) If the socket is temporarily unavailable, fall back to authenticated REST.
// This avoids both failure modes seen in the field: stale/missing REST auth helpers
// and transient WebSocket disconnects.

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
  // Home Assistant can assign .hass before the custom element is upgraded.
  // In that case an own "hass" property shadows the prototype setter, so the
  // core panel never receives _hass and every transport reports "connection
  // not ready" even though HA is visibly rendering the panel. Normalize that
  // pre-upgrade property into the real setter before any API work.
  Panel.prototype._resolveHass = function () {
    if (this._hass) return this._hass;

    if (Object.prototype.hasOwnProperty.call(this, "hass")) {
      const preUpgradeHass = this.hass;
      try {
        delete this.hass;
      } catch (_err) {
        // If deletion fails, we can still use the captured object below.
      }

      if (preUpgradeHass) {
        try {
          const descriptor = Object.getOwnPropertyDescriptor(Panel.prototype, "hass");
          if (descriptor?.set) {
            descriptor.set.call(this, preUpgradeHass);
          } else {
            this._hass = preUpgradeHass;
          }
        } catch (_err) {
          this._hass = preUpgradeHass;
        }
      }
    }

    return this._hass || null;
  };

  const _originalConnectedCallback = Panel.prototype.connectedCallback;
  Panel.prototype.connectedCallback = function () {
    this._resolveHass();
    return _originalConnectedCallback?.call(this);
  };
  Panel.prototype._callLlaWS = async function (message) {
    const hass = this._resolveHass();
    if (!hass) throw new Error("Home Assistant connection not ready");

    if (typeof hass.callWS === "function") {
      return hass.callWS(message);
    }

    const connection = hass.connection;
    if (connection && typeof connection.sendMessagePromise === "function") {
      return connection.sendMessagePromise(message);
    }

    throw new Error("Home Assistant WebSocket unavailable");
  };

  Panel.prototype._callLlaRest = async function (path, method = "GET", body = null, retryOn401 = true) {
    const hass = this._resolveHass();
    if (!hass) throw new Error("Home Assistant connection not ready");

    if (typeof hass.callApi === "function") {
      return hass.callApi(
        method,
        `grocery_learning/${path}`,
        body == null ? undefined : body
      );
    }

    const auth = hass.auth || hass.connection?.options?.auth;
    if (!auth) throw new Error("Home Assistant authentication unavailable");

    if (auth.expired && typeof auth.refreshAccessToken === "function") {
      await auth.refreshAccessToken();
    }

    const headers = { "Content-Type": "application/json;charset=UTF-8" };
    if (auth.accessToken) headers.Authorization = `Bearer ${auth.accessToken}`;

    const res = await fetch(`/api/grocery_learning/${path}`, {
      method,
      headers,
      body: body == null ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });

    if (res.status === 401 && retryOn401 && typeof auth.refreshAccessToken === "function") {
      await auth.refreshAccessToken();
      return this._callLlaRest(path, method, body, false);
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

  Panel.prototype.api = async function (path, method = "GET", body = null) {
    let wsError = null;

    try {
      if (path.startsWith("dashboard")) {
        const query = path.includes("?") ? path.slice(path.indexOf("?") + 1) : "";
        const params = new URLSearchParams(query);
        const listId = params.get("list_id") || undefined;
        return await this._callLlaWS({
          type: "grocery_learning/dashboard",
          ...(listId ? { list_id: listId } : {}),
        });
      }

      if (path === "action" && method === "POST") {
        return await this._callLlaWS({
          type: "grocery_learning/action",
          payload: body || {},
        });
      }
    } catch (err) {
      wsError = err;
    }

    try {
      return await this._callLlaRest(path, method, body);
    } catch (restErr) {
      const wsMessage = wsError?.message || (wsError ? String(wsError) : "");
      const restMessage = restErr?.message || String(restErr);
      throw new Error(
        wsMessage
          ? `Home Assistant connection failed (WebSocket: ${wsMessage}; REST: ${restMessage})`
          : restMessage
      );
    }
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
