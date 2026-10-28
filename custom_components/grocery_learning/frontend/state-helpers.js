export function categoryDisplay(category, categories = []) {
  const normalized = String(category || "").trim();
  if (!normalized) return "Items";
  if (normalized === "other") {
    return categories.length > 1 ? "Other" : "Items";
  }
  return normalized
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function groupTitle(state, category) {
  const existing = (state?.groups || []).find((group) => group.category === category);
  return existing?.title || categoryDisplay(category, state?.categories || []);
}

export function moveItemToCompleted(state, itemRef) {
  if (!state) return false;
  for (const group of state.groups || []) {
    const index = (group.items || []).findIndex((item) => item.item_ref === itemRef);
    if (index >= 0) {
      const [item] = group.items.splice(index, 1);
      state.completed = state.completed || [];
      state.completed.unshift({
        item_ref: item.item_ref,
        summary: item.summary,
        quantity: item.quantity || 1,
        description: item.description,
        list_entity: "internal:completed",
      });
      return true;
    }
  }
  return false;
}

export function recategorizeItemLocal(state, itemRef, targetCategory) {
  if (!state) return false;
  let movedItem = null;
  for (const group of state.groups || []) {
    const index = (group.items || []).findIndex((item) => item.item_ref === itemRef);
    if (index >= 0) {
      [movedItem] = group.items.splice(index, 1);
      break;
    }
  }
  if (!movedItem) return false;
  movedItem.category = targetCategory;
  movedItem.category_display = categoryDisplay(targetCategory, state?.categories || []);
  movedItem.list_entity = `internal:${targetCategory}`;
  let targetGroup = (state.groups || []).find((group) => group.category === targetCategory);
  if (!targetGroup) {
    targetGroup = { category: targetCategory, title: groupTitle(state, targetCategory), items: [] };
    state.groups = state.groups || [];
    state.groups.push(targetGroup);
  }
  targetGroup.items = targetGroup.items || [];
  targetGroup.items.unshift(movedItem);
  return true;
}

export function updateItemLocal(state, itemRef, updates = {}) {
  if (!state) return false;
  const nextSummary = String(updates.summary || "").trim();
  const nextCategory = String(updates.targetCategory || "").trim();
  const nextQuantity = Math.max(1, Number.parseInt(updates.quantity ?? 1, 10) || 1);
  let targetItem = null;
  let sourceGroup = null;
  for (const group of state.groups || []) {
    const found = (group.items || []).find((item) => item.item_ref === itemRef);
    if (found) {
      targetItem = found;
      sourceGroup = group;
      break;
    }
  }
  if (!targetItem) {
    const completedItem = (state.completed || []).find((item) => item.item_ref === itemRef);
    if (!completedItem) return false;
    if (nextSummary) {
      completedItem.summary = nextSummary;
    }
    completedItem.quantity = nextQuantity;
    return true;
  }
  if (nextSummary) {
    targetItem.summary = nextSummary;
  }
  targetItem.quantity = nextQuantity;
  if (nextCategory && nextCategory !== targetItem.category) {
    const moved = recategorizeItemLocal(state, itemRef, nextCategory);
    if (!moved) return false;
    for (const group of state.groups || []) {
      const found = (group.items || []).find((item) => item.item_ref === itemRef);
      if (found) {
        targetItem = found;
        sourceGroup = group;
        break;
      }
    }
  } else if (sourceGroup) {
    sourceGroup.title = groupTitle(state, sourceGroup.category);
  }
  return true;
}

export function switchListLocal(state, listId) {
  if (!state) return false;
  const nextList = (state.lists || []).find((list) => list.id === listId);
  if (!nextList) return false;
  for (const list of state.lists || []) {
    list.active = list.id === listId;
  }
  state.system = state.system || {};
  state.system.active_list_id = nextList.id;
  state.system.active_list_name = nextList.name;
  state.system.active_list_color = nextList.color || "#2c78ba";
  return true;
}

export function createListLocal(state, list) {
  if (!state || !list?.id || !list?.name) return false;
  state.lists = state.lists || [];
  if (state.lists.some((entry) => entry.id === list.id)) return false;
  for (const entry of state.lists) {
    entry.active = false;
  }
  const nextList = {
    id: list.id,
    name: list.name,
    color: list.color || "#2c78ba",
    active: true,
  };
  state.lists.push(nextList);
  state.lists.sort((a, b) => {
    if (a.id === "default") return -1;
    if (b.id === "default") return 1;
    return String(a.name || "").localeCompare(String(b.name || ""));
  });
  state.system = state.system || {};
  state.system.active_list_id = nextList.id;
  state.system.active_list_name = nextList.name;
  state.system.active_list_color = nextList.color;
  state.groups = [];
  state.completed = [];
  state.pending_review = { pending: false, item: "", source_list: "" };
  state.pending_duplicate = { pending: false, item: "", target: "" };
  return true;
}

export function renameListLocal(state, listId, newName) {
  if (!state || !listId || !newName) return false;
  const list = (state.lists || []).find((entry) => entry.id === listId);
  if (!list) return false;
  list.name = newName;
  if (list.active) {
    state.system = state.system || {};
    state.system.active_list_name = newName;
  }
  return true;
}

export function deleteArchivedListLocal(state, listId) {
  if (!state || !listId) return false;
  const archivedLists = state.archived_lists || [];
  const index = archivedLists.findIndex((entry) => entry.id === listId);
  if (index < 0) return false;
  archivedLists.splice(index, 1);
  return true;
}

// Filter a pre-ranked suggestion list against what the user has typed.
// Prefix matches come first (they are the strongest signal), then substring
// matches, both preserving the input's existing rank order. An exact match of
// the query is dropped so the dropdown doesn't just echo what was typed.
export function matchSuggestions(all, query, limit = 6) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return [];
  const cap = Math.max(0, limit || 0);
  const prefix = [];
  const substring = [];
  for (const suggestion of all || []) {
    const name = String(suggestion && suggestion.item || "").trim().toLowerCase();
    if (!name || name === q) continue;
    if (name.startsWith(q)) prefix.push(suggestion);
    else if (name.includes(q)) substring.push(suggestion);
  }
  return prefix.concat(substring).slice(0, cap);
}

