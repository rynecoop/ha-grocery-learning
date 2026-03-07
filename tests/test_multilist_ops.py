import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(module_name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


ops_module = _load_module("custom_components.grocery_learning.multilist_ops", "custom_components/grocery_learning/multilist_ops.py")

archive_list = ops_module.archive_list
restore_archived_list = ops_module.restore_archived_list
delete_archived_list = ops_module.delete_archived_list


class MultilistOpsTests(unittest.TestCase):
    def test_archive_list_moves_list_and_resets_active(self):
        model = {
            "active_list_id": "weekend",
            "lists": {
                "default": {"name": "Grocery List"},
                "weekend": {"name": "Weekend", "items": [{"id": "1", "summary": "Paint"}]},
            },
            "archived_lists": {},
        }

        result = archive_list(model, "weekend")

        self.assertEqual(result, {"ok": True, "list_name": "Weekend"})
        self.assertEqual(model["active_list_id"], "default")
        self.assertNotIn("weekend", model["lists"])
        self.assertIn("weekend", model["archived_lists"])
        self.assertEqual(model["archived_lists"]["weekend"]["items"][0]["summary"], "Paint")

    def test_archive_list_rejects_default(self):
        model = {"active_list_id": "default", "lists": {"default": {"name": "Grocery List"}}, "archived_lists": {}}
        self.assertEqual(archive_list(model, "default"), {"ok": False, "error": "cannot_archive_default"})

    def test_restore_archived_list_moves_back_and_activates(self):
        model = {
            "active_list_id": "default",
            "lists": {"default": {"name": "Grocery List"}},
            "archived_lists": {"trip": {"name": "Trip", "voice_aliases": ["travel"]}},
        }

        result = restore_archived_list(model, "trip")

        self.assertEqual(result, {"ok": True, "list_name": "Trip"})
        self.assertEqual(model["active_list_id"], "trip")
        self.assertIn("trip", model["lists"])
        self.assertNotIn("trip", model["archived_lists"])
        self.assertEqual(model["lists"]["trip"]["voice_aliases"], ["travel"])

    def test_delete_archived_list_removes_entry(self):
        model = {
            "active_list_id": "default",
            "lists": {"default": {"name": "Grocery List"}},
            "archived_lists": {"trip": {"name": "Trip"}},
        }

        result = delete_archived_list(model, "trip")

        self.assertEqual(result, {"ok": True, "list_name": "Trip"})
        self.assertEqual(model["archived_lists"], {})

    def test_restore_missing_archive_returns_error(self):
        model = {"active_list_id": "default", "lists": {"default": {"name": "Grocery List"}}, "archived_lists": {}}
        self.assertEqual(restore_archived_list(model, "trip"), {"ok": False, "error": "archive_not_found"})


if __name__ == "__main__":
    unittest.main()
