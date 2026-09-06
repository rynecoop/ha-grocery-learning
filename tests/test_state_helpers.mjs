import test from "node:test";
import assert from "node:assert/strict";
import {
  categoryDisplay,
  createListLocal,
  deleteArchivedListLocal,
  groupTitle,
  matchSuggestions,
  moveItemToCompleted,
  recategorizeItemLocal,
  itemIsRoutable,
  renameListLocal,
  routablePastedItems,
  splitPastedItems,
  switchListLocal,
  updateItemLocal,
} from "../custom_components/grocery_learning/frontend/state-helpers.js";

test("moveItemToCompleted moves an active item into completed", () => {
  const state = {
    groups: [
      {
        category: "produce",
        items: [{ item_ref: "1", summary: "Apples", description: "Added by Ryne" }],
      },
    ],
    completed: [],
  };

  const moved = moveItemToCompleted(state, "1");

  assert.equal(moved, true);
  assert.equal(state.groups[0].items.length, 0);
  assert.equal(state.completed.length, 1);
  assert.equal(state.completed[0].summary, "Apples");
});

test("recategorizeItemLocal moves item into target group and updates display fields", () => {
  const state = {
    categories: ["produce", "bakery", "other"],
    groups: [
      { category: "produce", title: "Produce", items: [{ item_ref: "1", summary: "Bread", category: "produce", list_entity: "internal:produce" }] },
    ],
  };

  const moved = recategorizeItemLocal(state, "1", "bakery");

  assert.equal(moved, true);
  assert.equal(state.groups[0].items.length, 0);
  const bakery = state.groups.find((group) => group.category === "bakery");
  assert.ok(bakery);
  assert.equal(bakery.title, "Bakery");
  assert.equal(bakery.items[0].category_display, "Bakery");
  assert.equal(bakery.items[0].list_entity, "internal:bakery");
});

test("switchListLocal updates active list and system state", () => {
  const state = {
    lists: [
      { id: "default", name: "Grocery List", color: "#2c78ba", active: true },
      { id: "trip", name: "Trip", color: "#1f8a70", active: false },
    ],
    system: { active_list_id: "default", active_list_name: "Grocery List", active_list_color: "#2c78ba" },
  };

  const switched = switchListLocal(state, "trip");

  assert.equal(switched, true);
  assert.equal(state.lists[0].active, false);
  assert.equal(state.lists[1].active, true);
  assert.equal(state.system.active_list_id, "trip");
  assert.equal(state.system.active_list_name, "Trip");
  assert.equal(state.system.active_list_color, "#1f8a70");
});

test("categoryDisplay and groupTitle preserve expected labels", () => {
  assert.equal(categoryDisplay("other", ["produce", "other"]), "Other");
  assert.equal(categoryDisplay("", []), "Items");
  assert.equal(groupTitle({ categories: ["produce", "other"], groups: [] }, "produce"), "Produce");
});

test("createListLocal appends and activates a new list", () => {
  const state = {
    lists: [{ id: "default", name: "Grocery List", color: "#2c78ba", active: true }],
    system: { active_list_id: "default", active_list_name: "Grocery List", active_list_color: "#2c78ba" },
    groups: [{ category: "produce", items: [{ item_ref: "1" }] }],
    completed: [{ item_ref: "done" }],
  };

  const created = createListLocal(state, { id: "trip", name: "Trip", color: "#1f8a70" });

  assert.equal(created, true);
  assert.equal(state.lists.find((list) => list.id === "trip").active, true);
  assert.equal(state.system.active_list_id, "trip");
  assert.deepEqual(state.groups, []);
  assert.deepEqual(state.completed, []);
});

test("renameListLocal updates the active list label", () => {
  const state = {
    lists: [{ id: "trip", name: "Trip", color: "#1f8a70", active: true }],
    system: { active_list_name: "Trip" },
  };

  const renamed = renameListLocal(state, "trip", "Vacation");

  assert.equal(renamed, true);
  assert.equal(state.lists[0].name, "Vacation");
  assert.equal(state.system.active_list_name, "Vacation");
});

test("deleteArchivedListLocal removes an archived list entry", () => {
  const state = {
    archived_lists: [
      { id: "trip", name: "Trip" },
      { id: "weekend", name: "Weekend" },
    ],
  };

  const deleted = deleteArchivedListLocal(state, "trip");

  assert.equal(deleted, true);
  assert.deepEqual(state.archived_lists, [{ id: "weekend", name: "Weekend" }]);
});

