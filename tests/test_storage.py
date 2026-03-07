import asyncio
import importlib.util
import sys
import types
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


if "homeassistant" not in sys.modules:
    homeassistant = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    storage_mod = types.ModuleType("homeassistant.helpers.storage")

    class DummyStore:
        def __init__(self, *args, **kwargs):
            self._data = None

        async def async_load(self):
            return self._data

        async def async_save(self, payload):
            self._data = payload

    storage_mod.Store = DummyStore
    helpers.storage = storage_mod
    homeassistant.helpers = helpers
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.storage"] = storage_mod


const_module = _load_module("custom_components.grocery_learning.const", "custom_components/grocery_learning/const.py")
storage_module = _load_module("custom_components.grocery_learning.storage", "custom_components/grocery_learning/storage.py")

LearnedTerms = storage_module.LearnedTerms
GroceryLearningStore = storage_module.GroceryLearningStore


class FakeStore:
    def __init__(self, data):
        self._data = data

    async def async_load(self):
        return self._data

    async def async_save(self, payload):
        self._data = payload


class StorageTests(unittest.TestCase):
    def test_learned_terms_from_raw_filters_and_normalizes(self):
        terms = LearnedTerms.from_raw(
            {
                "produce": [" Apples ", "", "BANANAS"],
                "bakery": ["Bread"],
            },
            categories=["produce", "bakery"],
        )
        self.assertEqual(terms.data["produce"], ["apples", "bananas"])
        self.assertEqual(terms.data["bakery"], ["bread"])

    def test_load_multilist_normalizes_lists_and_archives(self):
        store = GroceryLearningStore.__new__(GroceryLearningStore)
        store._store = FakeStore(
            {
                "multilist": {
                    "active_list_id": "weekend",
                    "list_order": ["weekend", "default", "missing"],
                    "lists": {
                        "weekend": {
                            "name": "Weekend",
                            "voice_entity": "todo.lla_weekend",
                            "voice_alias_entities": ["todo.lla_alias_weekend", "", 5],
                            "voice_aliases": [" Week End ", "", "weekend"],
                            "categories": ["Errands", "Completed"],
                            "color": "",
                            "items": [
                                {"id": "1", "summary": "Paint", "category": "errands", "status": "needs_action", "description": "typed"},
                                {"id": "2", "summary": "", "category": "errands", "status": "completed"},
                            ],
                        }
                    },
                    "archived_lists": {
                        "trip": {
                            "name": "Trip",
                            "voice_aliases": ["Travel list"],
                            "categories": ["Packing"],
                            "items": [
                                {"id": "a", "summary": "Socks", "category": "packing", "status": "completed", "description": ""},
                            ],
                        }
                    },
                }
            }
        )
        result = asyncio.run(store.load_multilist(["produce", "bakery"]))

        self.assertEqual(result["active_list_id"], "weekend")
        self.assertEqual(result["list_order"], ["default", "weekend"])
        self.assertIn("default", result["lists"])
        weekend = result["lists"]["weekend"]
        self.assertEqual(weekend["voice_alias_entities"], ["todo.lla_alias_weekend"])
        self.assertEqual(weekend["voice_aliases"], ["Week End", "weekend"])
        self.assertEqual(weekend["categories"], ["errands", "other"])
        self.assertEqual(len(weekend["items"]), 1)
        self.assertEqual(weekend["items"][0]["summary"], "Paint")
        self.assertIn("trip", result["archived_lists"])
        archived = result["archived_lists"]["trip"]
        self.assertEqual(archived["voice_aliases"], ["Travel list"])
        self.assertEqual(archived["categories"], ["packing", "other"])
        self.assertEqual(archived["items"][0]["summary"], "Socks")


if __name__ == "__main__":
    unittest.main()
