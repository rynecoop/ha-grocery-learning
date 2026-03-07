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
