import io
import os
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest

# Flask-SQLAlchemy binds its engine while importing the app.
os.environ["DATABASE_URL"] = "sqlite://"

from app import app, hash_token, normalize_database_url
from demo_data import seed_demo_specials
from models import (
    DistributionLog,
    RawSpecialSubmission,
    Restaurant,
    RestaurantLead,
    Special,
    SpecialDraft,
    SpecialMetric,
    Subscriber,
    db,
)
from special_pipeline import create_or_prepare_image, polish_special_text
from storage import R2Storage, UploadError, validate_image


@pytest.fixture()
def client(tmp_path):
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SECRET_KEY="test-secret",
        ADMIN_PASSWORD="test-password",
        UPLOAD_ROOT=str(tmp_path / "uploads"),
        R2_ENDPOINT=None,
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        restaurant = Restaurant(
            name="Test Kitchen",
            slug="test-kitchen",
            city="Mount Vernon",
            phone="360-555-0100",
            site="https://example.com",
            latitude=48.42,
            longitude=-122.33,
        )
        db.session.add(restaurant)
        db.session.commit()
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.session.remove()
        db.drop_all()


def csrf(client):
    client.get("/")
    with client.session_transaction() as flask_session:
        return flask_session["csrf_token"]


def test_database_url_uses_installed_psycopg_driver():
    assert normalize_database_url("postgresql://user:pass@example.com/app") == (
        "postgresql+psycopg://user:pass@example.com/app"
    )
    assert normalize_database_url("postgres://user:pass@example.com/app") == (
        "postgresql+psycopg://user:pass@example.com/app"
    )
    assert normalize_database_url("sqlite:///appertivo.db") == "sqlite:///appertivo.db"


def login(client):
    return client.post(
        "/admin/login",
        data={"password": "test-password", "csrf_token": csrf(client)},
        follow_redirects=True,
    )


def generate_token(client):
    login(client)
    response = client.post("/admin/restaurants/1/token", data={"csrf_token": csrf(client)})
    body = response.get_data(as_text=True)
    return body.split("/submit/")[1].split('"')[0]


def submit(client, token, **overrides):
    data = {
        "csrf_token": csrf(client),
        "title": "Prime Rib Friday",
        "description": "Limited plates.",
        "price": "$24",
        "special_date": "2026-06-05",
    }
    data.update(overrides)
    return client.post(f"/submit/{token}", data=data)


def test_admin_requires_login_and_csrf(client):
    assert client.get("/admin").status_code == 302
    assert client.post("/admin/login", data={"password": "test-password"}).status_code == 400
    assert login(client).status_code == 200
    assert b"Dashboard" in client.get("/admin").data


