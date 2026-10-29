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
  page.setDefaultTimeout(5000);
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

async function autocompleteFixture(t, options = {}) {
  const page = await fixture(t, options);
  await page.evaluate(() => {
    window.adds = [];
    conn.read = () => ({ ...snapshot(), frequent_items: [{ item: "Fire roasted tomatoes" }], suggestions: [
      { item: "Fire roasted tomatoes", normalized: "fire roasted tomato", category: "pantry", category_display: "Pantry" },
    ] });
    conn.action = payload => { adds.push(payload); return { ok: true, dashboard: conn.read() }; };
    return mount();
  });
  await flush(page);
  return page;
}

for (const tab of ["List", "Shop"]) {
  test(`${tab}: tapping autocomplete waits for quantity and Add on a small phone`, async t => {
    const page = await autocompleteFixture(t, { viewport: { width: 320, height: 740 }, isMobile: true, hasTouch: true });
    await page.getByRole("button", { name: tab, exact: true }).tap();
    const name = page.locator(tab === "Shop" ? "#shopAdd" : "#quickAdd");
    const quantity = page.getByRole("spinbutton", { name: "Quantity", exact: true });
    await name.fill("fire");
    await page.locator(".suggest-row").filter({ hasText: "Fire roasted tomatoes" }).tap();
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds), []);
    assert.equal(await name.inputValue(), "Fire roasted tomatoes");
    assert.equal(await quantity.inputValue(), "1");
    assert.equal(await quantity.evaluate(el => el.getRootNode().activeElement === el), true);
    assert.equal(await page.locator(".suggest-dropdown").count(), 0);
    // Typing replaces the selected default rather than turning 1 into 12.
    await page.keyboard.type("2");
    assert.equal(await quantity.inputValue(), "2");
    await page.getByRole("button", { name: "Add", exact: true }).tap();
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds.map(({ action, item, quantity, list_id, actor_user_id }) => ({ action, item, quantity, list_id, actor_user_id }))), [
      { action: "add_item", item: "Fire roasted tomatoes", quantity: 2, list_id: "default", actor_user_id: "test" },
    ]);
    assert.equal(await name.inputValue(), "");
    assert.equal(await quantity.inputValue(), "1");
    assert.equal(await name.evaluate(el => el.getRootNode().activeElement === el), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  });

  test(`${tab}: keyboard selection preserves quantity until Enter confirms`, async t => {
    const page = await autocompleteFixture(t);
    await page.getByRole("button", { name: tab, exact: true }).click();
    const name = page.locator(tab === "Shop" ? "#shopAdd" : "#quickAdd");
    const quantity = page.getByRole("spinbutton", { name: "Quantity", exact: true });
    await quantity.fill("3");
    await name.fill("fire");
    await name.press("ArrowDown");
    await name.press("Enter");
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds), []);
    assert.equal(await name.inputValue(), "Fire roasted tomatoes");
    assert.equal(await quantity.inputValue(), "3");
    assert.equal(await quantity.evaluate(el => el.getRootNode().activeElement === el), true);
    await quantity.press("Enter");
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds.map(p => [p.item, p.quantity])), [["Fire roasted tomatoes", 3]]);
    // A new typed item can still be added directly, with the reset quantity.
    await name.fill("Bread");
    await name.press("Enter");
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds.map(p => [p.item, p.quantity])), [["Fire roasted tomatoes", 3], ["Bread", 1]]);
  });
}

