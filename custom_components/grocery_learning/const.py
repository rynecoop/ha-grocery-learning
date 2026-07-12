"""Constants for Local List Assist."""

from __future__ import annotations

DOMAIN = "grocery_learning"
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

SERVICE_LEARN_TERM = "learn_term"
SERVICE_FORGET_TERM = "forget_term"
SERVICE_SYNC_HELPERS = "sync_helpers"
SERVICE_ROUTE_ITEM = "route_item"
SERVICE_ADD_TO_LIST = "add_to_list"
SERVICE_INSTALL_VOICE_SENTENCES = "install_voice_sentences"
SERVICE_APPLY_REVIEW = "apply_review"
SERVICE_CONFIRM_DUPLICATE = "confirm_duplicate"

# The default (and grocery-template) category set for new lists. Finer
# categories are ordered before their broader parent (seafood before meat;
# snacks and beverages before pantry; personal_care before pharmacy) because
# category_for_term breaks keyword ties by this order — so on a list that has
# both, "salmon" routes to Seafood and "soda" to Beverages. Existing lists keep
# their own saved category order and are unaffected.
DEFAULT_CATEGORIES = [
    "produce",
    "bakery",
    "seafood",
    "meat",
    "dairy",
    "frozen",
    "snacks",
    "beverages",
    "pantry",
    "household",
    "personal_care",
    "pharmacy",
]