def test_healthcheck(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_private_token_rotation_and_reviewed_submission(client):
    token = generate_token(client)
    response = submit(client, token)
    assert response.status_code == 200
    with app.app_context():
        draft = SpecialDraft.query.one()
        assert draft.status == "awaiting_approval"
        assert draft.expires_at == datetime(2026, 6, 6, 6, 59)
        assert Special.query.count() == 0
        assert Restaurant.query.one().submission_token_hash == hash_token(token)

    rotated_token = generate_token(client)
    assert rotated_token != token
    assert client.get(f"/submit/{token}").status_code == 404
    assert client.get(f"/submit/{rotated_token}").status_code == 200


def test_trusted_submission_publishes_and_future_special_is_hidden(client):
    token = generate_token(client)
    with app.app_context():
        restaurant = Restaurant.query.one()
        restaurant.direct_publish_enabled = True
        db.session.commit()
    submit(client, token, special_date="2099-06-05", start_time="17:00")
    with app.app_context():
        special = Special.query.one()
        assert special.status == "published"
        assert special.published_at is not None
    assert b"Prime Rib Friday" not in client.get("/").data


def test_local_photo_upload_and_validation(client):
    token = generate_token(client)
    response = submit(
        client,
        token,
        photo=(io.BytesIO(b"fake-image"), "plate.jpg", "image/jpeg"),
    )
    assert response.status_code == 200
    with app.app_context():
        draft = SpecialDraft.query.one()
        assert draft.image_url.startswith("/uploads/specials/")
        assert (app.config["UPLOAD_ROOT"] + "/" + draft.image_path)
    with pytest.raises(UploadError):
        validate_image(SimpleNamespace(filename="plate.gif", mimetype="image/gif"))


def test_detail_metrics_actions_and_distribution_log(client):
    login(client)
    with app.app_context():
        special = Special(
            restaurant_id=1,
            title="Taco Tuesday",
            description="Three tacos.",
            status="published",
            source="manual",
            expires_at=datetime(2099, 1, 1),
        )
        db.session.add(special)
        db.session.commit()
        public_id = special.public_id
        special_id = special.id
    assert client.get(f"/specials/{public_id}?channel=facebook_page").status_code == 200
    assert client.get(f"/specials/{public_id}/action/website?channel=facebook_page").status_code == 302
    response = client.post(
        f"/admin/specials/{special_id}/distribution",
        data={"csrf_token": csrf(client), "channel": "facebook_page", "note": "Launch post"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert SpecialMetric.query.filter_by(event_type="view").count() == 1
        assert SpecialMetric.query.filter_by(event_type="website").count() == 1
        assert DistributionLog.query.filter_by(channel="facebook_page").count() == 1


def test_subscriber_capture(client):
    response = client.post(
        "/",
        data={"csrf_token": csrf(client), "email": "DINER@example.com", "location": "Skagit Valley, WA"},
    )
    assert response.status_code == 302
    with app.app_context():
        assert Subscriber.query.one().email == "diner@example.com"
        assert Subscriber.query.one().location == "Skagit Valley, WA"


def test_location_search_defaults_to_skagit_and_waitlists_other_markets(client):
    default_page = client.get("/")
    assert b"Skagit Valley launch preview" in default_page.data
    assert b'value="Skagit Valley, WA"' in default_page.data

    city_page = client.get("/?location=Mount+Vernon")
    assert b"All Skagit cities" in city_page.data
    assert b'<option selected>Mount Vernon</option>' in city_page.data

    waitlist_page = client.get("/?location=Seattle")
    assert b"We're not in Seattle yet." in waitlist_page.data
    assert b"Join waitlist" in waitlist_page.data


def test_demo_special_seed_is_idempotent(client):
    with app.app_context():
        for name, city in [
            ("Adrift Restaurant", "Anacortes"),
            ("The Old Edison", "Bow"),
            ("Terramar Brewstillery", "Bow"),
            ("Dad's Diner Old School BBQ", "Anacortes"),
            ("Chuckanut Manor Seafood & Grill", "Bow"),
            ("Farm To Market Bakery", "Bow"),
        ]:
            db.session.add(Restaurant(name=name, slug=name.lower().replace(" ", "-"), city=city))
        db.session.commit()
        seeded, skipped = seed_demo_specials(db.session)
        refreshed, refreshed_skipped = seed_demo_specials(db.session)
        assert seeded == refreshed == 6
        assert skipped == refreshed_skipped == []
        assert Special.query.filter_by(source="demo").count() == 6


def test_marketing_routes_and_restaurant_lead_workflow(client):
    for path in ["/how-it-works", "/for-restaurants", "/for-diners", "/get-started"]:
        response = client.get(path)
        assert response.status_code == 200
        assert b"Appertivo" in response.data

    response = client.post(
        "/get-started",
        data={
            "csrf_token": csrf(client),
            "restaurant_name": "Local Table",
            "contact_name": "Alex Cook",
            "email": "alex@example.com",
            "phone": "360-555-0199",
            "city": "Anacortes",
            "note": "Dinner specials",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Let's get your specials" in response.data
    with app.app_context():
        lead = RestaurantLead.query.one()
        assert lead.status == "new"
        assert lead.restaurant_name == "Local Table"

    assert client.get("/admin/leads").status_code == 302
    login(client)
    assert b"Local Table" in client.get("/admin/leads").data
    response = client.post(
        "/admin/leads/1/contacted",
        data={"csrf_token": csrf(client)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assert RestaurantLead.query.one().status == "contacted"


def test_restaurant_lead_requires_practical_intake_fields(client):
    response = client.post(
        "/get-started",
        data={"csrf_token": csrf(client), "restaurant_name": "Incomplete"},
    )
    assert response.status_code == 400
    with app.app_context():
        assert RestaurantLead.query.count() == 0


def test_r2_storage_uses_s3_compatible_client(monkeypatch):
    uploads = []

    class FakeClient:
        def upload_fileobj(self, stream, bucket, key, ExtraArgs):
            uploads.append((stream.read(), bucket, key, ExtraArgs))

    fake_boto3 = SimpleNamespace(client=lambda **kwargs: FakeClient())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    storage = R2Storage("https://r2.example", "photos", "key", "secret", "https://images.example")
    upload = SimpleNamespace(stream=io.BytesIO(b"photo"), mimetype="image/webp")
    key, url = storage.save(upload, "specials/id.webp")
    assert key == "specials/id.webp"
    assert url == "https://images.example/specials/id.webp"
    assert uploads[0][1:] == ("photos", "specials/id.webp", {"ContentType": "image/webp"})


def test_special_pipeline_parser_and_missing_image():
    parsed = polish_special_text("Fish tacos tonight. Two plates for $14.99")
    assert parsed == {
        "title": "Fish tacos tonight",
        "description": "Fish tacos tonight. Two plates for $14.99",
        "price_text": "$14.99",
        "availability_text": "tonight",
        "cta_text": "View Special",
    }
    assert create_or_prepare_image(SimpleNamespace(raw_image_url=None, raw_image_path=None)) == {
        "image_url": None,
        "image_path": None,
        "ai_generated_image": False,
        "image_disclaimer": None,
    }


def test_public_submission_preview_approval_and_publish(client):
    response = client.post(
        "/submit-special",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "raw_text": "Happy hour oysters today $12",
            "sender_email": "owner@example.com",
        },
    )
    assert response.status_code == 200
    assert b"Special received" in response.data
    with app.app_context():
        submission = RawSpecialSubmission.query.one()
        draft = SpecialDraft.query.one()
        token = draft.approval_token
        assert submission.status == "awaiting_approval"
        assert draft.status == "awaiting_approval"
        assert Special.query.count() == 0

    assert client.get(f"/specials/preview/{token}").status_code == 302
    login(client)
    assert b"Happy hour oysters" in client.get(f"/specials/preview/{token}").data
    assert client.post(
        f"/specials/preview/{token}/approve", data={"csrf_token": csrf(client)}
    ).status_code == 302
    with app.app_context():
        assert SpecialDraft.query.one().status == "approved"
    response = client.post("/admin/special-drafts/1/publish", data={"csrf_token": csrf(client)})
    assert response.status_code == 302
    with app.app_context():
        special = Special.query.one()
        assert special.draft_id == SpecialDraft.query.one().id
        assert special.status == "published"
        assert RawSpecialSubmission.query.one().status == "published"
    assert client.post("/admin/special-drafts/1/publish", data={"csrf_token": csrf(client)}).status_code == 302
    with app.app_context():
        assert Special.query.count() == 1


def test_preview_rejection_updates_submission(client):
    client.post(
        "/submit-special",
        data={"csrf_token": csrf(client), "restaurant_id": "1", "raw_text": "Weekend brunch $18"},
    )
    with app.app_context():
        token = SpecialDraft.query.one().approval_token
    login(client)
    assert client.post(
        f"/specials/preview/{token}/reject", data={"csrf_token": csrf(client)}
    ).status_code == 302
    with app.app_context():
        assert SpecialDraft.query.one().status == "rejected"
        assert RawSpecialSubmission.query.one().status == "rejected"


def test_simulated_webhooks_and_unassigned_assignment(client):
    email = client.post(
        "/webhooks/email-special",
        json={"raw_text": "Soup tonight $9", "sender_email": "cook@example.com"},
    )
    sms = client.post(
        "/webhooks/sms-special",
        json={"restaurant_id": 1, "raw_text": "Lunch today $11", "sender_phone": "360-555-0101"},
    )
    assert email.status_code == sms.status_code == 201
    assert "/specials/preview/" in email.json["preview_url"]
    with app.app_context():
        draft = db.session.get(SpecialDraft, email.json["draft_id"])
        assert draft.restaurant_id is None
    login(client)
    assert client.post(
        f"/admin/special-drafts/{email.json['draft_id']}/assign",
        data={"csrf_token": csrf(client), "restaurant_id": "1"},
    ).status_code == 302
    with app.app_context():
        draft = db.session.get(SpecialDraft, email.json["draft_id"])
        assert draft.restaurant_id == 1
        assert draft.raw_submission.restaurant_id == 1


def test_simulated_webhooks_are_disabled_outside_testing(client):
    app.config["TESTING"] = False
    app.config["SPECIAL_WEBHOOK_TEST_ENABLED"] = False
    try:
        assert client.post("/webhooks/email-special", json={"raw_text": "Soup $9"}).status_code == 404
    finally:
        app.config["TESTING"] = True


def test_admin_structured_special_creation_publishes_through_pipeline(client):
    login(client)
    response = client.post(
        "/admin/specials/new",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "title": "Chef dinner",
            "description": "Three courses.",
            "price": "$35",
            "special_date": "2099-06-05",
            "status": "published",
            "source": "manual",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert RawSpecialSubmission.query.one().source_channel == "admin"
        assert SpecialDraft.query.one().status == "published"
        assert Special.query.one().title == "Chef dinner"
