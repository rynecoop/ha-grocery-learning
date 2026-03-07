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


matching_module = _load_module("custom_components.grocery_learning.matching", "custom_components/grocery_learning/matching.py")

normalize_voice_list_name = matching_module.normalize_voice_list_name
resolve_list_id_from_voice_name = matching_module.resolve_list_id_from_voice_name
voice_list_name_variants = matching_module.voice_list_name_variants


class MatchingTests(unittest.TestCase):
    def test_normalize_voice_list_name_handles_articles_and_possessives(self):
        self.assertEqual(normalize_voice_list_name("My Ryne's List"), "ryne")
        self.assertEqual(normalize_voice_list_name("the camping list"), "camping")

    def test_voice_list_name_variants_include_compact_and_singular_forms(self):
        variants = voice_list_name_variants("Rynes errands list")
        self.assertIn("rynes errands", variants)
        self.assertIn("ryne errand", variants)
        self.assertIn("ryneserrands", variants)
        self.assertIn("ryneserrand", variants)

    def test_resolve_list_id_from_voice_name_matches_display_name(self):
        lists = {
            "ryne_list": {"name": "Ryne's List", "voice_aliases": []},
            "default": {"name": "Grocery List", "voice_aliases": []},
        }
        self.assertEqual(resolve_list_id_from_voice_name("Ryne list", lists), "ryne_list")

    def test_resolve_list_id_from_voice_name_matches_alias(self):
        lists = {
            "ryne_list": {"name": "Ryne's List", "voice_aliases": ["Ryne", "Rynes"]},
        }
        self.assertEqual(resolve_list_id_from_voice_name("add it to rynes", lists), "")
        self.assertEqual(resolve_list_id_from_voice_name("Rynes", lists), "ryne_list")

    def test_resolve_list_id_from_voice_name_matches_list_id(self):
        lists = {
            "test_list": {"name": "Weekend Tasks", "voice_aliases": []},
        }
        self.assertEqual(resolve_list_id_from_voice_name("test list", lists), "test_list")

    def test_resolve_list_id_from_voice_name_returns_empty_for_no_match(self):
        lists = {
            "default": {"name": "Grocery List", "voice_aliases": ["shopping"]},
        }
        self.assertEqual(resolve_list_id_from_voice_name("hardware", lists), "")


if __name__ == "__main__":
    unittest.main()
