"""Fetch Google Places details for restaurants with an explicit execution gate.

Google Places content storage is restricted by Google Maps Platform terms.
Preview mode is the default and performs no network requests. Persistence
requires both --execute and --confirm-storage-terms.
"""
import argparse
import os
import sys
from pathlib import Path

import requests


sys.path.insert(0, str(Path(__file__).parents[1]))

DETAILS_URL = "https://places.googleapis.com/v1/places/{}"

CORE_FIELDS = [
    # IDs Only
    "attributions",
    "id",
    "photos",
    # Essentials
    "addressComponents",
    "adrFormatAddress",
    "formattedAddress",
    "location",
    "plusCode",
    "postalAddress",
    "shortFormattedAddress",
    "types",
    "viewport",
    # Pro
    "accessibilityOptions",
    "businessStatus",
    "containingPlaces",
    "displayName",
    "googleMapsLinks",
    "googleMapsUri",
    "iconBackgroundColor",
    "iconMaskBaseUri",
    "primaryType",
    "primaryTypeDisplayName",
    "pureServiceAreaBusiness",
    "subDestinations",
    "utcOffsetMinutes",
    # Enterprise
    "currentOpeningHours",
    "currentSecondaryOpeningHours",
    "internationalPhoneNumber",
    "nationalPhoneNumber",
    "priceLevel",
    "priceRange",
    "rating",
    "regularOpeningHours",
    "regularSecondaryOpeningHours",
    "userRatingCount",
    "websiteUri",
]

FIELD_MAP = {
    "primary_type": "primaryType",
    "place_types": "types",
    "google_photos": "photos",
    "adr_format_address": "adrFormatAddress",
    "short_formatted_address": "shortFormattedAddress",
    "postal_address": "postalAddress",
    "plus_code": "plusCode",
    "viewport": "viewport",
    "utc_offset_minutes": "utcOffsetMinutes",
    "international_phone": "internationalPhoneNumber",
    "google_maps_uri": "googleMapsUri",
    "google_maps_links": "googleMapsLinks",
    "containing_places": "containingPlaces",
    "sub_destinations": "subDestinations",
    "icon_background_color": "iconBackgroundColor",
    "icon_mask_base_uri": "iconMaskBaseUri",
    "pure_service_area_business": "pureServiceAreaBusiness",
    "price_level": "priceLevel",
    "price_range": "priceRange",
    "current_opening_hours": "currentOpeningHours",
    "current_secondary_opening_hours": "currentSecondaryOpeningHours",
    "regular_opening_hours": "regularOpeningHours",
    "regular_secondary_opening_hours": "regularSecondaryOpeningHours",
    "payment_options": "paymentOptions",
    "parking_options": "parkingOptions",
    "accessibility_options": "accessibilityOptions",
    "delivery": "delivery",
    "dine_in": "dineIn",
    "takeout": "takeout",
    "reservable": "reservable",
    "serves_breakfast": "servesBreakfast",
    "serves_brunch": "servesBrunch",
    "serves_lunch": "servesLunch",
    "serves_dinner": "servesDinner",
    "serves_beer": "servesBeer",
    "serves_wine": "servesWine",
    "serves_cocktails": "servesCocktails",
    "serves_coffee": "servesCoffee",
    "serves_dessert": "servesDessert",
    "serves_vegetarian": "servesVegetarianFood",
    "outdoor_seating": "outdoorSeating",
    "live_music": "liveMusic",
    "good_for_children": "goodForChildren",
    "good_for_groups": "goodForGroups",
    "allows_dogs": "allowsDogs",
    "restroom": "restroom",
    "good_for_watching_sports": "goodForWatchingSports",
    "google_attributions": "attributions",
}

app = None
Restaurant = None
RestaurantGoogleReview = None
db = None
utc_now = None


def load_application(database_url=None):
    global app, Restaurant, RestaurantGoogleReview, db, utc_now
    if database_url:
        os.environ["DATABASE_URL"] = database_url
    from app import app as flask_app
    from models import Restaurant as RestaurantModel
    from models import RestaurantGoogleReview as RestaurantGoogleReviewModel
    from models import db as database
    from models import utc_now as current_utc_time

    app = flask_app
    Restaurant = RestaurantModel
    RestaurantGoogleReview = RestaurantGoogleReviewModel
    db = database
    utc_now = current_utc_time


def localized_text(value):
    return (value or {}).get("text", "")


def address_parts(components):
    parts = {}
    for component in components or []:
        for component_type in component.get("types", []):
            parts[component_type] = component
    street = " ".join(
        filter(
            None,
            [
                (parts.get("street_number") or {}).get("longText"),
                (parts.get("route") or {}).get("longText"),
            ],
        )
    )
    return {
        "street": street,
        "city": localized_component(parts, "locality")
        or localized_component(parts, "postal_town")
        or localized_component(parts, "administrative_area_level_2"),
        "postal_code": localized_component(parts, "postal_code"),
        "us_state": short_component(parts, "administrative_area_level_1"),
        "country": short_component(parts, "country"),
    }