for (const activation of ["touch", "keyboard"]) {
  test(`Frequent chips: ${activation} selection waits for quantity confirmation`, async t => {
    const page = await autocompleteFixture(t, { viewport: { width: 320, height: 740 }, isMobile: true, hasTouch: true });
    const quantity = page.getByRole("spinbutton", { name: "Quantity", exact: true });
    await quantity.fill("3");
    const chip = page.locator(".frequent-chip").filter({ hasText: "Fire roasted tomatoes" });
    if (activation === "touch") await chip.tap();
    else { await chip.focus(); await chip.press("Enter"); }
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds), []);
    assert.equal(await page.locator("#quickAdd").inputValue(), "Fire roasted tomatoes");
    assert.equal(await quantity.inputValue(), "3");
    assert.equal(await quantity.evaluate(el => el.getRootNode().activeElement === el), true);
    await page.keyboard.type("2");
    assert.equal(await quantity.inputValue(), "2");
    await quantity.press("Enter");
    await flush(page);
    assert.deepEqual(await page.evaluate(() => adds.map(p => [p.action, p.item, p.quantity])), [["add_item", "Fire roasted tomatoes", 2]]);
    assert.equal(await quantity.inputValue(), "1");
    assert.equal(await page.locator("#quickAdd").inputValue(), "");
    assert.equal(await page.locator("#quickAdd").evaluate(el => el.getRootNode().activeElement === el), true);
  });
}

test("long-pressing a Frequent chip still hides it without preparing or adding it", async t => {
  const page = await autocompleteFixture(t);
  await page.locator("#quickAdd").fill("Unfinished item");
  await page.getByRole("spinbutton", { name: "Quantity", exact: true }).fill("4");
  await page.locator(".frequent-chip").hover();
  await page.mouse.down();
  await page.clock.runFor(551);
  await page.mouse.up();
  await flush(page);
  assert.deepEqual(await page.evaluate(() => adds.map(p => p.action)), ["dismiss_frequent"]);
  assert.equal(await page.locator("#quickAdd").inputValue(), "Unfinished item");
  assert.equal(await page.getByRole("spinbutton", { name: "Quantity", exact: true }).inputValue(), "4");
});

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

