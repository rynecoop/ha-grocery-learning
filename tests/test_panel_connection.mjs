// Run: npm install --no-save --package-lock=false playwright@1.58.2
//      npx playwright install chromium
//      node --test tests/test_panel_connection.mjs
// Real Chromium tests: import the shipped entry, then let DOM attachment/removal
// invoke lifecycle callbacks. Calling prototype callbacks directly misses late
// customElements.define() patching bugs.
import test, { before, after } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)("playwright");
const frontend = new URL("../custom_components/grocery_learning/frontend/", import.meta.url);
let server, browser, origin;

before(async () => {
  server = createServer(async (req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    if (path === "/") {
      res.setHeader("Content-Type", "text/html");
      res.end(`<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0}</style></head><body></body></html>`);
      return;
    }
    try {
      const url = new URL(`.${path}`, frontend);
      if (!fileURLToPath(url).startsWith(fileURLToPath(frontend))) throw new Error("bad path");
      res.setHeader("Content-Type", "text/javascript");
      res.end(await readFile(url));
    } catch { res.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}),
  });
});
after(async () => {
  await browser?.close();
  await new Promise(resolve => server?.close(resolve));
});

async function fixture(t, options = {}) {
  const page = await browser.newPage(options);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  t.after(async () => { await page.close(); assert.deepEqual(errors, []); });
  await page.goto(origin);
  await page.clock.install();
  await page.evaluate(() => {
    window.snapshot = (revision = "1") => ({
      revision, settings: {}, system: { active_list_id: "default" },
      lists: [{ id: "default", name: "Groceries", active: true }],
      groups: [], completed: [], categories: [],
    });
    window.makeHass = () => {
      const listeners = new Map();
      const c = {
        connected: true, subscriptions: 0, reads: 0, restReads: 0, unsubs: 0,
        callbacks: [], listeners,
        addEventListener(name, fn) {
          if (!listeners.has(name)) listeners.set(name, new Set());
          listeners.get(name).add(fn);
        },
        removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
        fire(name) { for (const fn of listeners.get(name) || []) fn(c); },
        async subscribeMessage(fn) {
          c.subscriptions++; c.callbacks.push(fn);
          if (c.subscribe) return c.subscribe(fn);
          return () => { c.unsubs++; };
        },
      };
      return {
        connection: c, states: {}, user: { id: "test" },
        async callWS(message) {
          if (message.type === "grocery_learning/action") {
            if (c.action) return c.action(message.payload);
            return { ok: true, dashboard: snapshot() };
          }
          c.reads++;
          if (!c.connected) throw new Error("offline");
          return c.read ? c.read() : snapshot();
        },
        async callApi(method, path, body) {
          if (method === "POST") {
            if (c.action) return c.action(body);
            return { ok: true, dashboard: snapshot() };
          }
          c.restReads++;
          if (!c.connected) throw new Error("offline");
          return c.rest ? c.rest() : snapshot();
        },
      };
    };
    window.hass = makeHass();
    window.conn = hass.connection;
    window.mount = async (preUpgrade = false) => {
      if (preUpgrade) {
        window.panel = document.createElement("local-list-assist-panel");
        panel.hass = hass;
        document.body.append(panel);
      }
      await import("/local-list-assist-panel.js?v=test");
      if (!preUpgrade) {
        window.panel = document.createElement("local-list-assist-panel");
        panel.hass = hass;
        document.body.append(panel);
      }
      await panel.updateComplete;
    };
  });
  return page;
}
const flush = page => page.evaluate(async () => { await Promise.resolve(); await panel.updateComplete; });

test("pre-upgrade hass starts through real browser lifecycle; detach cleans everything", async t => {
  const page = await fixture(t);
  await page.evaluate(() => mount(true));
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [!!panel._state, conn.reads, conn.subscriptions, panel.hasOwnProperty("hass")]), [true, 1, 1, false]);
  await page.evaluate(() => panel.remove());
  assert.deepEqual(await page.evaluate(() => [conn.unsubs, [...conn.listeners.values()].reduce((n,s) => n+s.size,0), panel._syncTimer]), [1, 0, null]);
});

test("successful dashboard does not stop retrying a late subscription rejection", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    conn.subscribe = () => new Promise((_, reject) => { window.rejectSubscription = reject; });
    return mount();
  });
  await page.clock.runFor(1000);
  assert.equal(await page.evaluate(() => !!panel._state), true);
  await page.evaluate(() => { conn.subscribe = null; rejectSubscription(new Error("integration not ready")); });
  await page.clock.runFor(251);
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [conn.reads, conn.subscriptions, panel._wsActive, panel._syncStatus]), [1, 2, true, ""]);
});

