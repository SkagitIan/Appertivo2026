import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"

from app import app, hash_token
from models import Restaurant, db
from scripts.classify_restaurant_catalog import classify_restaurant


def restaurant(**overrides):
    values = {
        "primary_type": "",
        "primary_type_label": "",
        "type": "",
        "category": "",
        "place_types": [],
        "subtypes": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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


def test_classifier_uses_full_row_types_conservatively():
    assert classify_restaurant(restaurant(primary_type="mexican_restaurant"))[0] == "included"
    assert classify_restaurant(restaurant(primary_type="coffee_stand"))[0] == "excluded"
    assert classify_restaurant(restaurant(primary_type="grocery_store"))[0] == "excluded"
    assert (
        classify_restaurant(
            restaurant(primary_type="grocery_store", place_types=["grocery_store", "deli"])
        )[0]
        == "review"
    )
    assert classify_restaurant(restaurant(primary_type="bakery"))[0] == "review"


def test_catalog_status_hides_nonincluded_venues_from_normal_admin_workflows():
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        ADMIN_PASSWORD="test-password",
        GOOGLE_PLACES_API_KEY="places-key",
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all(
            [
                Restaurant(
                    name="Included Cafe",
                    slug="included-cafe",
                    city="Anacortes",
                    place_id="included-place",
                ),
                Restaurant(
                    name="Hidden Market",
                    slug="hidden-market",
                    city="Anacortes",
                    place_id="hidden-place",
                    catalog_status="excluded",
                    catalog_reason="primary type is grocery store",
                    submission_token_hash=hash_token("hidden-token"),
                ),
                Restaurant(
                    name="Pending Bakery",
                    slug="pending-bakery",
                    city="Anacortes",
                    place_id="pending-place",
                    catalog_status="review",
                    catalog_reason="primary type is bakery",
                ),
            ]
        )
        db.session.commit()

    with app.test_client() as client:
        public_directory = client.get("/restaurants")
        assert public_directory.status_code == 200
        assert b"Included Cafe" in public_directory.data
        assert b"Hidden Market" not in public_directory.data
        assert b"Pending Bakery" not in public_directory.data
        assert client.get("/restaurants/hidden-market").status_code == 404
        assert b"Included Cafe" in client.get("/restaurants/included-cafe").data
        login(client)
        restaurants_page = client.get("/admin/restaurants")
        assert b"Included Cafe" in restaurants_page.data
        assert b"Hidden Market" not in restaurants_page.data
        assert b"Pending Bakery" not in restaurants_page.data
        enrichment_page = client.get("/admin/restaurant-enrichment")
        assert b"Included Cafe" in enrichment_page.data
        assert b"Hidden Market" not in enrichment_page.data
        assert b"Pending Bakery" not in enrichment_page.data
        assert client.get("/admin/restaurant-catalog").status_code == 404
        assert client.get("/admin/restaurants/2/edit").status_code == 404
        assert client.get("/submit/hidden-token").status_code == 404

    with app.app_context():
        db.session.remove()
        db.drop_all()
