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


item_logic = _load_module(
    "custom_components.grocery_learning.item_logic",
    "custom_components/grocery_learning/item_logic.py",
)


class StripLeadingArticlesTests(unittest.TestCase):
    def test_strips_leading_articles(self):
        self.assertEqual(item_logic.strip_leading_item_articles("the milk"), "milk")
        self.assertEqual(item_logic.strip_leading_item_articles("a banana"), "banana")
        self.assertEqual(item_logic.strip_leading_item_articles("an apple"), "apple")

    def test_only_strips_leading_run(self):
        self.assertEqual(item_logic.strip_leading_item_articles("the the milk"), "milk")
        # An article in the middle is preserved.
        self.assertEqual(item_logic.strip_leading_item_articles("milk the good kind"), "milk the good kind")

    def test_handles_empty_and_whitespace(self):
        self.assertEqual(item_logic.strip_leading_item_articles(""), "")
        self.assertEqual(item_logic.strip_leading_item_articles("   the   eggs  "), "eggs")


class SingularizeTokenTests(unittest.TestCase):
    def test_regular_plurals(self):
        self.assertEqual(item_logic.singularize_token("apples"), "apple")
        self.assertEqual(item_logic.singularize_token("bananas"), "banana")

    def test_ies_plurals(self):
        self.assertEqual(item_logic.singularize_token("berries"), "berry")
        self.assertEqual(item_logic.singularize_token("cherries"), "cherry")

    def test_es_family_plurals(self):
        self.assertEqual(item_logic.singularize_token("boxes"), "box")
        self.assertEqual(item_logic.singularize_token("dishes"), "dish")
        self.assertEqual(item_logic.singularize_token("tomatoes"), "tomato")

    def test_does_not_overstrip(self):
        self.assertEqual(item_logic.singularize_token("glass"), "glass")  # ss
        self.assertEqual(item_logic.singularize_token("bus"), "bus")      # short + us
        self.assertEqual(item_logic.singularize_token("axis"), "axis")    # is
        self.assertEqual(item_logic.singularize_token("egg"), "egg")      # <= 3 chars

    def test_leaves_numeric_tokens_alone(self):
        self.assertEqual(item_logic.singularize_token("2ss"), "2ss")


class CanonicalItemPhraseTests(unittest.TestCase):
    def test_articles_case_and_plural(self):
        self.assertEqual(item_logic.canonical_item_phrase("The Apples"), "apple")
        self.assertEqual(item_logic.canonical_item_phrase("  Bananas  "), "banana")

    def test_only_last_token_singularized(self):
        # Leading modifier keeps its form; only the final noun is singularized.
        self.assertEqual(item_logic.canonical_item_phrase("green peppers"), "green pepper")

    def test_strips_punctuation(self):
        self.assertEqual(item_logic.canonical_item_phrase("Coke (2-liter)!"), "coke 2 liter")

    def test_empty(self):
        self.assertEqual(item_logic.canonical_item_phrase(""), "")
        self.assertEqual(item_logic.canonical_item_phrase("!!!"), "")


class DisplayItemSummaryTests(unittest.TestCase):
    def test_preserves_case_strips_article_collapses_space(self):
        self.assertEqual(item_logic.display_item_summary("the  Whole   Milk"), "Whole Milk")

    def test_does_not_singularize(self):
        self.assertEqual(item_logic.display_item_summary("Bananas"), "Bananas")


class NormalizeCategoryAndListIdTests(unittest.TestCase):
    def test_normalize_category_slugifies(self):
        self.assertEqual(item_logic.normalize_category("Frozen Foods"), "frozen_foods")
        self.assertEqual(item_logic.normalize_category("  Pharmacy!! "), "pharmacy")
        self.assertEqual(item_logic.normalize_category("A/B & C"), "a_b_c")

    def test_normalize_category_empty(self):
        self.assertEqual(item_logic.normalize_category(""), "")
        self.assertEqual(item_logic.normalize_category("   "), "")
        self.assertEqual(item_logic.normalize_category("!!!"), "")

    def test_normalize_list_id_falls_back_to_list(self):
        self.assertEqual(item_logic.normalize_list_id("Costco Run"), "costco_run")
        self.assertEqual(item_logic.normalize_list_id(""), "list")
        self.assertEqual(item_logic.normalize_list_id("!!!"), "list")