for (const width of [320, 740, 1280]) {
  test(`Shop shows contributors beside quantities and keeps check-off working at ${width}px`, async t => {
    const page = await fixture(t, { viewport: { width, height: 800 } });
    await page.evaluate(() => {
      window.actions = [];
      window.items = [
        { item_ref: "tomatoes", summary: "Fire roasted tomatoes", quantity: 3, description: "Added by Alexandria Montgomery, Ryne & Jordan · just now · Typed", category: "pantry" },
        { item_ref: "bread", summary: "Bread", quantity: 1, description: "", category: "pantry" },
      ];
      conn.read = () => ({ ...snapshot(), groups: [{ category: "pantry", title: "Pantry", items }] });
      conn.action = payload => { actions.push(payload); return { ok: true, dashboard: conn.read() }; };
      return mount();
    });
    await page.getByRole("button", { name: "Shop", exact: true }).click();
    const row = page.locator(".shop-item").filter({ hasText: "Fire roasted tomatoes" });
    assert.match(await row.innerText(), /Added by Alexandria Montgomery, Ryne & Jordan/);
    assert.equal(await row.locator(".pill").innerText(), "×3");
    assert.equal(await page.locator(".shop-item").filter({ hasText: "Bread" }).locator(".shop-attribution").count(), 0);
    assert.equal(await row.locator(".shop-attribution").evaluate(el => el.getBoundingClientRect().right <= innerWidth), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (width === 320) await page.screenshot({ path: "/tmp/lla-shopping-attribution.png", fullPage: true });
    await row.click();
    assert.deepEqual(await page.evaluate(() => actions.map(p => [p.action, p.item, p.status])), [["set_status", "tomatoes", "completed"]]);
  });
}

// A valid raster exercises the real browser decode/canvas/WebP path.
const photoPng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAABgAAAAQCAIAAACDRijCAAAAG0lEQVR4nGP8v5SBKoCJOsaMGjRq0KhBI9cgAMfwAcQ4+tH4AAAAAElFTkSuQmCC", "base64");
async function photoFixture(t, options = {}) {
  const page = await fixture(t, options);
  await page.evaluate(() => {
    window.saved = []; window.imageReads = [];
    window.meals = [];
    window.photoData = "";
    window.failSave = false;
    conn.read = () => ({ ...snapshot(), meals, favorites: [], meal_categories: [] });
    conn.action = payload => {
      if (payload.action === "get_recipe_image") { imageReads.push(payload.image_id); return { ok: true, image_data: photoData }; }
      if (payload.action === "save_meal") {
        saved.push(payload);
        if (failSave) return { ok: false, error: "Save failed" };
        const old = meals.find(m => m.id === payload.meal_id);
        if (payload.image_data) photoData = payload.image_data;
        const meal = { ...old, ...payload, id: payload.meal_id || "dinner", ingredient_count: payload.ingredients.length,
          image_id: payload.image_data === undefined ? old?.image_id || "" : payload.image_data ? "a".repeat(64) : "" };
        meals = [meal];
        return { ok: true, dashboard: conn.read() };
      }
      if (payload.action === "import_recipe") return window.importResult;
      return { ok: true, dashboard: conn.read() };
    };
    return mount();
  });
  await page.getByRole("button", { name: "Meals", exact: true }).click();
  await page.evaluate(() => panel.openMealEditor());
  return page;
}

for (const width of [320, 1280]) {
  test(`Recipe photo upload, save, thumbnail, details, preserve, replace and remove at ${width}px`, async t => {
    const page = await photoFixture(t, { viewport: { width, height: 900 } });
    assert.equal(await page.getByRole("button", { name: "Add photo", exact: true }).isVisible(), true);
    await page.getByPlaceholder("Meal name (e.g. Taco Night)").fill("Taco Night");
    await page.locator("#recipePhotoInput").setInputFiles({ name: "tacos.png", mimeType: "image/png", buffer: photoPng });
    await page.locator(".recipe-photo-preview").waitFor();
    assert.equal(await page.getByRole("button", { name: "Replace photo", exact: true }).isVisible(), true);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (width === 320) await page.screenshot({ path: "/tmp/lla-recipe-photo-editor.png", fullPage: true });
    await page.getByRole("button", { name: "Create Meal", exact: true }).click();
    await page.locator(".meal-row lla-recipe-photo img").waitFor();
    assert.match(await page.evaluate(() => saved[0].image_data), /^data:image\/webp;base64,/);
    await page.locator(".meal-row").click();
    await page.getByRole("dialog", { name: "Taco Night" }).locator("lla-recipe-photo img").waitFor();
    assert.equal(await page.evaluate(() => imageReads.every(id => id === "a".repeat(64))), true);
    await page.evaluate(() => { panel.closeMealDetail(); panel.openMealEditor("dinner"); });
    await page.getByRole("button", { name: "Save Meal", exact: true }).click();
    assert.equal(await page.evaluate(() => "image_data" in saved.at(-1)), false);
    await page.evaluate(() => panel.openMealEditor("dinner"));
    await page.locator("#recipePhotoInput").setInputFiles({ name: "replacement.png", mimeType: "image/png", buffer: photoPng });
    await page.locator(".recipe-photo-preview").waitFor();
    await page.getByRole("button", { name: "Save Meal", exact: true }).click();
    assert.match(await page.evaluate(() => saved.at(-1).image_data), /^data:image\/webp;base64,/);
    await page.evaluate(() => panel.openMealEditor("dinner"));
    await page.getByRole("button", { name: "Remove photo", exact: true }).click();
    assert.equal(await page.getByRole("button", { name: "Add photo", exact: true }).isVisible(), true);
    await page.getByRole("button", { name: "Save Meal", exact: true }).click();
    assert.equal(await page.evaluate(() => saved.at(-1).image_data), "");
    assert.equal(await page.locator(".meal-row lla-recipe-photo").count(), 0);
  });
}

test("Recipe photo failed save keeps preview; invalid files do not replace the selected photo", async t => {
  const page = await photoFixture(t);
  await page.getByPlaceholder("Meal name (e.g. Taco Night)").fill("Dinner");
  await page.locator("#recipePhotoInput").setInputFiles({ name: "dinner.png", mimeType: "image/png", buffer: photoPng });
  await page.locator(".recipe-photo-preview").waitFor();
  const src = await page.locator(".recipe-photo-preview").getAttribute("src");
  await page.locator("#recipePhotoInput").setInputFiles({ name: "bad.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg/>") });
  assert.equal(await page.locator(".recipe-photo-preview").getAttribute("src"), src);
  assert.match(await page.locator(".recipe-import .error").innerText(), /Choose a photo from your library/);
  await page.evaluate(() => { failSave = true; });
  await page.getByRole("button", { name: "Create Meal", exact: true }).click();
  assert.equal(await page.locator(".recipe-photo-preview").getAttribute("src"), src);
  assert.equal(await page.getByRole("button", { name: "Create Meal", exact: true }).isVisible(), true);
});

