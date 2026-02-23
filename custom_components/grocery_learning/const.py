"""Constants for Local Grocery Assistant."""

from __future__ import annotations

DOMAIN = "grocery_learning"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

SERVICE_LEARN_TERM = "learn_term"
SERVICE_FORGET_TERM = "forget_term"
SERVICE_SYNC_HELPERS = "sync_helpers"
SERVICE_ROUTE_ITEM = "route_item"
SERVICE_APPLY_REVIEW = "apply_review"

DEFAULT_CATEGORIES = [
    "produce",
    "bakery",
    "meat",
    "dairy",
    "frozen",
    "pantry",
    "household",
]

DEFAULT_KEYWORDS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "dairy": ("milk", "egg", "eggs", "cheese", "butter", "yogurt", "cream", "sour cream"),
    "meat": ("chicken", "beef", "steak", "pork", "turkey", "sausage", "bacon", "ham", "fish", "salmon", "tuna", "shrimp"),
    "bakery": ("bread", "bagel", "bun", "roll", "tortilla", "muffin", "croissant", "donut", "donuts"),
    "produce": (
        "apple",
        "banana",
        "orange",
        "grape",
        "berry",
        "berries",
        "lettuce",
        "spinach",
        "kale",
        "tomato",
        "cucumber",
        "onion",
        "potato",
        "avocado",
        "pepper",
        "carrot",
    ),
    "frozen": ("frozen", "ice cream", "frozen pizza", "hash brown", "waffles"),
    "household": (
        "paper towel",
        "toilet paper",
        "tissue",
        "trash bag",
        "detergent",
        "dish soap",
        "hand soap",
        "sponge",
        "foil",
        "ziplock",
        "ziploc",
        "cloth",
    ),
    "pantry": (
        "soda",
        "pop",
        "coke",
        "juice",
        "coffee",
        "tea",
        "pasta",
        "alfredo",
        "sauce",
        "pickle",
        "pickles",
        "rice",
        "cereal",
        "chips",
        "cracker",
        "crackers",
        "snack",
        "soup",
        "flour",
        "sugar",
        "oil",
        "vinegar",
        "spice",
        "seasoning",
        "peanut butter",
        "jam",
    ),
}

HELPER_BY_CATEGORY = {
    "produce": "input_text.grocery_learned_produce",
    "bakery": "input_text.grocery_learned_bakery",
    "meat": "input_text.grocery_learned_meat",
    "dairy": "input_text.grocery_learned_dairy",
    "frozen": "input_text.grocery_learned_frozen",
    "pantry": "input_text.grocery_learned_pantry",
    "household": "input_text.grocery_learned_household",
}

TARGET_LIST_BY_CATEGORY = {
    "produce": "todo.grocery_produce",
    "bakery": "todo.grocery_bakery",
    "meat": "todo.grocery_meat",
    "dairy": "todo.grocery_dairy",
    "frozen": "todo.grocery_frozen",
    "pantry": "todo.grocery_pantry",
    "household": "todo.grocery_household",
    "other": "todo.grocery_other",
}

REVIEW_ITEM_HELPER = "input_text.grocery_review_item"
REVIEW_SOURCE_HELPER = "input_text.grocery_review_source_list"
REVIEW_PENDING_HELPER = "input_boolean.grocery_review_pending"
REVIEW_CATEGORY_HELPER = "input_select.grocery_review_category"

DUPLICATE_PENDING_HELPER = "input_boolean.grocery_confirm_pending"
DUPLICATE_PENDING_ITEM_HELPER = "input_text.grocery_pending_display_item"
DUPLICATE_PENDING_TARGET_HELPER = "input_text.grocery_pending_target_list"
DUPLICATE_PENDING_KEY_HELPER = "input_text.grocery_pending_key"

CONF_INBOX_ENTITY = "inbox_entity"
CONF_AUTO_ROUTE_INBOX = "auto_route_inbox"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_CATEGORIES = "categories"
CONF_AUTO_PROVISION = "auto_provision"
CONF_AUTO_DASHBOARD = "auto_dashboard"
