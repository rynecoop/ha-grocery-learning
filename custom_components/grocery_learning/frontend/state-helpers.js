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
    return true;
  }
  if (nextSummary) {
    targetItem.summary = nextSummary;
  }
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