def localized_component(parts, key):
    return (parts.get(key) or {}).get("longText", "")


def short_component(parts, key):
    return (parts.get(key) or {}).get("shortText", "")


def apply_place_details(restaurant, details):
    restaurant.name = localized_text(details.get("displayName")) or restaurant.name
    restaurant.full_address = details.get("formattedAddress", restaurant.full_address)
    for key, value in address_parts(details.get("addressComponents")).items():
        if value:
            setattr(restaurant, key, value)
    location = details.get("location") or {}
    restaurant.latitude = location.get("latitude", restaurant.latitude)
    restaurant.longitude = location.get("longitude", restaurant.longitude)
    restaurant.phone = details.get("nationalPhoneNumber", restaurant.phone)
    restaurant.site = details.get("websiteUri", restaurant.site)
    restaurant.rating = details.get("rating", restaurant.rating)
    restaurant.reviews = details.get("userRatingCount", restaurant.reviews)
    restaurant.business_status = details.get("businessStatus", restaurant.business_status)
    if "primaryTypeDisplayName" in details:
        restaurant.primary_type_label = localized_text(details["primaryTypeDisplayName"])
    if "editorialSummary" in details:
        restaurant.editorial_summary = localized_text(details["editorialSummary"])
    for model_field, response_field in FIELD_MAP.items():
        if response_field in details:
            setattr(restaurant, model_field, details[response_field])
    restaurant.google_place_refreshed_at = utc_now()
    if "reviews" in details:
        replace_reviews(restaurant, details["reviews"])


def replace_reviews(restaurant, reviews):
    existing = {review.google_review_name: review for review in restaurant.google_reviews}
    received_names = {review["name"] for review in reviews if review.get("name")}
    for review in list(restaurant.google_reviews):
        if review.google_review_name not in received_names:
            restaurant.google_reviews.remove(review)
    for review in reviews:
        if not review.get("name"):
            continue
        item = existing.get(review["name"]) or RestaurantGoogleReview(
            google_review_name=review["name"]
        )
        item.rating = review.get("rating")
        item.text = review.get("text")
        item.original_text = review.get("originalText")
        item.relative_publish_time = review.get("relativePublishTimeDescription", "")
        item.publish_time = review.get("publishTime", "")
        item.author_attribution = review.get("authorAttribution")
        item.flag_content_uri = review.get("flagContentUri", "")
        item.google_maps_uri = review.get("googleMapsUri", "")
        item.visit_date = review.get("visitDate")
        item.fetched_at = utc_now()
        if item not in restaurant.google_reviews:
            restaurant.google_reviews.append(item)


def field_mask():
    return ",".join(CORE_FIELDS)


def fetch_place_details(session, api_key, place_id):
    response = session.get(
        DETAILS_URL.format(place_id),
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask(),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def enrich_restaurant(restaurant, api_key, session=None):
    session = session or requests.Session()
    details = fetch_place_details(session, api_key, restaurant.place_id)
    apply_place_details(restaurant, details)
    return details


def selected_restaurants(limit, place_id):
    query = Restaurant.query.filter(Restaurant.place_id.isnot(None), Restaurant.place_id != "")
    if place_id:
        query = query.filter_by(place_id=place_id)
    query = query.order_by(Restaurant.id)
    return query.limit(limit).all() if limit else query.all()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Send billable Places API requests.")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Write fetched Places content to the database. Requires --confirm-storage-terms.",
    )
    parser.add_argument(
        "--confirm-storage-terms",
        action="store_true",
        help="Confirm your Google Maps agreement permits storage of the requested Places content.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--place-id")
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL, for example sqlite:///instance/appertivo.db.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.persist and not args.execute:
        raise SystemExit("--persist requires --execute.")
    if args.persist and not args.confirm_storage_terms:
        raise SystemExit("--persist requires --confirm-storage-terms.")
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if args.execute and not api_key:
        raise SystemExit("Set GOOGLE_PLACES_API_KEY before using --execute.")

    load_application(args.database_url)
    with app.app_context():
        restaurants = selected_restaurants(args.limit, args.place_id)
        print(f"Restaurants selected: {len(restaurants)}")
        print(f"Field mask: {field_mask()}")
        if not args.execute:
            print("Preview only: no API requests sent.")
            return

        session = requests.Session()
        for index, restaurant in enumerate(restaurants, start=1):
            print(f"[{index}/{len(restaurants)}] {restaurant.name} ({restaurant.place_id})")
            details = fetch_place_details(session, api_key, restaurant.place_id)
            if args.persist:
                apply_place_details(restaurant, details)
                db.session.commit()
        print("Completed.")


if __name__ == "__main__":
    main()