test("updateItemLocal updates summary and category in one pass", () => {
  const state = {
    categories: ["produce", "bakery", "other"],
    groups: [
      {
        category: "produce",
        title: "Produce",
        items: [{ item_ref: "1", summary: "Aples", category: "produce", category_display: "Produce", list_entity: "internal:produce" }],
      },
    ],
  };

  const updated = updateItemLocal(state, "1", { summary: "Apples", targetCategory: "bakery" });

  assert.equal(updated, true);
  const bakery = state.groups.find((group) => group.category === "bakery");
  assert.ok(bakery);
  assert.equal(bakery.items[0].summary, "Apples");
  assert.equal(bakery.items[0].category, "bakery");
});

test("updateItemLocal can rename a completed item", () => {
  const state = {
    completed: [{ item_ref: "done1", summary: "Mlk", description: "Added by Ryne" }],
  };

  const updated = updateItemLocal(state, "done1", { summary: "Milk" });

  assert.equal(updated, true);
  assert.equal(state.completed[0].summary, "Milk");
});

test("matchSuggestions returns prefix matches before substring, capped", () => {
  const all = [
    { item: "Whole milk", category_display: "Dairy" },
    { item: "Milk", category_display: "Dairy" },
    { item: "Almond milk", category_display: "Dairy" },
    { item: "Cereal", category_display: "Pantry" },
  ];
  const result = matchSuggestions(all, "mil", 6).map((s) => s.item);
  assert.deepEqual(result, ["Milk", "Whole milk", "Almond milk"]); // prefix first, Cereal excluded
  assert.deepEqual(matchSuggestions(all, "mil", 2).map((s) => s.item), ["Milk", "Whole milk"]);
});

test("matchSuggestions ignores empty query and exact echoes", () => {
  const all = [{ item: "Milk" }, { item: "Bananas" }];
  assert.deepEqual(matchSuggestions(all, "", 6), []);
  // an exact match of the typed text is dropped so the dropdown doesn't just echo it
  assert.deepEqual(matchSuggestions(all, "milk", 6), []);
});

test("splitPastedItems: one item per line, drops blanks", () => {
  assert.deepEqual(splitPastedItems("Milk\n\nEggs\n  \nBread\n"), ["Milk", "Eggs", "Bread"]);
});

test("splitPastedItems: strips bullets, numbers and checkboxes", () => {
  const text = "- Eggs\n* Bread\n1. Flour\n2) Sugar\n[ ] Butter\n[x] Cheese\n• Bananas\n– Salt";
  assert.deepEqual(splitPastedItems(text), ["Eggs", "Bread", "Flour", "Sugar", "Butter", "Cheese", "Bananas", "Salt"]);
});

test("splitPastedItems: strips compound markdown checkbox prefixes", () => {
  const text = "- [ ] Milk\n* [x] Eggs\n- [X]   Bread\n1. [ ] Flour";
  assert.deepEqual(splitPastedItems(text), ["Milk", "Eggs", "Bread", "Flour"]);
});

test("splitPastedItems: drops marker-only lines (matches backend count)", () => {
  // The client cap must not count "- [ ]" etc. as items; the backend discards them.
  assert.deepEqual(splitPastedItems("- [ ]\n[ ]\n-\n1.\n[x]"), []);
  assert.deepEqual(splitPastedItems("Milk\n- [ ]\nEggs"), ["Milk", "Eggs"]);
});

test("splitPastedItems: does not over-strip a marker glued to text", () => {
  assert.deepEqual(splitPastedItems("-milk\n5-spice powder"), ["-milk", "5-spice powder"]);
});

test("splitPastedItems: handles CRLF and empty input", () => {
  assert.deepEqual(splitPastedItems("A\r\nB\r\n"), ["A", "B"]);
  assert.deepEqual(splitPastedItems(""), []);
  assert.deepEqual(splitPastedItems("   \n  "), []);
});

test("itemIsRoutable / routablePastedItems: drop canonically-empty lines", () => {
  assert.equal(itemIsRoutable("Milk"), true);
  assert.equal(itemIsRoutable("5-spice"), true);
  assert.equal(itemIsRoutable("..."), false);
  assert.equal(itemIsRoutable("🎉"), false);
  assert.equal(itemIsRoutable("牛乳"), false);
  assert.equal(itemIsRoutable("the"), false);
  // routablePastedItems mirrors add_items' server-side filter after marker strip
  assert.deepEqual(routablePastedItems("Milk\n...\n- Eggs\n🎉\n牛乳\nBread"), ["Milk", "Eggs", "Bread"]);
});
