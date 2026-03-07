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


_load_module("custom_components.grocery_learning.const", "custom_components/grocery_learning/const.py")
templates_module = _load_module("custom_components.grocery_learning.list_templates", "custom_components/grocery_learning/list_templates.py")

categories_for_template = templates_module.categories_for_template
template_presets = templates_module.template_presets


class ListTemplateTests(unittest.TestCase):
    def test_grocery_template_uses_fallback_categories(self):
        self.assertEqual(
            categories_for_template("grocery", ["produce", "bakery", "pharmacy"]),
            ["produce", "bakery", "pharmacy"],
        )

    def test_flat_template_has_no_categories(self):
        self.assertEqual(categories_for_template("flat", ["produce"]), [])

    def test_named_template_returns_expected_categories(self):
        self.assertEqual(
            categories_for_template("travel"),
            ["packing", "documents", "booking", "errands", "other"],
        )

    def test_template_presets_includes_flat_and_grocery(self):
        presets = template_presets(["produce", "bakery"])
        self.assertEqual(presets["flat"], [])
        self.assertEqual(presets["grocery"], ["produce", "bakery"])


if __name__ == "__main__":
    unittest.main()