test("failed initial reads retry independently of a healthy subscription", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    conn.read = conn.rest = () => { throw new Error("starting"); };
    return mount();
  });
  await flush(page);
  assert.match(await page.locator("[role=status]").innerText(), /Unable to load/);
  await page.evaluate(() => { conn.read = conn.rest = null; });
  await page.clock.runFor(251);
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [!!panel._state, conn.reads, conn.subscriptions]), [true, 2, 1]);
});

test("ready refreshes stale data without duplicate subscription and preserves drafts/focus/errors", async t => {
  const page = await fixture(t);
  await page.evaluate(() => mount());
  await flush(page);
  await page.locator("#quickAdd").fill("Milk draft");
  await page.evaluate(() => {
    panel._error = "That file is not a valid backup.";
    conn.connected = false; conn.fire("disconnected");
  });
  await flush(page);
  assert.match(await page.locator(".sync-notice").innerText(), /Reconnecting/);
  await page.evaluate(() => { conn.read = () => snapshot("2"); conn.connected = true; conn.fire("ready"); });
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [panel._state.revision, conn.subscriptions, panel._error, panel._drafts.quickAdd, panel.shadowRoot.activeElement?.id]), ["2", 1, "That file is not a valid backup.", "Milk draft", "quickAdd"]);
  assert.equal(await page.locator(".sync-notice").count(), 0);
});

test("detach and reattach ignore late reads/subscriptions from the previous lifecycle", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    conn.read = () => new Promise(resolve => { window.resolveRead = resolve; });
    conn.subscribe = () => new Promise(resolve => { window.resolveSub = resolve; });
    return mount();
  });
  await page.evaluate(() => {
    panel.remove();
    conn.read = () => snapshot("new"); conn.subscribe = null;
    document.body.append(panel);
  });
  await flush(page);
  await page.evaluate(() => {
    resolveRead(snapshot("old"));
    resolveSub(() => { conn.unsubs++; return Promise.reject(new Error("closed")); });
  });
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [panel._state.revision, conn.unsubs, conn.subscriptions, panel._wsActive, panel._loading]), ["new", 1, 2, true, false]);
  const reads = await page.evaluate(() => conn.reads);
  await page.evaluate(() => conn.callbacks[0]({ revision: "obsolete" }));
  await flush(page);
  assert.equal(await page.evaluate(() => conn.reads), reads);
});

test("connection replacement releases old listeners and ignores pending old requests", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    conn.read = () => new Promise(resolve => { window.resolveRead = resolve; });
    return mount();
  });
  await page.evaluate(() => {
    window.old = conn; window.hass = makeHass(); window.conn = hass.connection;
    conn.read = () => snapshot("replacement"); panel.hass = hass;
    resolveRead(snapshot("old")); old.fire("ready");
  });
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [panel._state.revision, old.unsubs, [...old.listeners.values()].reduce((n,s)=>n+s.size,0), conn.reads, conn.subscriptions]), ["replacement", 1, 0, 1, 1]);
});

test("backoff is capped, hass updates do not postpone retries, and detach cancels them", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    window.delays = []; const timeout = window.setTimeout.bind(window);
    window.setTimeout = (fn, delay, ...args) => { delays.push(delay); return timeout(fn, delay, ...args); };
    conn.subscribe = () => { throw new Error("not ready"); };
    return mount();
  });
  for (let i = 0; i < 5; i++) {
    await page.evaluate(() => { panel.hass = { ...hass }; });
    await page.clock.runFor(60);
  }
  assert.equal(await page.evaluate(() => conn.subscriptions), 2);
  await page.clock.runFor(24000);
  const delays = await page.evaluate(() => window.delays);
  assert.deepEqual(delays.slice(0, 7), [250, 500, 1000, 2000, 4000, 5000, 5000]);
  await page.evaluate(() => { panel.remove(); window.count = conn.subscriptions; });
  await page.clock.runFor(10000);
  assert.equal(await page.evaluate(() => conn.subscriptions === count && panel._syncTimer === null), true);
});