class CoerceQuantityTests(unittest.TestCase):
    def test_positive_ints(self):
        self.assertEqual(item_logic.coerce_quantity("3"), 3)
        self.assertEqual(item_logic.coerce_quantity(5), 5)

    def test_floor_of_at_least_one(self):
        self.assertEqual(item_logic.coerce_quantity(0), 1)
        self.assertEqual(item_logic.coerce_quantity(-4), 1)

    def test_invalid_defaults_to_one(self):
        self.assertEqual(item_logic.coerce_quantity("abc"), 1)
        self.assertEqual(item_logic.coerce_quantity(None), 1)
        self.assertEqual(item_logic.coerce_quantity(""), 1)


class MetaQuantityTests(unittest.TestCase):
    def test_prefers_current_quantity(self):
        self.assertEqual(item_logic.meta_quantity({"current_quantity": "4", "add_count": "9"}), 4)

    def test_falls_back_through_keys(self):
        self.assertEqual(item_logic.meta_quantity({"total_quantity": "3"}), 3)
        self.assertEqual(item_logic.meta_quantity({"add_count": "2"}), 2)
        self.assertEqual(item_logic.meta_quantity({}), 1)


class ContributorTests(unittest.TestCase):
    def test_decode_from_json_dedupes_case_insensitively(self):
        meta = {"contributors_json": '["Ryne", "ryne", "Sam"]'}
        self.assertEqual(item_logic.decode_contributors(meta), ["Ryne", "Sam"])

    def test_decode_falls_back_to_last_added_by_name(self):
        self.assertEqual(item_logic.decode_contributors({"last_added_by_name": "Ryne"}), ["Ryne"])
        self.assertEqual(item_logic.decode_contributors({}), [])

    def test_decode_handles_invalid_json(self):
        self.assertEqual(
            item_logic.decode_contributors({"contributors_json": "not json", "last_added_by_name": "Sam"}),
            ["Sam"],
        )

    def test_format(self):
        self.assertEqual(item_logic.format_contributors([]), "Unknown")
        self.assertEqual(item_logic.format_contributors(["Ryne"]), "Ryne")
        self.assertEqual(item_logic.format_contributors(["Ryne", "Sam"]), "Ryne and Sam")
        self.assertEqual(item_logic.format_contributors(["A", "B", "C"]), "A, B, and C")


class MergeMetaRecordsTests(unittest.TestCase):
    def test_quantities_sum_not_drift(self):
        # Regression guard for the quantity-drift class of bugs: merging must add.
        existing = {"current_quantity": "2", "add_count": "2"}
        incoming = {"current_quantity": "3", "add_count": "1"}
        merged = item_logic.merge_meta_records(existing, incoming)
        self.assertEqual(merged["current_quantity"], "5")
        self.assertEqual(merged["add_count"], "3")

    def test_empty_sides_passthrough(self):
        self.assertEqual(item_logic.merge_meta_records({}, {"current_quantity": "2"}), {"current_quantity": "2"})
        self.assertEqual(item_logic.merge_meta_records({"current_quantity": "2"}, {}), {"current_quantity": "2"})

    def test_contributors_unioned_and_last_fields_prefer_incoming(self):
        existing = {
            "current_quantity": "1",
            "contributors_json": '["Ryne"]',
            "last_added_by_name": "Ryne",
            "last_source": "typed",
        }
        incoming = {
            "current_quantity": "1",
            "contributors_json": '["Sam"]',
            "last_added_by_name": "Sam",
            "last_source": "voice_assistant",
        }
        merged = item_logic.merge_meta_records(existing, incoming)
        self.assertEqual(item_logic.decode_contributors(merged), ["Ryne", "Sam"])
        self.assertEqual(merged["last_added_by_name"], "Sam")
        self.assertEqual(merged["last_source"], "voice_assistant")
        self.assertEqual(merged["current_quantity"], "2")


class CategoryForTermTests(unittest.TestCase):
    CATEGORIES = ["produce", "dairy", "pantry"]
    KEYWORDS = {
        "dairy": ("milk", "egg", "cheese"),
        "produce": ("apple", "banana", "pepper"),
        "pantry": ("peanut butter", "rice"),
    }

    def test_learned_term_wins_over_keywords(self):
        terms = {"pantry": ["milk"]}  # user taught that "milk" goes to pantry
        self.assertEqual(
            item_logic.category_for_term(terms, "milk", self.CATEGORIES, self.KEYWORDS),
            "pantry",
        )

    def test_keyword_match(self):
        self.assertEqual(
            item_logic.category_for_term({}, "cheese", self.CATEGORIES, self.KEYWORDS),
            "dairy",
        )

    def test_keyword_match_tolerates_plurals(self):
        # "eggs" should still route via the "egg" keyword.
        self.assertEqual(
            item_logic.category_for_term({}, "eggs", self.CATEGORIES, self.KEYWORDS),
            "dairy",
        )

    def test_multiword_keyword(self):
        self.assertEqual(
            item_logic.category_for_term({}, "peanut butter", self.CATEGORIES, self.KEYWORDS),
            "pantry",
        )

    def test_no_match_returns_other(self):
        self.assertEqual(
            item_logic.category_for_term({}, "hammer", self.CATEGORIES, self.KEYWORDS),
            "other",
        )

    def test_empty_normalized_returns_other(self):
        self.assertEqual(
            item_logic.category_for_term({"dairy": [""]}, "", self.CATEGORIES, self.KEYWORDS),
            "other",
        )