// Mirror of item_logic.clean_bulk_line / split_pasted_items so the client counts
// a paste the same way the backend routes it — stripping leading list markers
// (bullets, "1."/"1)" numbering, "[ ]"/"[x]" checkboxes) one at a time and
// dropping lines that reduce to nothing. Keep in sync with item_logic.py.
const BULK_LINE_PREFIX_RE = /^\s*(?:[-*•·▪◦–—]+|\d+[.)]|\[[ xX]?\])(?:\s+|$)/;

export function cleanBulkLine(line) {
  let text = String(line == null ? "" : line).trim();
  let prev = null;
  while (text && text !== prev) {
    prev = text;
    text = text.replace(BULK_LINE_PREFIX_RE, "").trim();
  }
  return text.replace(/\s+/g, " ").trim();
}

export function splitPastedItems(text) {
  const out = [];
  for (const raw of String(text == null ? "" : text).split(/[\r\n]+/)) {
    const cleaned = cleanBulkLine(raw);
    if (cleaned) out.push(cleaned);
  }
  return out;
}

// Mirror of item_logic.canonical_item_phrase's emptiness test (article-strip,
// then keep only a-z0-9): route_item no-ops on any line whose canonical form is
// empty (emoji-only, punctuation like "...", or non-Latin text like "牛乳"), so
// the client count must drop those too or the cap disagrees with the server.
// Singularization can't empty a non-empty token, so it's irrelevant here.
export function itemIsRoutable(value) {
  const words = String(value == null ? "" : value).trim().split(/\s+/).filter(Boolean);
  while (words.length && (words[0].toLowerCase() === "a" || words[0].toLowerCase() === "an" || words[0].toLowerCase() === "the")) {
    words.shift();
  }
  return words.join(" ").toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).some(Boolean);
}

// Items a paste would actually add: marker-stripped and canonically non-empty,
// matching add_items' server-side filter so the client count and cap agree.
export function routablePastedItems(text) {
  return splitPastedItems(text).filter(itemIsRoutable);
}

// Decoded byte length of a base64 data URL's payload, so the recipe-photo picker
// can enforce the server's exact byte cap (recipe_images.MAX_OUTPUT) instead of
// a looser data-URL character count that would accept images the server rejects.
export function dataUrlByteLength(dataUrl) {
  const s = String(dataUrl == null ? "" : dataUrl);
  const comma = s.indexOf(",");
  const b64 = comma < 0 ? "" : s.slice(comma + 1);
  if (!b64) return 0;
  const padding = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor(b64.length * 3 / 4) - padding);
}
