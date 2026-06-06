import re


TAG_DEFINITIONS = [
    {"key": "happy_hour", "label": "Happy Hour", "kind": "occasion", "keywords": ["happy hour", "hh", "drink special"]},
    {"key": "pizza", "label": "Pizza", "kind": "dish", "keywords": ["pizza", "pepperoni", "wood-fired"]},
    {"key": "burgers", "label": "Burgers", "kind": "dish", "keywords": ["burger", "burgers", "smashburger", "smash burger"]},
    {"key": "seafood", "label": "Seafood", "kind": "dish", "keywords": ["seafood", "oyster", "oysters", "salmon", "halibut", "fish", "crab", "shrimp", "cioppino"]},
    {"key": "date_night", "label": "Date Night", "kind": "occasion", "keywords": ["date night", "for two", "two can dine", "prix fixe", "three course", "3 course"]},
    {"key": "brunch", "label": "Brunch", "kind": "occasion", "keywords": ["brunch", "mimosa", "benedict", "breakfast"]},
    {"key": "cocktails", "label": "Cocktails", "kind": "dish", "keywords": ["cocktail", "cocktails", "margarita", "old fashioned", "martini", "wine", "beer", "pint"]},
    {"key": "pasta", "label": "Pasta", "kind": "dish", "keywords": ["pasta", "spaghetti", "carbonara", "ravioli", "lasagna", "linguine"]},
    {"key": "tacos", "label": "Tacos", "kind": "dish", "keywords": ["taco", "tacos", "taqueria"]},
    {"key": "sushi", "label": "Sushi", "kind": "dish", "keywords": ["sushi", "roll", "sashimi", "nigiri"]},
    {"key": "steak", "label": "Steak", "kind": "dish", "keywords": ["steak", "prime rib", "ribeye", "filet", "sirloin"]},
    {"key": "dessert", "label": "Dessert", "kind": "dish", "keywords": ["dessert", "cake", "pie", "pastry", "cookie", "gelato"]},
    {"key": "italian", "label": "Italian", "kind": "cuisine", "keywords": ["italian", "pasta", "pizza", "risotto"]},
    {"key": "mexican", "label": "Mexican", "kind": "cuisine", "keywords": ["mexican", "taco", "tacos", "burrito", "enchilada", "margarita"]},
    {"key": "japanese", "label": "Japanese", "kind": "cuisine", "keywords": ["japanese", "sushi", "ramen", "teriyaki", "sashimi"]},
    {"key": "american", "label": "American", "kind": "cuisine", "keywords": ["american", "burger", "steak", "diner", "sandwich"]},
    {"key": "bbq", "label": "BBQ", "kind": "cuisine", "keywords": ["bbq", "barbecue", "brisket", "ribs", "pulled pork", "smoked"]},
    {"key": "bakery", "label": "Bakery", "kind": "cuisine", "keywords": ["bakery", "bread", "pastry", "croissant", "donut"]},
    {"key": "coffee", "label": "Coffee", "kind": "cuisine", "keywords": ["coffee", "espresso", "latte", "cafe"]},
]

TAG_BY_KEY = {item["key"]: item for item in TAG_DEFINITIONS}
APPROVED_TAG_KEYS = set(TAG_BY_KEY)
FEED_TAG_KEYS = ["happy_hour", "pizza", "burgers", "seafood", "date_night", "brunch"]
CUISINE_TAG_KEYS = [item["key"] for item in TAG_DEFINITIONS if item["kind"] == "cuisine"]


def normalize_tag_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")


def validate_tag_keys(values, allowed=None):
    allowed_keys = set(allowed or APPROVED_TAG_KEYS)
    if isinstance(values, str):
        values = re.split(r"[\s,;|]+", values)
    cleaned = []
    for value in values or []:
        key = normalize_tag_key(value)
        if key in allowed_keys and key not in cleaned:
            cleaned.append(key)
    return cleaned


def parse_tag_text(value, allowed=None):
    return validate_tag_keys(re.split(r"[\s,;|]+", value or ""), allowed=allowed)


def serialize_tag_keys(values, allowed=None):
    return ",".join(validate_tag_keys(values, allowed=allowed))


def tag_label(key):
    return TAG_BY_KEY.get(normalize_tag_key(key), {}).get("label", "")


def tag_options(kind=None):
    items = TAG_DEFINITIONS
    if kind:
        items = [item for item in items if item["kind"] == kind]
    return [{"key": item["key"], "label": item["label"]} for item in items]


def tag_labels(value):
    return [tag_label(key) for key in parse_tag_text(value) if tag_label(key)]


def feed_tag_options():
    return [{"key": key, "label": tag_label(key)} for key in FEED_TAG_KEYS]


def _contains_keyword(text, keyword):
    return re.search(rf"\b{re.escape(keyword)}\b", text, flags=re.I) is not None


def infer_tags_from_text(*parts, allowed=None):
    text = " ".join(str(part or "") for part in parts).casefold()
    allowed_keys = set(allowed or APPROVED_TAG_KEYS)
    inferred = []
    for item in TAG_DEFINITIONS:
        if item["key"] not in allowed_keys:
            continue
        if any(_contains_keyword(text, keyword.casefold()) for keyword in item["keywords"]):
            inferred.append(item["key"])
    return validate_tag_keys(inferred, allowed=allowed)


def infer_restaurant_cuisine_tags(restaurant):
    parts = [
        getattr(restaurant, "category", ""),
        getattr(restaurant, "subtypes", ""),
        getattr(restaurant, "primary_type", ""),
        getattr(restaurant, "primary_type_label", ""),
        getattr(restaurant, "editorial_summary", ""),
        getattr(restaurant, "name", ""),
    ]
    return infer_tags_from_text(*parts, allowed=CUISINE_TAG_KEYS)


def primary_tag_from(tag_keys, requested=None):
    keys = validate_tag_keys(tag_keys)
    requested_key = normalize_tag_key(requested)
    if requested_key in keys:
        return requested_key
    return keys[0] if keys else None
