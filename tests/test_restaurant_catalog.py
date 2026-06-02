import os
from types import SimpleNamespace

os.environ["DATABASE_URL"] = "sqlite://"

from app import app
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


def test_catalog_status_hides_public_venues_and_admin_can_override():
    app.config.update(TESTING=True, SECRET_KEY="test-secret", ADMIN_PASSWORD="test-password")
    with app.app_context():
        db.drop_all()
        db.create_all()
        db.session.add_all(
            [
                Restaurant(name="Included Cafe", slug="included-cafe", city="Anacortes"),
                Restaurant(
                    name="Hidden Market",
                    slug="hidden-market",
                    city="Anacortes",
                    catalog_status="excluded",
                    catalog_reason="primary type is grocery store",
                ),
            ]
        )
        db.session.commit()

    with app.test_client() as client:
        assert b"Included Cafe" in client.get("/restaurants").data
        assert b"Hidden Market" not in client.get("/restaurants").data
        assert client.get("/restaurants/hidden-market").status_code == 404
        login(client)
        assert b"Hidden Market" in client.get("/admin/restaurant-catalog?status=excluded").data
        response = client.post(
            "/admin/restaurants/2/catalog/included",
            data={"csrf_token": csrf(client)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Hidden Market marked included" in response.data
        assert b"Hidden Market" in client.get("/restaurants").data
        response = client.post(
            "/admin/restaurants/catalog/excluded",
            data={"csrf_token": csrf(client), "restaurant_ids": ["2"]},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"1 venues marked excluded" in response.data
        assert b"Hidden Market" not in client.get("/restaurants").data

    with app.app_context():
        db.session.remove()
        db.drop_all()