class ReorderCategoryItemsTests(unittest.TestCase):
    def _items(self):
        return [
            {"id": "a", "category": "produce", "status": "needs_action"},
            {"id": "x", "category": "dairy", "status": "needs_action"},
            {"id": "b", "category": "produce", "status": "needs_action"},
            {"id": "c", "category": "produce", "status": "completed"},
            {"id": "d", "category": "produce", "status": "needs_action"},
        ]

    def test_reorders_within_category_only(self):
        result = item_logic.reorder_category_items(self._items(), "produce", ["d", "a", "b"])
        # Produce active slots are indices 0, 2, 4 -> now d, a, b in those slots.
        self.assertEqual([i["id"] for i in result], ["d", "x", "a", "c", "b"])
        # The dairy item and the completed item never moved.
        self.assertEqual(result[1]["id"], "x")
        self.assertEqual(result[3]["id"], "c")

    def test_unmentioned_ids_keep_order_at_end(self):
        result = item_logic.reorder_category_items(self._items(), "produce", ["d"])
        # d first, then a and b keep their relative order.
        self.assertEqual([i["id"] for i in result if i["category"] == "produce" and i["status"] == "needs_action"], ["d", "a", "b"])

    def test_noop_for_single_or_empty(self):
        one = [{"id": "a", "category": "produce", "status": "needs_action"}]
        self.assertEqual(item_logic.reorder_category_items(one, "produce", ["a"]), one)
        self.assertEqual(item_logic.reorder_category_items([], "produce", []), [])

    def test_ignores_unknown_ids(self):
        result = item_logic.reorder_category_items(self._items(), "produce", ["zzz", "b", "a", "d"])
        self.assertEqual([i["id"] for i in result if i["category"] == "produce" and i["status"] == "needs_action"], ["b", "a", "d"])


const = _load_module(
    "custom_components.grocery_learning.const",
    "custom_components/grocery_learning/const.py",
)


class CategorySpecificityTests(unittest.TestCase):
    CATEGORIES = ["produce", "dairy", "pantry"]
    KEYWORDS = {
        "produce": ("tomato", "pepper"),
        "dairy": ("butter", "milk"),
        "pantry": ("tomato sauce", "peanut butter", "black pepper", "coconut milk"),
    }

    def route(self, text):
        return item_logic.category_for_term(
            {}, item_logic.canonical_item_phrase(text), self.CATEGORIES, self.KEYWORDS
        )

    def test_multiword_keyword_beats_single(self):
        self.assertEqual(self.route("tomato sauce"), "pantry")
        self.assertEqual(self.route("peanut butter"), "pantry")
        self.assertEqual(self.route("black pepper"), "pantry")
        self.assertEqual(self.route("coconut milk"), "pantry")

    def test_single_word_still_routes(self):
        self.assertEqual(self.route("tomato"), "produce")
        self.assertEqual(self.route("butter"), "dairy")
        self.assertEqual(self.route("bell pepper"), "produce")  # only produce has "pepper"