test("Recipe imports show photo and source link; missing photo preserves usable recipe text", async t => {
  const page = await photoFixture(t);
  await page.evaluate(async () => {
    const canvas = document.createElement("canvas"); canvas.width = canvas.height = 2;
    importResult = { ok: true, recipe: { name: "Imported dinner", ingredients: ["rice"], directions: ["Cook"], image_data: canvas.toDataURL("image/webp") }, source_url: "https://example.com/dinner" };
  });
  await page.getByPlaceholder("Paste a recipe URL").fill("https://example.com/dinner");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await page.locator(".recipe-photo-preview").waitFor();
  await page.getByRole("button", { name: "Create Meal", exact: true }).click();
  await page.locator(".meal-row").click();
  assert.equal(await page.getByRole("link", { name: "View original recipe" }).getAttribute("href"), "https://example.com/dinner");
  await page.evaluate(() => {
    panel.closeMealDetail(); panel.openMealEditor();
    importResult = { ok: true, recipe: { name: "No photo dinner", ingredients: ["rice"], directions: ["Cook"] }, image_warning: "Photo unavailable — upload your own." };
  });
  await page.getByPlaceholder("Paste a recipe URL").fill("https://example.com/other");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  assert.equal(await page.getByPlaceholder("Meal name (e.g. Taco Night)").inputValue(), "No photo dinner");
  assert.match(await page.locator(".recipe-import .error").innerText(), /Photo unavailable/);
  assert.equal(await page.getByRole("button", { name: "Add photo", exact: true }).isVisible(), true);
});

test("Removing a photo invalidates an in-flight decode and saves wait for photo preparation", async t => {
  const page = await photoFixture(t);
  await page.getByPlaceholder("Meal name (e.g. Taco Night)").fill("Dinner");
  await page.evaluate(() => { window.realDecode = createImageBitmap; window.createImageBitmap = file => new Promise(resolve => { window.finishDecode = async () => resolve(await realDecode(file)); }); });
  await page.locator("#recipePhotoInput").setInputFiles({ name: "dinner.png", mimeType: "image/png", buffer: photoPng });
  assert.equal(await page.getByRole("button", { name: "Create Meal", exact: true }).isDisabled(), true);
  await page.getByRole("button", { name: "Remove photo", exact: true }).click();
  await page.evaluate(() => finishDecode());
  assert.equal(await page.locator(".recipe-photo-preview").count(), 0);
  assert.equal(await page.getByRole("button", { name: "Create Meal", exact: true }).isEnabled(), true);
});

test("An import superseding a pending photo decode does not leave Save disabled", async t => {
  const page = await photoFixture(t);
  await page.evaluate(() => {
    window.realDecode = createImageBitmap;
    window.createImageBitmap = file => new Promise(resolve => { window.finishDecode = async () => resolve(await realDecode(file)); });
    window.importResult = { ok: true, recipe: { name: "Imported dinner", ingredients: ["rice"] } };
  });
  await page.locator("#recipePhotoInput").setInputFiles({ name: "dinner.png", mimeType: "image/png", buffer: photoPng });
  await page.getByPlaceholder("Paste a recipe URL").fill("https://example.com/dinner");
  await page.getByRole("button", { name: "Import", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "Create Meal", exact: true }).isEnabled(), true);
  await page.evaluate(() => finishDecode());
  assert.equal(await page.locator(".recipe-photo-preview").count(), 0);
});

