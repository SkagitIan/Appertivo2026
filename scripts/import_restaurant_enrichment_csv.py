"""Update existing restaurants from the enhanced master CSV.

Preview mode is the default. The importer matches by place_id and never adds
or deletes restaurants.
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1]))


BOOLEAN_FIELDS = [
    "delivery",
    "dine_in",
    "takeout",
    "reservable",
    "serves_breakfast",
    "serves_brunch",
    "serves_lunch",
    "serves_dinner",
    "serves_beer",
    "serves_wine",
    "serves_cocktails",
    "serves_coffee",
    "serves_dessert",
    "serves_vegetarian",
    "outdoor_seating",
    "live_music",
    "good_for_children",
    "good_for_groups",
    "allows_dogs",
    "restroom",
    "good_for_watching_sports",
]


def optional_json(value):
    return json.loads(value) if value else None


def optional_int(value):
    return int(float(value)) if value else None


def optional_float(value):
    return float(value) if value else None


def optional_bool(value):
    if not value:
        return None
    return value.strip().casefold() == "true"


def address_parts(address):
    parts = [part.strip() for part in address.split(",")]
    if len(parts) < 4:
        return {}
    state_zip = parts[-2].split()
    return {
        "street": ", ".join(parts[:-3]),
        "city": parts[-3],
        "us_state": state_zip[0] if state_zip else "",
        "postal_code": state_zip[1] if len(state_zip) > 1 else "",
        "country": parts[-1],
    }


def set_if_present(restaurant, field, value):
    if value != "":
        setattr(restaurant, field, value)


def apply_csv_row(restaurant, row, utc_now, include_heavy_content=False):
    set_if_present(restaurant, "name", row["name"])
    set_if_present(restaurant, "full_address", row["address"])
    for key, value in address_parts(row["address"]).items():
        if value:
            setattr(restaurant, key, value)
    restaurant.latitude = optional_float(row["lat"])
    restaurant.longitude = optional_float(row["lng"])
    set_if_present(restaurant, "phone", row["phone"])
    set_if_present(restaurant, "international_phone", row["phone_intl"])
    set_if_present(restaurant, "site", row["website"])
    set_if_present(restaurant, "google_maps_uri", row["google_maps_url"])
    restaurant.rating = optional_float(row["rating"])
    restaurant.reviews = optional_int(row["review_count"])
    restaurant.business_status = row["business_status"]
    restaurant.primary_type = row["primary_type"]
    restaurant.primary_type_label = row["primary_type_label"]
    restaurant.place_types = [item for item in row["types"].split(",") if item]
    restaurant.plus_code = {"globalCode": row["plus_code"]} if row["plus_code"] else None
    restaurant.timezone = row["timezone"]
    restaurant.utc_offset_minutes = optional_int(row["utc_offset_min"])
    restaurant.price_level = row["price_level"]
    restaurant.hours_text = row["hours_text"]
    restaurant.editorial_summary = row["editorial_summary"]
    restaurant.top_review = row["top_review"]
    restaurant.google_photo_count = optional_int(row["photo_count"])
    if include_heavy_content:
        restaurant.google_review_texts = optional_json(row["all_reviews_json"])
        restaurant.google_first_photo_ref = row["first_photo_ref"]
    restaurant.payment_options = optional_json(row["payment_options_json"])
    restaurant.parking_options = optional_json(row["parking_options_json"])
    restaurant.accessibility_options = optional_json(row["accessibility_json"])
    restaurant.opening_date = optional_json(row["opening_date_json"])
    restaurant.scraped_zip = row["scraped_zip"]
    for field in BOOLEAN_FIELDS:
        setattr(restaurant, field, optional_bool(row[field]))
    restaurant.google_place_refreshed_at = utc_now()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--execute", action="store_true", help="Commit matched CSV updates.")
    parser.add_argument(
        "--confirm-storage-terms",
        action="store_true",
        help="Confirm your Google Maps agreement permits storage of this Places content.",
    )
    parser.add_argument(
        "--include-heavy-content",
        action="store_true",
        help="Also store bulk review text and full photo references.",
    )
    parser.add_argument("--database-url", help="Override DATABASE_URL.")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.execute and not args.confirm_storage_terms:
        raise SystemExit("--execute requires --confirm-storage-terms.")
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url
    from app import app
    from models import Restaurant, db, utc_now

    with args.csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.DictReader(csv_file))

    with app.app_context():
        restaurants = {
            restaurant.place_id: restaurant
            for restaurant in Restaurant.query.filter(
                Restaurant.place_id.isnot(None), Restaurant.place_id != ""
            )
        }
        matched = [row for row in rows if row["place_id"] in restaurants]
        unmatched = [row for row in rows if row["place_id"] not in restaurants]
        print(f"CSV rows: {len(rows)}")
        print(f"Matched existing restaurants: {len(matched)}")
        print(f"Unmatched rows left for manual review: {len(unmatched)}")
        if not args.execute:
            print("Preview only: no database changes committed.")
            return
        updated = 0
        for row in matched:
            for attempt in range(3):
                try:
                    restaurant = Restaurant.query.filter_by(place_id=row["place_id"]).one()
                    apply_csv_row(
                        restaurant,
                        row,
                        utc_now,
                        include_heavy_content=args.include_heavy_content,
                    )
                    db.session.commit()
                    updated += 1
                    break
                except Exception:
                    db.session.rollback()
                    db.engine.dispose()
                    if attempt == 2:
                        raise
                    time.sleep(attempt + 1)
        print(f"Updated existing restaurants: {updated}")


if __name__ == "__main__":
    main()