class RealKeywordRoutingTests(unittest.TestCase):
    """Route common grocery phrases through the shipped keyword table."""

    def route(self, text):
        return item_logic.category_for_term(
            {},
            item_logic.canonical_item_phrase(text),
            list(const.DEFAULT_CATEGORIES),
            const.DEFAULT_KEYWORDS_BY_CATEGORY,
        )

    def test_common_items(self):
        cases = {
            "bananas": "produce",
            "baby spinach": "produce",
            "chicken breast": "meat",
            "ground beef": "meat",
            "whole milk": "dairy",
            "almond milk": "dairy",
            "shredded cheddar": "dairy",
            "everything bagels": "bakery",
            "sourdough bread": "bakery",
            "ice cream": "frozen",
            "frozen pizza": "frozen",
            "tomato sauce": "pantry",
            "peanut butter": "pantry",
            "coconut milk": "pantry",
            "black pepper": "pantry",
            "paper towels": "household",
            "laundry detergent": "household",
            "ibuprofen": "pharmacy",
            "toothpaste": "personal_care",
        }
        for text, expected in cases.items():
            self.assertEqual(self.route(text), expected, f"{text!r} should route to {expected}")

    def test_new_finer_categories(self):
        # On a new list (full default set), the finer split categories win over
        # their broad parent because they are ordered first in DEFAULT_CATEGORIES.
        cases = {
            "salmon": "seafood",
            "shrimp": "seafood",
            "soda": "beverages",
            "orange juice": "beverages",
            "coffee": "beverages",
            "potato chips": "snacks",
            "trail mix": "snacks",
            "shampoo": "personal_care",
            "deodorant": "personal_care",
            "toothpaste": "personal_care",
            # broad-parent items with no finer split stay put
            "ibuprofen": "pharmacy",
            "canned black beans": "pantry",
            "chicken breast": "meat",
        }
        for text, expected in cases.items():
            self.assertEqual(self.route(text), expected, f"{text!r} should route to {expected}")


class LegacyListNoRegressionTests(unittest.TestCase):
    """A pre-existing list without the finer categories must route unchanged."""

    LEGACY = ["produce", "bakery", "meat", "dairy", "frozen", "pantry", "household", "pharmacy"]

    def route(self, text):
        return item_logic.category_for_term(
            {}, item_logic.canonical_item_phrase(text), self.LEGACY, const.DEFAULT_KEYWORDS_BY_CATEGORY
        )

    def test_finer_items_fall_back_to_broad_parent(self):
        cases = {
            "salmon": "meat",
            "soda": "pantry",
            "orange juice": "pantry",
            "potato chips": "pantry",
            "shampoo": "pharmacy",
            "toothpaste": "pharmacy",
        }
        for text, expected in cases.items():
            self.assertEqual(self.route(text), expected, f"{text!r} should route to {expected} on a legacy list")

    def test_head_noun_breaks_ties(self):
        # "soup" is the head noun -> pantry, even though the modifier word also
        # appears in another category (mushroom/tomato/chicken/potato = produce/meat).
        self.assertEqual(self.route("mushroom soup"), "pantry")
        self.assertEqual(self.route("cream of mushroom soup"), "pantry")
        self.assertEqual(self.route("tomato soup"), "pantry")
        self.assertEqual(self.route("chicken noodle soup"), "pantry")
        self.assertEqual(self.route("potato soup"), "pantry")
        # But the fresh items still route to their real section.
        self.assertEqual(self.route("mushrooms"), "produce")
        self.assertEqual(self.route("roma tomatoes"), "produce")

    def test_unknown_still_other(self):
        self.assertEqual(self.route("garden hose"), "other")


class MergeMealIngredientsTests(unittest.TestCase):
    def test_accepts_strings_and_mappings(self):
        result = item_logic.merge_meal_ingredients(["eggs", {"item": "milk"}])
        self.assertEqual(result, [{"item": "eggs"}, {"item": "milk"}])

    def test_tidies_and_drops_blanks(self):
        result = item_logic.merge_meal_ingredients(["  the bread  ", "", "   ", {"item": ""}])
        # leading article stripped, whitespace collapsed, blanks removed
        self.assertEqual(result, [{"item": "bread"}])

    def test_dedupes_case_insensitively_preserving_order(self):
        result = item_logic.merge_meal_ingredients(["Salsa", "salsa", "SALSA", "chips"])
        self.assertEqual(result, [{"item": "Salsa"}, {"item": "chips"}])

    def test_empty_input(self):
        self.assertEqual(item_logic.merge_meal_ingredients([]), [])
        self.assertEqual(item_logic.merge_meal_ingredients(None), [])


class DedupeRankSuggestionsTests(unittest.TestCase):
    def test_dedupes_by_normalized_and_keeps_best(self):
        entries = [
            {"normalized": "milk", "item": "Milk", "count": 2, "last": "2026-01-01", "source": "frequent"},
            {"normalized": "milk", "item": "milk", "count": 5, "last": "2026-02-01", "source": "history"},
            {"normalized": "eggs", "item": "Eggs", "count": 3, "last": "2026-01-15", "source": "frequent"},
        ]
        out = item_logic.dedupe_rank_suggestions(entries)
        self.assertEqual([s["item"] for s in out], ["Milk", "Eggs"])  # milk(5) ranks above eggs(3)
        self.assertEqual(out[0]["count"], 5)          # max count across sources
        self.assertEqual(out[0]["last"], "2026-02-01")  # most recent timestamp
        self.assertEqual(out[0]["item"], "Milk")       # first non-empty display kept

    def test_ranks_by_recency_on_count_tie(self):
        entries = [
            {"normalized": "a", "item": "A", "count": 3, "last": "2026-01-01"},
            {"normalized": "b", "item": "B", "count": 3, "last": "2026-02-01"},
        ]
        self.assertEqual([s["item"] for s in item_logic.dedupe_rank_suggestions(entries)], ["B", "A"])

    def test_skips_blank_normalized_and_caps(self):
        entries = [{"normalized": "", "item": "x", "count": 9}]
        entries += [{"normalized": f"n{i}", "item": f"I{i}", "count": i} for i in range(5)]
        out = item_logic.dedupe_rank_suggestions(entries, limit=2)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(s["normalized"] for s in out))


