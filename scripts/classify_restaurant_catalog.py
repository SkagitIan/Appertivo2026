"""Classify restaurant catalog rows without deleting records.

The rules use full Google Places type metadata. Preview mode is the default.
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1]))


COFFEE_TYPES = {"coffee shop", "coffee stand", "coffee roastery", "coffee store"}
RETAIL_TYPES = {
    "bed & breakfast",
    "book store",
    "brewing supply store",
    "butcher shop",
    "convenience store",
    "farmers' market",
    "filipino grocery store",
    "food and beverage consultant",
    "food and beverage exporter",
    "fresh food market",
    "general store",
    "gourmet grocery store",
    "grocery store",
    "health and beauty shop",
    "hotel",
    "liquor store",
    "mexican grocery store",
    "seafood market",
    "seafood wholesaler",
    "smoke shop",
    "store",
    "supermarket",
    "visitor center",
    "wedding venue",
    "wholesaler",
    "wholesale grocer",
}
REVIEW_TYPES = {
    "bakery",
    "bubble tea store",
    "cake shop",
    "cookie shop",
    "deli",
    "dessert shop",
    "donut shop",
    "ice cream shop",
    "mobile caterer",
    "tea house",
}
DINING_TYPES = {
    "bar",
    "bar & grill",
    "brewery",
    "brewpub",
    "cafe",
    "cocktail bar",
    "diner",
    "lounge bar",
    "pub",
    "snack bar",
    "sports bar",
    "wine bar",
}


def normalize(value):
    return (value or "").strip().casefold().replace("_", " ")


def restaurant_types(restaurant):
    values = [
        restaurant.primary_type,
        restaurant.primary_type_label,
        restaurant.type,
        restaurant.category,
    ]
    values.extend(restaurant.place_types or [])
    values.extend((restaurant.subtypes or "").split(","))
    return {normalize(value) for value in values if normalize(value)}


def has_restaurant_type(types):
    return any(value == "restaurant" or value.endswith(" restaurant") for value in types)


def classify_restaurant(restaurant):
    primary = normalize(restaurant.primary_type or restaurant.type)
    types = restaurant_types(restaurant)
    if primary in COFFEE_TYPES:
        return "excluded", f"primary type is {primary}"
    retail_types = types & RETAIL_TYPES
    if retail_types:
        retail = sorted(retail_types)[0]
        if has_restaurant_type(types) or types & {"bakery", "cafe", "deli", "espresso bar"}:
            return "review", f"mixed-use venue with retail type {retail}"
        return "excluded", f"retail type: {retail}"
    if primary in RETAIL_TYPES:
        if has_restaurant_type(types) or types & {"bakery", "cafe", "deli", "espresso bar"}:
            return "review", f"mixed-use venue with primary type {primary}"
        return "excluded", f"primary type is {primary}"
    if primary in REVIEW_TYPES:
        return "review", f"primary type is {primary}"
    if has_restaurant_type(types) or primary in DINING_TYPES:
        return "included", f"dining type: {primary or 'restaurant'}"
    if types & REVIEW_TYPES:
        return "review", "food venue without restaurant primary type"
    return "review", f"unrecognized primary type: {primary or 'blank'}"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Commit catalog classifications.")
    parser.add_argument("--database-url", help="Override DATABASE_URL.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    from app import app
    from models import Restaurant, db, utc_now

    with app.app_context():
        restaurants = Restaurant.query.order_by(Restaurant.id).all()
        results = []
        for restaurant in restaurants:
            status, reason = classify_restaurant(restaurant)
            results.append((restaurant, status, reason))
        counts = Counter(status for _, status, _ in results)
        for status in ["included", "excluded", "review"]:
            print(f"{status.upper()}={counts[status]}")
        for restaurant, status, reason in results:
            if status != "included":
                print(f"{status}\t{restaurant.id}\t{restaurant.name}\t{reason}")
        if not args.execute:
            print("Preview only: no database changes committed.")
            return
        for restaurant, status, reason in results:
            restaurant.catalog_status = status
            restaurant.catalog_reason = reason
            restaurant.catalog_reviewed_at = utc_now()
        db.session.commit()
        print(f"Updated catalog status for {len(results)} restaurants.")


if __name__ == "__main__":
    main()