# Keyword hints used to auto-sort items into the default grocery categories.
# Prefer singular forms — the matcher singularizes item words before comparing.
# Multi-word entries win over single-word ones (see item_logic.category_for_term),
# so specific phrases like "tomato sauce" route correctly even when a word like
# "tomato" also appears in another category.
DEFAULT_KEYWORDS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "dairy": (
        "milk", "egg", "cheese", "butter", "yogurt", "cream", "sour cream", "cream cheese",
        "cottage cheese", "mozzarella", "cheddar", "parmesan", "feta", "ricotta", "provolone",
        "swiss", "gouda", "brie", "string cheese", "shredded cheese", "half and half",
        "heavy cream", "whipping cream", "buttermilk", "margarine", "creamer", "almond milk",
        "oat milk", "soy milk", "eggnog",
    ),
    "meat": (
        "chicken", "beef", "steak", "pork", "turkey", "sausage", "bacon", "ham", "fish", "salmon",
        "tuna", "shrimp", "ground beef", "ground turkey", "ground chicken", "hot dog", "bratwurst",
        "meatball", "rib", "roast", "pork chop", "tenderloin", "wing", "drumstick", "thigh",
        "chicken breast", "lamb", "veal", "crab", "lobster", "scallop", "cod", "tilapia",
        "catfish", "sardine", "lunch meat", "deli meat", "pepperoni", "salami", "prosciutto",
        "chorizo", "jerky", "brisket", "filet",
    ),
    "bakery": (
        "bread", "bagel", "bun", "roll", "tortilla", "muffin", "croissant", "donut", "cake",
        "pie", "cookie", "brownie", "baguette", "pita", "naan", "biscuit", "pastry", "danish",
        "scone", "pretzel", "breadstick", "hamburger bun", "hot dog bun", "english muffin",
        "flatbread", "cupcake", "dinner roll", "sourdough", "focaccia", "ciabatta", "loaf",
    ),
    "produce": (
        "apple", "banana", "orange", "grape", "berry", "strawberry", "blueberry", "raspberry",
        "blackberry", "lettuce", "spinach", "kale", "tomato", "cucumber", "onion", "potato",
        "sweet potato", "avocado", "pepper", "bell pepper", "jalapeno", "carrot", "celery",
        "broccoli", "cauliflower", "cabbage", "zucchini", "squash", "mushroom", "garlic",
        "ginger", "lemon", "lime", "peach", "pear", "plum", "mango", "pineapple", "melon",
        "watermelon", "cantaloupe", "grapefruit", "cherry", "kiwi", "green bean", "pea",
        "asparagus", "cilantro", "parsley", "basil", "mint", "green onion", "scallion",
        "radish", "beet", "turnip", "eggplant", "apricot", "nectarine", "clementine",
        "tangerine", "salad", "coleslaw", "sprout", "artichoke", "leek", "shallot", "arugula",
        "romaine", "herb",
    ),
    "frozen": (
        "frozen", "ice cream", "frozen pizza", "hash brown", "waffle", "popsicle",
        "frozen vegetable", "frozen fruit", "frozen meal", "tv dinner", "ice", "sorbet",
        "gelato", "frozen yogurt", "tater tot", "fish stick", "frozen dinner", "edamame",
        "ice pop", "frozen chicken", "frozen berries", "frozen corn",
    ),
    "household": (
        "paper towel", "toilet paper", "tissue", "trash bag", "garbage bag", "detergent",
        "laundry detergent", "dish soap", "dish detergent", "hand soap", "sponge", "foil",
        "aluminum foil", "ziplock", "ziploc", "cloth", "fabric softener", "dryer sheet",
        "bleach", "cleaner", "disinfectant", "wipe", "napkin", "plastic wrap", "parchment paper",
        "wax paper", "storage bag", "sandwich bag", "air freshener", "candle", "light bulb",
        "battery", "paper plate", "plastic cup", "straw", "broom", "mop", "glove", "sanitizer",
        "lysol", "clorox", "windex", "swiffer", "febreze", "scrubber",
    ),
    "pharmacy": (
        "medicine", "medication", "pain relief", "ibuprofen", "acetaminophen", "tylenol",
        "advil", "aspirin", "aleve", "vitamin", "supplement", "toothpaste", "toothbrush",
        "mouthwash", "floss", "deodorant", "shampoo", "conditioner", "razor", "bandage",
        "band aid", "first aid", "cough drop", "cough syrup", "allergy", "benadryl", "claritin",
        "zyrtec", "dayquil", "nyquil", "antacid", "tums", "pepto", "sunscreen", "lotion",
        "chapstick", "lip balm", "cotton swab", "q tip", "cotton ball", "hand sanitizer",
        "body wash", "soap", "tampon", "pad", "diaper", "baby wipe", "contact solution",
        "eye drop", "melatonin", "probiotic", "laxative", "thermometer",
    ),
    "pantry": (
        "soda", "pop", "coke", "pepsi", "sprite", "juice", "coffee", "tea", "water",
        "sparkling water", "pasta", "spaghetti", "macaroni", "noodle", "ramen", "alfredo",
        "sauce", "marinara", "salsa", "pickle", "rice", "cereal", "oatmeal", "granola", "chip",
        "cracker", "snack", "soup", "broth", "stock", "flour", "sugar", "brown sugar",
        "powdered sugar", "oil", "olive oil", "vegetable oil", "canola oil", "vinegar", "spice",
        "seasoning", "salt", "black pepper", "peanut butter", "almond butter", "jam", "jelly",
        "honey", "syrup", "maple syrup", "ketchup", "mustard", "mayo", "mayonnaise", "ranch",
        "dressing", "bbq sauce", "soy sauce", "hot sauce", "sriracha", "bean", "black bean",
        "tomato sauce", "tomato paste", "diced tomato", "chicken broth", "bouillon",
        "breadcrumb", "baking soda", "baking powder", "yeast", "vanilla", "cocoa",
        "chocolate chip", "cake mix", "pancake mix", "cornstarch", "gravy", "tortilla chip",
        "popcorn", "nut", "almond", "cashew", "peanut", "trail mix", "protein bar",
        "granola bar", "fruit snack", "applesauce", "pudding", "jello", "quinoa", "couscous",
        "lentil", "cornmeal", "grits", "molasses", "coconut milk", "energy drink", "gatorade",
        "lemonade", "sweetener", "stevia", "splenda", "nutella", "raisin", "hummus",
        "guacamole", "olive", "relish", "teriyaki", "coconut water",
    ),
    # The four categories below are also represented within meat/pantry/pharmacy
    # above (so lists without these finer categories still route correctly). On a
    # list that has both, the finer category wins because it is ordered first in
    # DEFAULT_CATEGORIES.
    "seafood": (
        "fish", "salmon", "tuna", "shrimp", "crab", "lobster", "scallop", "cod", "tilapia",
        "catfish", "sardine", "seafood", "shellfish", "clam", "oyster", "mussel", "halibut",
        "mahi", "trout", "anchovy", "calamari", "crawfish", "prawn", "swordfish", "snapper",
    ),
    "beverages": (
        "soda", "pop", "coke", "pepsi", "sprite", "juice", "apple juice", "orange juice",
        "coffee", "tea", "iced tea", "water", "sparkling water", "seltzer", "energy drink",
        "gatorade", "powerade", "lemonade", "coconut water", "kombucha", "cola", "root beer",
        "ginger ale", "sports drink", "beverage", "drink", "red bull", "la croix", "tonic",
        "club soda", "smoothie",
    ),
    "snacks": (
        "chip", "cracker", "snack", "popcorn", "pretzel", "tortilla chip", "candy", "chocolate",
        "gummy", "raisin", "applesauce", "pudding", "jello", "trail mix", "protein bar",
        "granola bar", "fruit snack", "nut", "almond", "cashew", "peanut", "pistachio", "walnut",
        "pecan", "sunflower seed", "goldfish", "cheez it", "dorito", "cheeto", "beef jerky",
        "fruit cup", "rice cake", "granola",
    ),
    "personal_care": (
        "toothpaste", "toothbrush", "mouthwash", "floss", "deodorant", "shampoo", "conditioner",
        "razor", "shaving cream", "body wash", "face wash", "soap", "lotion", "moisturizer",
        "sunscreen", "chapstick", "lip balm", "cotton swab", "q tip", "cotton ball", "tampon",
        "pad", "diaper", "baby wipe", "hairspray", "makeup", "nail polish", "perfume", "cologne",
        "hairbrush", "comb",
    ),
}