class CleanSuggestionDisplayTests(unittest.TestCase):
    def test_standardizes_capitalization(self):
        self.assertEqual(item_logic.clean_suggestion_display("apples"), "Apples")
        self.assertEqual(item_logic.clean_suggestion_display("APPLES"), "Apples")
        self.assertEqual(item_logic.clean_suggestion_display("aPPles"), "Apples")
        self.assertEqual(item_logic.clean_suggestion_display("whole milk"), "Whole Milk")

    def test_strips_trailing_quantity_suffix(self):
        self.assertEqual(item_logic.clean_suggestion_display("Avocado x 3"), "Avocado")
        self.assertEqual(item_logic.clean_suggestion_display("avocado x3"), "Avocado")
        self.assertEqual(item_logic.clean_suggestion_display("Bananas ×2"), "Bananas")

    def test_collapses_whitespace_and_handles_blank(self):
        self.assertEqual(item_logic.clean_suggestion_display("  green   beans  "), "Green Beans")
        self.assertEqual(item_logic.clean_suggestion_display(""), "")
        self.assertEqual(item_logic.clean_suggestion_display("   "), "")

    def test_keeps_interior_digits_and_symbols(self):
        # only a trailing quantity is stripped, not numbers that are part of the name
        self.assertEqual(item_logic.clean_suggestion_display("2% milk"), "2% Milk")
        self.assertEqual(item_logic.clean_suggestion_display("half & half"), "Half & Half")


class UniqueMealIdTests(unittest.TestCase):
    def test_slugifies_name(self):
        self.assertEqual(item_logic.unique_meal_id("Taco Night", []), "taco_night")

    def test_avoids_collisions(self):
        self.assertEqual(item_logic.unique_meal_id("Taco Night", ["taco_night"]), "taco_night_2")
        self.assertEqual(
            item_logic.unique_meal_id("Taco Night", ["taco_night", "taco_night_2"]),
            "taco_night_3",
        )

    def test_blank_name_falls_back(self):
        # normalize_list_id falls back to "list" for empty input
        self.assertEqual(item_logic.unique_meal_id("", []), "list")


class SelectFrequentTests(unittest.TestCase):
    def _freq(self, **entries):
        return entries

    def test_requires_count_at_least_two(self):
        freq = {
            "eggs": {"display": "Eggs", "count": 1},
            "milk": {"display": "Milk", "count": 2},
        }
        result = item_logic.select_frequent(freq, set())
        self.assertEqual(result, [{"item": "Milk", "count": 2}])

    def test_excludes_dismissed_and_on_list(self):
        freq = {
            "eggs": {"display": "Eggs", "count": 5},
            "milk": {"display": "Milk", "count": 4, "dismissed": True},
            "butter": {"display": "Butter", "count": 3},
        }
        result = item_logic.select_frequent(freq, {"butter"})
        self.assertEqual(result, [{"item": "Eggs", "count": 5}])

    def test_ranks_by_count_then_recency_and_caps(self):
        freq = {
            "a": {"display": "A", "count": 3, "last": "2026-01-01"},
            "b": {"display": "B", "count": 5, "last": "2026-01-01"},
            "c": {"display": "C", "count": 3, "last": "2026-02-01"},
        }
        result = item_logic.select_frequent(freq, set(), limit=2)
        # B (highest count) first; then C beats A on recency at equal count
        self.assertEqual(result, [{"item": "B", "count": 5}, {"item": "C", "count": 3}])

    def test_falls_back_to_key_when_display_blank(self):
        freq = {"paper towels": {"display": "  ", "count": 2}}
        result = item_logic.select_frequent(freq, set())
        self.assertEqual(result, [{"item": "paper towels", "count": 2}])


if __name__ == "__main__":
    unittest.main()
