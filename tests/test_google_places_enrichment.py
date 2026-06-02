import os
from datetime import datetime


os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from models import Restaurant, RestaurantGoogleReview, db
from scripts.enrich_restaurants_google import apply_place_details, field_mask, load_application


load_application()


def test_core_field_mask_stops_at_website_tier_until_atmosphere_is_requested():
    core_fields = field_mask().split(",")
    assert "websiteUri" in core_fields
    assert "displayName" in core_fields
    assert "formattedAddress" in core_fields
    assert "reviews" not in core_fields
    assert "delivery" not in core_fields


def test_apply_place_details_updates_profile_and_replaces_reviews_idempotently():
    details = {
        "displayName": {"text": "Updated Kitchen"},
        "formattedAddress": "123 Main St, Mount Vernon, WA 98273, USA",
        "addressComponents": [
            {"longText": "123", "shortText": "123", "types": ["street_number"]},
            {"longText": "Main Street", "shortText": "Main St", "types": ["route"]},
            {"longText": "Mount Vernon", "shortText": "Mount Vernon", "types": ["locality"]},
            {
                "longText": "Washington",
                "shortText": "WA",
                "types": ["administrative_area_level_1"],
            },
            {"longText": "United States", "shortText": "US", "types": ["country"]},
            {"longText": "98273", "shortText": "98273", "types": ["postal_code"]},
        ],
        "location": {"latitude": 48.4, "longitude": -122.3},
        "primaryType": "restaurant",
        "primaryTypeDisplayName": {"text": "Restaurant"},
        "nationalPhoneNumber": "(360) 555-0199",
        "internationalPhoneNumber": "+1 360-555-0199",
        "websiteUri": "https://example.com",
        "googleMapsUri": "https://maps.google.com/example",
        "rating": 4.7,
        "userRatingCount": 42,
        "delivery": True,
        "editorialSummary": {"text": "A local restaurant."},
        "reviews": [
            {
                "name": "places/example/reviews/one",
                "rating": 5,
                "text": {"text": "Excellent."},
                "authorAttribution": {"displayName": "Guest"},
            }
        ],
    }

    with app.app_context():
        db.drop_all()
        db.create_all()
        restaurant = Restaurant(
            name="Old Kitchen",
            slug="old-kitchen",
            city="Old City",
            place_id="example",
        )
        db.session.add(restaurant)
        db.session.commit()

        apply_place_details(restaurant, details)
        db.session.commit()
        apply_place_details(restaurant, details)
        db.session.commit()

        restaurant = Restaurant.query.one()
        assert restaurant.name == "Updated Kitchen"
        assert restaurant.street == "123 Main Street"
        assert restaurant.city == "Mount Vernon"
        assert restaurant.us_state == "WA"
        assert restaurant.country == "US"
        assert restaurant.primary_type == "restaurant"
        assert restaurant.delivery is True
        assert restaurant.google_place_refreshed_at is not None
        assert RestaurantGoogleReview.query.count() == 1
        assert RestaurantGoogleReview.query.one().text == {"text": "Excellent."}

        db.session.remove()
        db.drop_all()


def csrf(client):
    client.get("/")
    with client.session_transaction() as flask_session:
        return flask_session["csrf_token"]


def login(client):
    return client.post(
        "/admin/login",
        data={"password": "test-password", "csrf_token": csrf(client)},
        follow_redirects=True,
    )


def test_admin_enrichment_queue_enhances_one_confirmed_restaurant(monkeypatch):
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        ADMIN_PASSWORD="test-password",
        GOOGLE_PLACES_API_KEY="places-key",
    )
    calls = []

    def fake_enrich(restaurant, api_key):
        calls.append((restaurant.id, api_key))
        restaurant.google_place_refreshed_at = datetime(2026, 6, 2)

    monkeypatch.setattr("scripts.enrich_restaurants_google.enrich_restaurant", fake_enrich)
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add(
            Restaurant(
                name="Needs Details",
                slug="needs-details",
                city="Mount Vernon",
                place_id="place-1",
            )
        )
        db.session.commit()

    with app.test_client() as client:
        login(client)
        assert b"Needs Details" in client.get("/admin/restaurant-enrichment").data
        assert client.post(
            "/admin/restaurants/1/enhance",
            data={"csrf_token": csrf(client)},
        ).status_code == 400
        response = client.post(
            "/admin/restaurants/1/enhance",
            data={
                "csrf_token": csrf(client),
                "confirm_api_cost": "on",
                "confirm_storage_terms": "on",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Enhanced Needs Details" in response.data
        assert b"Needs Details" not in client.get("/admin/restaurant-enrichment").data
    assert calls == [(1, "places-key")]

    with app.app_context():
        db.session.remove()
        db.drop_all()