test("A real 48MP phone JPEG over 8 MB is resized on-device and saved as a bounded raster", async t => {
  const page = await photoFixture(t, { viewport: { width: 320, height: 900 } });
  page.setDefaultTimeout(20000);
  await page.getByPlaceholder("Meal name (e.g. Taco Night)").fill("Phone photo dinner");
  const original = await page.evaluate(async () => {
    const canvas = document.createElement("canvas"); canvas.width = 8000; canvas.height = 6000;
    const ctx = canvas.getContext("2d");
    // Reuse a noisy eight-row tile to keep fixture memory low. JPEG encodes
    // every block separately, producing a genuine large 48MP camera-like file.
    const tile = ctx.createImageData(8000, 8); let seed = 123456;
    for (let i = 0; i < tile.data.length; i += 4) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      tile.data[i] = seed >>> 24; tile.data[i + 1] = (seed >>> 16) & 255; tile.data[i + 2] = (seed >>> 8) & 255; tile.data[i + 3] = 255;
    }
    for (let y = 0; y < canvas.height; y += 8) ctx.putImageData(tile, 0, y);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/jpeg", 0.92));
    canvas.width = canvas.height = 1;
    const file = new File([blob], "IMG_1234.JPG", { type: "image/jpeg" });
    const dt = new DataTransfer(); dt.items.add(file);
    const input = panel.renderRoot.getElementById("recipePhotoInput"); input.files = dt.files; input.dispatchEvent(new Event("change", { bubbles: true }));
    return { size: file.size, width: 8000, height: 6000 };
  });
  assert.ok(original.size > 8 * 1024 * 1024, `fixture should exceed the old cap: ${original.size}`);
  assert.ok(original.size < 100 * 1024 * 1024);
  await page.locator(".recipe-photo-preview").waitFor();
  const prepared = await page.evaluate(async () => {
    const blob = await (await fetch(panel._drafts.mealImageData)).blob();
    const bitmap = await createImageBitmap(blob);
    const result = { bytes: blob.size, width: bitmap.width, height: bitmap.height }; bitmap.close(); return result;
  });
  assert.ok(prepared.bytes <= 256 * 1024);
  assert.ok(Math.max(prepared.width, prepared.height) <= 1200);
  assert.equal(prepared.width / prepared.height, 4 / 3);
  await page.getByRole("button", { name: "Create Meal", exact: true }).click();
  assert.equal(await page.evaluate(() => saved.length), 1);
  assert.ok(await page.evaluate(() => saved[0].image_data.length < 360000));
});

test("Detailed photos automatically shrink further when the first size cannot fit", async t => {
  const page = await photoFixture(t);
  const result = await page.evaluate(async () => {
    const { prepareRecipePhoto } = await import("/recipe-photo.js?v=test");
    const real = HTMLCanvasElement.prototype.toDataURL; window.encodedSizes = [];
    HTMLCanvasElement.prototype.toDataURL = function (...args) {
      encodedSizes.push([this.width, this.height]);
      if (Math.max(this.width, this.height) >= 1200) return "data:image/webp;base64," + "A".repeat(360000);
      return real.apply(this, args);
    };
    try {
      const canvas = document.createElement("canvas"); canvas.width = 1600; canvas.height = 1200;
      const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
      const data = await prepareRecipePhoto(new File([blob], "detailed.png", { type: "image/png" }));
      const image = await createImageBitmap(await (await fetch(data)).blob());
      const result = { width: image.width, height: image.height, tried: encodedSizes }; image.close(); return result;
    } finally { HTMLCanvasElement.prototype.toDataURL = real; }
  });
  assert.ok(result.tried.some(([w]) => w === 1200));
  assert.equal(result.width, 900);
  assert.equal(result.height, 675);
});

