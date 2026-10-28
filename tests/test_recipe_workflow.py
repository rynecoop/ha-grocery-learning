"""Exercise the shipped action handlers with real disk images and storage validators.

Extract the runtime closures so these tests do not need a running HA server.
Only the HA scheduler, activity log and dashboard rendering are substituted.
"""
import ast
import asyncio
import contextvars
import base64
import copy
import datetime
import io
import logging
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from PIL import Image

from test_recipe_images import images
from test_storage import GroceryLearningStore, FakeStore, LearnedTerms
from test_item_logic import item_logic

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components/grocery_learning/__init__.py"
TREE = ast.parse(SOURCE.read_text())
NAMES = {"_handle_dashboard_action_impl", "_cleanup_recipe_images", "_get_recipe_image", "_run_locked", "_save", "_flush_save"}


def image_data(color):
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class SnapshotStore(FakeStore):
    async def async_load(self):
        return copy.deepcopy(self._data)

    async def async_save(self, payload):
        self._data = copy.deepcopy(payload)


class RecipeWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = GroceryLearningStore.__new__(GroceryLearningStore)
        self.store._store = SnapshotStore({})
        self.state = {"terms": LearnedTerms({}), "meals": {}, "meal_categories": [], "_action_lock": asyncio.Lock()}

        async def executor(fn, *args):
            return fn(*args)

        self.env = {
            "Any": Any, "Path": Path, "copy": copy, "recipe_images": images,
            "DOMAIN": "grocery_learning", "DEFAULT_CATEGORIES": ["other"],
            "hass": types.SimpleNamespace(data={"grocery_learning": self.state}, async_add_executor_job=executor),
            "store": self.store, "image_directory": Path(self.directory.name),
            "_LOGGER": logging.getLogger(__name__),
            "dt_util": types.SimpleNamespace(utcnow=lambda: datetime.datetime.now(datetime.timezone.utc)),
            "_multilist_enabled": lambda: True,
            "_display_item_summary": lambda name: name,
            "_normalize_list_id": item_logic.normalize_list_id,
            "_unique_meal_id": lambda name, existing: item_logic.normalize_list_id(name),
            "_merge_meal_ingredients": lambda ingredients: ingredients,
            "_migrate_meal_categories": item_logic.migrate_meal_categories,
            "_mark_changed_list": lambda _: None,
            "_IN_LOCKED_ACTION": contextvars.ContextVar("test_locked", default=False),
            "_publish_dashboard_revision": lambda _: None, "_record_activity": AsyncMock(),
            "_build_dashboard_payload_internal": AsyncMock(return_value={}),
        }
        functions = [node for node in ast.walk(TREE) if isinstance(node, ast.AsyncFunctionDef) and node.name in NAMES]
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), self.env)
        async def action(payload):
            return await self.env["_run_locked"](lambda: self.env["_handle_dashboard_action_impl"](payload))
        self.action = action

    async def save_meal(self, name="Dinner", **updates):
        return await self.action({"action": "save_meal", "name": name, "ingredients": [{"item": "rice"}], **updates})

    async def test_save_restart_export_and_restore_multiple_photos(self):
        for name, color in [("Dinner", "red"), ("Lunch", "green"), ("Breakfast", "blue")]:
            result = await self.save_meal(name, image_data=image_data(color), source_url="https://example.com/recipe")
            self.assertTrue(result["ok"])
        original = await self.store.load_meals()
        # Reload through the exact storage validator used on HA startup.
        self.state["meals"] = await self.store.load_meals()
        self.assertEqual(self.state["meals"], original)
        backup = (await self.action({"action": "export_data"}))["export"]
        self.assertNotIn("image_data", self.state["meals"]["dinner"])
        with tempfile.TemporaryDirectory() as clean:
            self.env["image_directory"] = Path(clean)
            self.store._store = SnapshotStore({})
            self.state["meals"] = {}
            result = await self.action({"action": "import_data", "export": backup})
            self.assertTrue(result["ok"])
            self.assertEqual(self.state["meals"], {key: {k: v for k, v in meal.items() if k != "category"} for key, meal in original.items()})
            for meal in self.state["meals"].values():
                photo = await self.env["_get_recipe_image"]({"image_id": meal["image_id"]})
                self.assertTrue(photo["ok"])
                self.assertEqual(photo["image_data"], backup["data"]["meals"][meal["id"]]["image_data"])

    async def test_replace_remove_shared_image_and_failed_save(self):
        await self.save_meal(image_data=image_data("red"))
        await self.save_meal("Lunch", image_data=image_data("red"))
        shared = self.state["meals"]["dinner"]["image_id"]
        await self.save_meal(meal_id="dinner", image_data=image_data("blue"))
        replacement = self.state["meals"]["dinner"]["image_id"]
        self.assertNotEqual(shared, replacement)
        self.assertTrue(images.image_path(self.env["image_directory"], shared).exists())
        before = copy.deepcopy(self.state["meals"])
        self.assertFalse((await self.save_meal(meal_id="dinner", image_data="bad"))["ok"])
        self.assertEqual(self.state["meals"], before)
        await self.save_meal(meal_id="dinner", image_data="")
        self.assertFalse(images.image_path(self.env["image_directory"], replacement).exists())
        self.assertTrue(images.image_path(self.env["image_directory"], shared).exists())
        await self.save_meal("Lunch", meal_id="lunch", image_data="")
        self.assertFalse(images.image_path(self.env["image_directory"], shared).exists())

    async def test_invalid_backup_is_atomic_and_older_backup_remains_compatible(self):
        await self.save_meal(image_data=image_data("red"))
        before = await self.store.load_meals()
        self.state["meals"] = copy.deepcopy(before)
        backup = (await self.action({"action": "export_data"}))["export"]
        backup["data"]["meals"]["invalid"] = {"name": "Invalid", "image_data": "not an image"}
        self.assertFalse((await self.action({"action": "import_data", "export": backup}))["ok"])
        self.assertEqual(self.state["meals"], before)
        self.assertEqual(await self.store.load_meals(), before)
        result = await self.action({"action": "import_data", "data": {"meals": {"old": {"name": "Old meal", "ingredients": []}}}})
        self.assertTrue(result["ok"])
        self.assertEqual(self.state["meals"]["old"]["image_id"], "")
        self.assertEqual(list(self.env["image_directory"].glob("*.webp")), [])

    async def test_failed_persistence_retains_the_previously_saved_photo(self):
        await self.save_meal(image_data=image_data("red"))
        old_id = self.state["meals"]["dinner"]["image_id"]
        self.store._store.async_save = AsyncMock(side_effect=OSError("disk full"))
        with self.assertRaises(OSError):
            await self.save_meal(meal_id="dinner", image_data=image_data("blue"))
        self.assertTrue(images.image_path(self.env["image_directory"], old_id).exists())
        persisted = await self.store.load_meals()
        self.assertEqual(persisted["dinner"]["image_id"], old_id)
