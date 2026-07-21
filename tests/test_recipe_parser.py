import importlib.util
import json
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


recipe_parser = _load_module(
    "custom_components.grocery_learning.recipe_parser",
    "custom_components/grocery_learning/recipe_parser.py",
)


def _page(ld: dict | list) -> str:
    return (
        "<html><head>"
        '<script type="application/ld+json">'
        + json.dumps(ld)
        + "</script></head><body>hi</body></html>"
    )


class RecipeParserTests(unittest.TestCase):
    def test_howto_step_list(self):
        page = _page(
            {
                "@context": "https://schema.org",
                "@type": "Recipe",
                "name": "Taco Night",
                "recipeIngredient": ["1 lb ground beef", "8 taco shells", "cheese"],
                "recipeInstructions": [
                    {"@type": "HowToStep", "text": "Brown the beef."},
                    {"@type": "HowToStep", "text": "Warm the shells."},
                    {"@type": "HowToStep", "text": "Assemble and serve."},
                ],
            }
        )
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(result["name"], "Taco Night")
        self.assertEqual(
            result["ingredients"], ["1 lb ground beef", "8 taco shells", "cheese"]
        )
        self.assertEqual(
            result["directions"],
            ["Brown the beef.", "Warm the shells.", "Assemble and serve."],
        )

    def test_instructions_as_plain_string_split_on_newlines(self):
        page = _page(
            {
                "@type": "Recipe",
                "name": "Simple Soup",
                "recipeIngredient": ["water", "salt"],
                "recipeInstructions": "Boil the water.\nAdd salt.\nSimmer.",
            }
        )
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(
            result["directions"], ["Boil the water.", "Add salt.", "Simmer."]
        )

    def test_graph_wrapper_and_type_list(self):
        page = _page(
            {
                "@context": "https://schema.org",
                "@graph": [
                    {"@type": "WebSite", "name": "A Food Blog"},
                    {
                        "@type": ["Recipe", "NewsArticle"],
                        "name": "Nested Recipe",
                        "recipeIngredient": ["flour", "sugar"],
                        "recipeInstructions": [{"@type": "HowToStep", "text": "Mix."}],
                    },
                ],
            }
        )
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(result["name"], "Nested Recipe")
        self.assertEqual(result["ingredients"], ["flour", "sugar"])
        self.assertEqual(result["directions"], ["Mix."])

    def test_howto_section_item_list(self):
        page = _page(
            {
                "@type": "Recipe",
                "name": "Two-Part Meal",
                "recipeIngredient": ["a", "b"],
                "recipeInstructions": [
                    {
                        "@type": "HowToSection",
                        "name": "Prep",
                        "itemListElement": [
                            {"@type": "HowToStep", "text": "Chop veg."},
                            {"@type": "HowToStep", "text": "Measure spices."},
                        ],
                    },
                    {
                        "@type": "HowToSection",
                        "name": "Cook",
                        "itemListElement": [
                            {"@type": "HowToStep", "text": "Saute."},
                        ],
                    },
                ],
            }
        )
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(
            result["directions"], ["Chop veg.", "Measure spices.", "Saute."]
        )

    def test_cleans_html_entities_and_tags(self):
        page = _page(
            {
                "@type": "Recipe",
                "name": "Mac &amp; Cheese",
                "recipeIngredient": ["<b>2 cups</b> pasta", "1 cup milk"],
                "recipeInstructions": [{"@type": "HowToStep", "text": "Cook &amp; stir"}],
            }
        )
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(result["name"], "Mac & Cheese")
        self.assertEqual(result["ingredients"], ["2 cups pasta", "1 cup milk"])
        self.assertEqual(result["directions"], ["Cook & stir"])

    def test_no_recipe_returns_empty(self):
        page = _page({"@type": "WebSite", "name": "Just a site"})
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(result, {"name": "", "ingredients": [], "directions": []})

    def test_missing_or_invalid_input(self):
        self.assertEqual(
            recipe_parser.parse_recipe(""),
            {"name": "", "ingredients": [], "directions": []},
        )
        self.assertEqual(
            recipe_parser.parse_recipe("<html>no ld json here</html>"),
            {"name": "", "ingredients": [], "directions": []},
        )

    def test_malformed_json_block_is_skipped(self):
        page = (
            "<html><head>"
            '<script type="application/ld+json">{ not valid json ,,, }</script>'
            '<script type="application/ld+json">'
            + json.dumps(
                {
                    "@type": "Recipe",
                    "name": "Recovered",
                    "recipeIngredient": ["x"],
                    "recipeInstructions": "Do the thing.",
                }
            )
            + "</script></head></html>"
        )
        result = recipe_parser.parse_recipe(page)
        self.assertEqual(result["name"], "Recovered")
        self.assertEqual(result["ingredients"], ["x"])
        self.assertEqual(result["directions"], ["Do the thing."])


if __name__ == "__main__":
    unittest.main()
