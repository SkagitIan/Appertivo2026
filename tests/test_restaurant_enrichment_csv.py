from types import SimpleNamespace

from scripts.import_restaurant_enrichment_csv import apply_csv_row, optional_int


def test_optional_int_accepts_decimal_csv_counts():
    assert optional_int("310.0") == 310


def test_csv_enrichment_preserves_existing_contact_values_when_source_is_blank():
    row = {
        "name": "Updated Kitchen",
        "address": "123 Main St, Mount Vernon, WA 98273, USA",
        "lat": "48.4",
        "lng": "-122.3",
        "phone": "",
        "phone_intl": "",
        "website": "",
        "google_maps_url": "https://maps.example/place",
        "rating": "4.7",
        "review_count": "42.0",
        "business_status": "OPERATIONAL",
        "primary_type": "restaurant",
        "primary_type_label": "Restaurant",
        "types": "restaurant,food",
        "plus_code": "84WV+TEST",
        "timezone": "America/Los_Angeles",
        "utc_offset_min": "-420",
        "price_level": "PRICE_LEVEL_MODERATE",
        "hours_text": "Monday: 9 AM - 5 PM",
        "editorial_summary": "Local restaurant.",
        "top_review": "Excellent.",
        "all_reviews_json": '["Excellent."]',
        "photo_count": "3",
        "first_photo_ref": "places/example/photos/one",
        "payment_options_json": '{"acceptsCreditCards": true}',
        "parking_options_json": "{}",
        "accessibility_json": "{}",
        "opening_date_json": "{}",
        "scraped_zip": "98273",
        **{
            field: "true"
            for field in [
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
        },
    }
    restaurant = SimpleNamespace(phone="keep-phone", international_phone="keep-intl", site="keep-site")

    apply_csv_row(restaurant, row, lambda: "now")

    assert restaurant.phone == "keep-phone"
    assert restaurant.international_phone == "keep-intl"
    assert restaurant.site == "keep-site"
    assert restaurant.city == "Mount Vernon"
    assert restaurant.google_review_texts == ["Excellent."]
    assert restaurant.google_place_refreshed_at == "now"
