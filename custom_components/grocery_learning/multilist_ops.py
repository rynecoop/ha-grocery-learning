"""Pure helpers for internal multilist model mutations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def archive_list(model: dict[str, Any], list_id: str) -> dict[str, Any]:
    lists = model.get("lists", {})
    archived_lists = model.get("archived_lists", {})
    if not isinstance(lists, dict) or not isinstance(archived_lists, dict):
        return {"ok": False, "error": "invalid_model"}
    if list_id == "default":
        return {"ok": False, "error": "cannot_archive_default"}
    if list_id not in lists:
        return {"ok": False, "error": "list_not_found"}

    archived_name = str(lists[list_id].get("name", list_id)).strip() or list_id
    archived_lists[list_id] = deepcopy(lists[list_id])
    lists.pop(list_id, None)
    if str(model.get("active_list_id", "")).strip() == list_id:
        model["active_list_id"] = "default"
    return {"ok": True, "list_name": archived_name}


def restore_archived_list(model: dict[str, Any], list_id: str) -> dict[str, Any]:
    lists = model.get("lists", {})
    archived_lists = model.get("archived_lists", {})
    if not isinstance(lists, dict) or not isinstance(archived_lists, dict):
        return {"ok": False, "error": "invalid_model"}
    if list_id in lists:
        return {"ok": False, "error": "list_exists"}

    archived_obj = archived_lists.get(list_id)
    if not isinstance(archived_obj, dict):
        return {"ok": False, "error": "archive_not_found"}

    restored_name = str(archived_obj.get("name", list_id)).strip() or list_id
    lists[list_id] = archived_obj
    archived_lists.pop(list_id, None)
    model["active_list_id"] = list_id
    return {"ok": True, "list_name": restored_name}


def delete_archived_list(model: dict[str, Any], list_id: str) -> dict[str, Any]:
    archived_lists = model.get("archived_lists", {})
    if not isinstance(archived_lists, dict):
        return {"ok": False, "error": "invalid_model"}

    archived_obj = archived_lists.get(list_id)
    if not isinstance(archived_obj, dict):
        return {"ok": False, "error": "archive_not_found"}

    archived_name = str(archived_obj.get("name", list_id)).strip() or list_id
    archived_lists.pop(list_id, None)
    return {"ok": True, "list_name": archived_name}