test("Missing MIME metadata and browser decode/JPEG-encode fallbacks require no user conversion", async t => {
  const page = await photoFixture(t);
  const result = await page.evaluate(async bytes => {
    const { prepareRecipePhoto } = await import("/recipe-photo.js?v=test");
    const bitmapDecoder = window.createImageBitmap;
    const encode = HTMLCanvasElement.prototype.toDataURL;
    const realCreate = URL.createObjectURL; const realRevoke = URL.revokeObjectURL;
    window.urlCreates = []; window.urlRevokes = [];
    URL.createObjectURL = blob => { const url = realCreate(blob); urlCreates.push(url); return url; };
    URL.revokeObjectURL = url => { urlRevokes.push(url); return realRevoke(url); };
    window.createImageBitmap = async () => { throw new Error("bitmap decoder unavailable"); };
    HTMLCanvasElement.prototype.toDataURL = function (type, quality) { return encode.call(this, type === "image/webp" ? "image/png" : type, quality); };
    try {
      const data = await prepareRecipePhoto(new File([new Uint8Array(bytes)], "PHONE.PNG", { type: "" }));
      return { data, creates: urlCreates, revokes: urlRevokes };
    } finally {
      window.createImageBitmap = bitmapDecoder; HTMLCanvasElement.prototype.toDataURL = encode;
      URL.createObjectURL = realCreate; URL.revokeObjectURL = realRevoke;
    }
  }, [...photoPng]);
  assert.match(result.data, /^data:image\/jpeg;base64,/);
  assert.equal(result.creates.length, 1);
  assert.deepEqual(result.creates, result.revokes);
});

test("An unsupported phone format keeps the existing preview and recovers the Save button", async t => {
  const page = await photoFixture(t);
  await page.getByPlaceholder("Meal name (e.g. Taco Night)").fill("Dinner");
  await page.locator("#recipePhotoInput").setInputFiles({ name: "dinner.png", mimeType: "image/png", buffer: photoPng });
  await page.locator(".recipe-photo-preview").waitFor();
  const before = await page.locator(".recipe-photo-preview").getAttribute("src");
  await page.locator("#recipePhotoInput").setInputFiles({ name: "bad.heic", mimeType: "image/heic", buffer: Buffer.from("not a valid HEIC photo") });
  await page.waitForFunction(() => !panel._photoLoading);
  assert.equal(await page.locator(".recipe-photo-preview").getAttribute("src"), before);
  assert.match(await page.locator(".recipe-import .error").innerText(), /browser couldn’t read that photo format/);
  assert.equal(await page.getByRole("button", { name: "Create Meal", exact: true }).isEnabled(), true);
});


test("Phone EXIF orientation is preserved while preparing a recipe photo", async t => {
  const page = await photoFixture(t);
  await page.locator("#recipePhotoInput").setInputFiles({ name: "portrait.JPG", mimeType: "image/jpeg", buffer: Buffer.from("/9j/4AAQSkZJRgABAQAAAQABAAD/4QAiRXhpZgAATU0AKgAAAAgAAQESAAMAAAABAAYAAAAAAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAAUACgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDi6KKK+ZP3EKKKKACiiigAooooAKKKKACiiigD/9k=", "base64") });
  await page.locator(".recipe-photo-preview").waitFor();
  const size = await page.evaluate(async () => {
    const bitmap = await createImageBitmap(await (await fetch(panel._drafts.mealImageData)).blob());
    const result = [bitmap.width, bitmap.height]; bitmap.close(); return result;
  });
  assert.deepEqual(size, [20, 40]);
});

test("Unusually large originals are rejected before decoding or uploading", async t => {
  const page = await photoFixture(t);
  const result = await page.evaluate(async () => {
    const { prepareRecipePhoto } = await import("/recipe-photo.js?v=test");
    const real = window.createImageBitmap; let decoded = false;
    window.createImageBitmap = async () => { decoded = true; throw Error("unexpected decode"); };
    try {
      await prepareRecipePhoto({ name: "enormous.jpg", type: "image/jpeg", size: 101 * 1024 * 1024 });
      return { decoded, error: "none" };
    } catch (e) { return { decoded, error: e.message }; }
    finally { window.createImageBitmap = real; }
  });
  assert.equal(result.decoded, false);
  assert.match(result.error, /under 100 MB/);
});