test("REST fallback still works and failed writes keep the same request id for retry", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    conn.read = () => { throw new Error("WS unavailable"); };
    return mount();
  });
  await flush(page);
  assert.equal(await page.evaluate(() => !!panel._state && conn.restReads === 1), true);
  await page.evaluate(async () => {
    window.ids = [];
    conn.action = payload => { ids.push(payload.request_id); throw new Error("offline"); };
    await panel.act({ action: "add_item", item: "Milk" });
  });
  assert.equal(await page.evaluate(() => panel._pendingWrites.length), 1);
  await page.evaluate(async () => {
    conn.action = payload => { ids.push(payload.request_id); return {ok:true, dashboard:snapshot("saved")}; };
    await panel.retryPending();
  });
  assert.deepEqual(await page.evaluate(() => [panel._pendingWrites.length, new Set(ids).size, panel._state.revision]), [0, 1, "saved"]);
});

test("live update during an in-flight read schedules a follow-up without overlap", async t => {
  const page = await fixture(t);
  await page.evaluate(() => {
    conn.read = () => new Promise(resolve => { window.resolveRead = resolve; });
    return mount();
  });
  await page.evaluate(() => {
    conn.callbacks[0]({revision:"2"});
    conn.read = () => snapshot("2");
    resolveRead(snapshot("1"));
  });
  await page.clock.runFor(251);
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [conn.reads, panel._state.revision]), [2, "2"]);
});

test("late hass assignment starts once, and assignments while detached do no work", async t => {
  const page = await fixture(t);
  await page.evaluate(async () => {
    await import("/local-list-assist-panel.js?v=test");
    window.panel = document.createElement("local-list-assist-panel");
    document.body.append(panel);
    await panel.updateComplete;
  });
  assert.equal(await page.locator("[role=status]").innerText(), "Connecting…");
  await page.evaluate(() => { panel.hass = hass; });
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [conn.reads, conn.subscriptions, !!panel._state]), [1, 1, true]);
  await page.evaluate(() => { panel.remove(); panel.hass = { ...hass }; });
  await page.clock.runFor(6000);
  assert.deepEqual(await page.evaluate(() => [conn.reads, conn.subscriptions, panel._syncTimer]), [1, 1, null]);
});

test("failed reconnect refresh keeps old data and retries without a new hass assignment", async t => {
  const page = await fixture(t);
  await page.evaluate(() => mount());
  await flush(page);
  await page.evaluate(() => {
    conn.connected = false; conn.fire("disconnected");
    conn.read = conn.rest = () => { throw new Error("backend still starting"); };
    conn.connected = true; conn.fire("ready");
  });
  await flush(page);
  assert.equal(await page.evaluate(() => panel._state.revision), "1");
  assert.match(await page.locator(".sync-notice").innerText(), /Unable to refresh/);
  await page.evaluate(() => { conn.read = () => snapshot("recovered"); });
  await page.clock.runFor(251);
  await flush(page);
  assert.deepEqual(await page.evaluate(() => [panel._state.revision, conn.subscriptions, panel._syncStatus]), ["recovered", 1, ""]);
});

// Simulate HA's documented sidebar event receiver outside an extra shadow root.
// This checks the integration boundary without depending on private HA methods.
async function navigationHost(page) {
  await page.evaluate(() => {
    const host = document.createElement("section");
    document.body.append(host);
    host.attachShadow({ mode: "open" }).append(panel);
    window.navigationEvents = [];
    window.windowEvents = 0;
    window.backCalls = 0;
    window.sidebarOpen = false;
    history.pushState({}, "", "/grocery-app");
    history.back = () => { backCalls++; };
    document.addEventListener("hass-toggle-menu", event => {
      navigationEvents.push({ open: event.detail?.open, composed: event.composed, bubbles: event.bubbles });
      sidebarOpen = event.detail?.open ?? !sidebarOpen;
    });
    window.addEventListener("hass-toggle-menu", () => { windowEvents++; });
  });
  await flush(page);
}

