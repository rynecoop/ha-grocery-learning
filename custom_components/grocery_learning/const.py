"""Constants for Grocery Learning."""

from __future__ import annotations

DOMAIN = "grocery_learning"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

SERVICE_LEARN_TERM = "learn_term"
SERVICE_FORGET_TERM = "forget_term"
SERVICE_SYNC_HELPERS = "sync_helpers"
SERVICE_ROUTE_ITEM = "route_item"
SERVICE_APPLY_REVIEW = "apply_review"

CATEGORIES = [
    "produce",
    "bakery",
    "meat",
    "dairy",
    "frozen",
    "pantry",
    "household",
]

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