HELPER_BY_CATEGORY = {
    "produce": "input_text.grocery_learned_produce",
    "bakery": "input_text.grocery_learned_bakery",
    "seafood": "input_text.grocery_learned_seafood",
    "meat": "input_text.grocery_learned_meat",
    "dairy": "input_text.grocery_learned_dairy",
    "frozen": "input_text.grocery_learned_frozen",
    "snacks": "input_text.grocery_learned_snacks",
    "beverages": "input_text.grocery_learned_beverages",
    "pantry": "input_text.grocery_learned_pantry",
    "household": "input_text.grocery_learned_household",
    "personal_care": "input_text.grocery_learned_personal_care",
    "pharmacy": "input_text.grocery_learned_pharmacy",
}

TARGET_LIST_BY_CATEGORY = {
    "produce": "todo.grocery_produce",
    "bakery": "todo.grocery_bakery",
    "seafood": "todo.grocery_seafood",
    "meat": "todo.grocery_meat",
    "dairy": "todo.grocery_dairy",
    "frozen": "todo.grocery_frozen",
    "snacks": "todo.grocery_snacks",
    "beverages": "todo.grocery_beverages",
    "pantry": "todo.grocery_pantry",
    "household": "todo.grocery_household",
    "personal_care": "todo.grocery_personal_care",
    "pharmacy": "todo.grocery_pharmacy",
    "other": "todo.grocery_other",
}

COMPLETED_LIST_ENTITY = "todo.grocery_completed"

REVIEW_ITEM_HELPER = "input_text.grocery_review_item"
REVIEW_SOURCE_HELPER = "input_text.grocery_review_source_list"
REVIEW_PENDING_HELPER = "input_boolean.grocery_review_pending"
REVIEW_CATEGORY_HELPER = "input_select.grocery_review_category"

DUPLICATE_PENDING_HELPER = "input_boolean.grocery_confirm_pending"
DUPLICATE_PENDING_ITEM_HELPER = "input_text.grocery_pending_display_item"
DUPLICATE_PENDING_TARGET_HELPER = "input_text.grocery_pending_target_list"
DUPLICATE_PENDING_KEY_HELPER = "input_text.grocery_pending_key"
DUPLICATE_PENDING_BY_HELPER = "input_text.grocery_pending_existing_added_by"
DUPLICATE_PENDING_WHEN_HELPER = "input_text.grocery_pending_existing_added_when"
DUPLICATE_PENDING_SOURCE_HELPER = "input_text.grocery_pending_existing_added_source"

CONF_INBOX_ENTITY = "inbox_entity"
CONF_AUTO_ROUTE_INBOX = "auto_route_inbox"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_CATEGORIES = "categories"
CONF_AUTO_PROVISION = "auto_provision"
CONF_AUTO_DASHBOARD = "auto_dashboard"
CONF_EXPERIMENTAL_MULTILIST = "experimental_multilist"
CONF_DEFAULT_GROCERY_CATEGORIES = "default_grocery_categories"
CONF_DEBUG_MODE = "debug_mode"
CONF_DASHBOARD_NAME = "dashboard_name"