for (const [name, options] of [
  ["small phone", { viewport: { width: 320, height: 740 }, isMobile: true, hasTouch: true }],
  ["phone landscape", { viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true }],
  ["desktop with hidden sidebar", { viewport: { width: 1280, height: 900 } }],
]) {
  test(`Home Assistant menu is reachable from every view on ${name}`, async t => {
    const page = await fixture(t, options);
    await page.evaluate(() => mount());
    await navigationHost(page);
    // Do not rely on narrow being supplied correctly or a docked desktop sidebar.
    await page.evaluate(() => { panel.narrow = false; hass.dockedSidebar = "always_hidden"; });
    const activate = locator => options.hasTouch ? locator.tap() : locator.click();
    for (const label of ["List", "Shop", "Meals", "Plan"]) {
      await activate(page.getByRole("button", { name: label, exact: true }));
      await flush(page);
      const button = page.getByRole("button", { name: "Open Home Assistant menu", exact: true });
      assert.equal(await button.count(), 1);
      const box = await button.boundingBox();
      assert.ok(box.height >= 44 && box.width >= 44);
      await activate(button);
      assert.equal(await page.evaluate(() => sidebarOpen), true);
    }
    await activate(page.getByRole("button", { name: "List", exact: true }));
    await activate(page.getByRole("button", { name: "Open menu", exact: true }));
    await activate(page.getByRole("button", { name: "Activity", exact: true }));
    await activate(page.getByRole("button", { name: "Open Home Assistant menu", exact: true }));
    assert.deepEqual(await page.evaluate(() => ({ events: navigationEvents, count: windowEvents, back: backCalls, path: location.pathname })), {
      events: Array(5).fill({ open: true, composed: true, bubbles: true }), count: 5, back: 0, path: "/grocery-app",
    });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  });
}

test("Home Assistant navigation stays available before hass, during loading, and after a load failure", async t => {
  const page = await fixture(t, { viewport: { width: 390, height: 844 } });
  await page.evaluate(async () => {
    await import("/local-list-assist-panel.js?v=test");
    window.panel = document.createElement("local-list-assist-panel");
    document.body.append(panel);
  });
  await navigationHost(page);
  const button = page.getByRole("button", { name: "Open Home Assistant menu", exact: true });
  await button.click();
  await page.evaluate(() => {
    conn.read = () => new Promise((_, reject) => { window.failRead = reject; });
    conn.rest = () => { throw new Error("unavailable"); };
    panel.hass = hass;
  });
  await flush(page);
  await button.click();
  await page.evaluate(() => failRead(new Error("unavailable")));
  await flush(page);
  assert.match(await page.locator("[role=status]").innerText(), /Unable to load/);
  await button.click();
  assert.deepEqual(await page.evaluate(() => [navigationEvents.length, windowEvents, sidebarOpen, backCalls]), [3, 3, true, 0]);
});

test("keyboard navigation opens HA over app dialogs without losing an unfinished draft", async t => {
  const page = await fixture(t, { viewport: { width: 390, height: 844 } });
  await page.evaluate(() => mount());
  await navigationHost(page);
  await page.locator("#quickAdd").fill("Unfinished groceries");
  await page.getByRole("button", { name: "Open menu", exact: true }).click();
  await page.getByRole("button", { name: "App Settings", exact: true }).click();
  const button = page.getByRole("button", { name: "Open Home Assistant menu", exact: true });
  const header = await page.locator(".ha-navigation").boundingBox();
  const overlay = await page.locator(".overlay-shell").boundingBox();
  assert.ok(overlay.y >= header.y + header.height);
  await button.click(); // Playwright checks the modal doesn't intercept the click.
  await button.focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Space");
  assert.deepEqual(await page.evaluate(() => [sidebarOpen, navigationEvents.length, windowEvents, backCalls, panel._drafts.quickAdd]), [true, 3, 3, 0, "Unfinished groceries"]);
});

test("long lists keep the HA header visible and shopping controls below it", async t => {
  const page = await fixture(t, { viewport: { width: 390, height: 844 } });
  await page.evaluate(() => {
    conn.read = () => ({ ...snapshot(), groups: [{ category: "other", title: "Groceries", items: Array.from({ length: 35 }, (_, i) => ({ item_ref: `item-${i}`, summary: `Grocery item ${i}`, quantity: 1 })) }] });
    return mount();
  });
  await navigationHost(page);
  await page.evaluate(() => window.scrollTo(0, 800));
  await page.clock.runFor(50);
  const button = page.getByRole("button", { name: "Open Home Assistant menu", exact: true });
  let header = await page.locator(".ha-navigation").boundingBox();
  assert.equal(header.y, 0);
  await button.click();
  await page.getByRole("button", { name: "Shop", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 800));
  await page.clock.runFor(50);
  header = await page.locator(".ha-navigation").boundingBox();
  const shopping = await page.locator(".shop-bar").boundingBox();
  assert.equal(header.y, 0);
  assert.ok(shopping.y >= header.y + header.height);
  await button.click();
  assert.equal(await page.evaluate(() => navigationEvents.length), 2);
});
