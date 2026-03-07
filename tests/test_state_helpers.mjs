import test from "node:test";
import assert from "node:assert/strict";
import {
  categoryDisplay,
  groupTitle,
  moveItemToCompleted,
  recategorizeItemLocal,
  switchListLocal,
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
