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
from special_taxonomy import infer_tags_from_text, serialize_tag_keys, tag_label
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
        OPENAI_API_KEY=None,
        CLOUDINARY_CLOUD_NAME=None,
        CLOUDINARY_API_KEY=None,
        CLOUDINARY_API_SECRET=None,
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
        "raw_text": "Prime Rib Friday. Limited plates for $24.",
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
        assert draft.title == "Prime Rib Friday"
        assert draft.price_text == "$24"
        assert Special.query.count() == 0
        assert Restaurant.query.one().submission_token_hash == hash_token(token)

    rotated_token = generate_token(client)
    assert rotated_token != token
    assert client.get(f"/submit/{token}").status_code == 404
    assert client.get(f"/submit/{rotated_token}").status_code == 200


def test_trusted_submission_publishes_rough_private_link_special(client):
    token = generate_token(client)
    with app.app_context():
        restaurant = Restaurant.query.one()
        restaurant.direct_publish_enabled = True
        db.session.commit()
    submit(client, token, raw_text="Trusted Taco Lunch. Fast-published tacos for $12.")
    with app.app_context():
        special = Special.query.one()
        assert special.status == "published"
        assert special.title == "Trusted Taco Lunch"
        assert special.price == "$12"
        assert special.published_at is not None


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
    with app.app_context():
        db.session.add(
            Special(
                restaurant_id=1,
                title="Preview Pasta",
                description="A sample dinner special.",
                price="$18",
                status="published",
                source="demo",
                expires_at=datetime(2099, 1, 1),
            )
        )
        db.session.commit()

    default_page = client.get("/")
    assert b"Tonight" in default_page.data
    assert b"Best Specials" in default_page.data
    assert b"Today's specials" in default_page.data
    assert b"Sample special" not in default_page.data
    assert b"Updated daily" in default_page.data
    assert b"Miss a Special" in default_page.data
    assert b"Skagit Valley launch preview" not in default_page.data
    assert b'value="Skagit Valley, WA"' in default_page.data

    city_page = client.get("/?location=Mount+Vernon")
    assert b"All Skagit cities" in city_page.data
    assert b'<option selected>Mount Vernon</option>' in city_page.data

    waitlist_page = client.get("/?location=Seattle")
    assert b"Get restaurant specials near Seattle." in waitlist_page.data
    assert b"Get Local Specials" in waitlist_page.data


def test_skagit_feed_includes_sedro_woolley_city_variant(client):
    with app.app_context():
        restaurant = Restaurant(
            name="Bullpen Bar and Grill",
            slug="bullpen-bar-and-grill",
            city="Sedro Woolley",
        )
        db.session.add(restaurant)
        db.session.flush()
        db.session.add(
            Special(
                restaurant_id=restaurant.id,
                title="Game Day Burger",
                description="Burger and fries.",
                status="published",
                source="manual",
                expires_at=datetime(2099, 1, 1),
            )
        )
        db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Game Day Burger" in response.data


def test_specials_feed_filters_featured_and_saved_flow(client):
    with app.app_context():
        db.session.add_all(
            [
                Special(
                    restaurant_id=1,
                    title="Featured Burger",
                    description="Burger and fries.",
                    price="$16",
                    status="published",
                    tag_keys="burgers,american",
                    primary_tag="burgers",
                    featured_rank=1,
                    expires_at=datetime(2099, 1, 1),
                    photo_url="https://images.example/burger.jpg",
                    published_at=datetime(2026, 6, 4),
                ),
                Special(
                    restaurant_id=1,
                    title="Seafood Pasta",
                    description="Clams and linguine.",
                    price="$21",
                    status="published",
                    tag_keys="seafood,pasta,italian",
                    primary_tag="seafood",
                    expires_at=datetime(2099, 1, 1),
                    published_at=datetime(2026, 6, 5),
                ),
            ]
        )
        db.session.commit()
        burger = Special.query.filter_by(title="Featured Burger").one()
        pasta = Special.query.filter_by(title="Seafood Pasta").one()
        burger_public_id = burger.public_id
        pasta_public_id = pasta.public_id

    page = client.get("/specials?tag=burgers")
    assert page.status_code == 200
    assert b'data-testid="featured-special"' in page.data
    assert b"Featured Burger" in page.data
    assert b"Seafood Pasta" not in page.data

    seafood_page = client.get("/specials?tag=seafood")
    assert b"Seafood Pasta" in seafood_page.data
    assert b"Featured Burger" not in seafood_page.data

    save_response = client.post(
        f"/specials/{pasta_public_id}/save",
        data={"csrf_token": csrf(client)},
        follow_redirects=True,
    )
    assert save_response.status_code == 200
    saved_page = client.get("/saved")
    assert b"Seafood Pasta" in saved_page.data
    assert b"Featured Burger" not in saved_page.data
    with app.app_context():
        assert SpecialMetric.query.filter_by(event_type="save", special_id=pasta.id).count() == 1
        assert Special.query.filter_by(public_id=burger_public_id).one().featured_rank == 1


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


def test_marketing_routes_and_first_special_workflow(client, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "email_system.outreach_service.send_draft_publish_email",
        lambda draft, to_email: sent.append((draft.id, to_email))
        or {"success": True, "provider": "test", "message_id": "draft-1", "error": None},
    )
    for path in ["/how-it-works", "/for-restaurants", "/get-started", "/contact"]:
        response = client.get(path)
        assert response.status_code == 200
        assert b"Appertivo" in response.data
    assert client.get("/for-diners").status_code == 302
    assert client.get("/faq").status_code == 302
    faq_page = client.get("/how-it-works")
    assert b"For diners" in faq_page.data
    assert b"For restaurants" in faq_page.data
    assert b"Can I mark a special sold out early" in faq_page.data

    response = client.post(
        "/get-started",
        data={
            "csrf_token": csrf(client),
            "restaurant_name": "Local Table",
            "restaurant_city": "Anacortes",
            "restaurant_address": "101 Commercial Ave, Anacortes, WA",
            "sender_email": "chef@example.com",
            "special_date": "2026-06-05",
            "raw_text": "halibut tacos tonite 18 until sold out",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Special received" in response.data
    with app.app_context():
        restaurant = Restaurant.query.filter_by(name="Local Table").one()
        submission = RawSpecialSubmission.query.one()
        draft = SpecialDraft.query.one()
        assert restaurant.catalog_status == "included"
        assert restaurant.contact_email == "chef@example.com"
        assert submission.source_channel == "get_started"
        assert submission.sender_email == "chef@example.com"
        assert draft.restaurant_id == restaurant.id
        assert sent == [(draft.id, "chef@example.com")]

    assert client.get("/admin/leads").status_code == 302
    login(client)
    assert b"Local Table" not in client.get("/admin/leads").data
    assert b"Leads" in client.get("/admin/tools").data
    assert b"Leads" not in client.get("/admin").data


def test_get_started_requires_email_and_special_details(client):
    response = client.post(
        "/get-started",
        data={"csrf_token": csrf(client), "restaurant_name": "Incomplete"},
    )
    assert response.status_code == 400
    with app.app_context():
        assert RestaurantLead.query.count() == 0
        assert RawSpecialSubmission.query.count() == 0


def test_for_restaurants_page_has_launch_trust_signals(client):
    response = client.get("/for-restaurants")
    assert response.status_code == 200
    assert b"polished local post diners can find and act on tonight" in response.data
    assert b"You approve it before anything goes live" in response.data
    assert b"Early restaurants post free" in response.data
    assert b"Most drafts are ready within a few minutes" in response.data


def test_get_started_restaurant_lookup_includes_google_places(client, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    {
                        "id": "places/local-table",
                        "displayName": {"text": "Local Table"},
                        "formattedAddress": "101 Commercial Ave, Anacortes, WA 98221, USA",
                        "nationalPhoneNumber": "(360) 555-0199",
                        "websiteUri": "https://local.example",
                    }
                ]
            }

    monkeypatch.setitem(app.config, "GOOGLE_PLACES_API_KEY", "places-key")
    monkeypatch.setattr("app.requests.post", lambda *args, **kwargs: Response())
    results = client.get("/api/restaurant-lookup?q=Local").json
    assert results[-1] == {
        "id": None,
        "place_id": "places/local-table",
        "name": "Local Table",
        "city": "Anacortes",
        "address": "101 Commercial Ave, Anacortes, WA 98221, USA",
        "phone": "(360) 555-0199",
        "website": "https://local.example",
        "status": "google_place",
    }


def test_get_started_restaurant_lookup_marks_outside_market_places_coming_soon(client, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    {
                        "id": "places/seattle-table",
                        "displayName": {"text": "Seattle Table"},
                        "formattedAddress": "1 Pike St, Seattle, WA 98101, USA",
                    }
                ]
            }

    monkeypatch.setitem(app.config, "GOOGLE_PLACES_API_KEY", "places-key")
    monkeypatch.setattr("app.requests.post", lambda *args, **kwargs: Response())
    results = client.get("/api/restaurant-lookup?q=Seattle").json
    assert results[-1]["status"] == "coming_soon"

    response = client.post(
        "/get-started",
        data={
            "csrf_token": csrf(client),
            "place_id": "places/seattle-table",
            "restaurant_name": "Seattle Table",
            "restaurant_city": "Seattle",
            "sender_email": "chef@example.com",
            "special_date": "2026-06-05",
            "raw_text": "oysters today 12",
        },
    )
    assert response.status_code == 400
    with app.app_context():
        assert RawSpecialSubmission.query.count() == 0


def test_restaurant_lead_admin_actions_still_work_from_tools(client):
    with app.app_context():
        db.session.add(
            RestaurantLead(
                restaurant_name="Local Table",
                contact_name="Alex Cook",
                city="Anacortes",
                email="alex@example.com",
                phone="360-555-0199",
                status="new",
            )
        )
        db.session.commit()
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
    assert parsed["title"] == "Fish tacos tonight"
    assert parsed["description"] == "Fish tacos tonight. Two plates for $14.99"
    assert parsed["price_text"] == "$14.99"
    assert parsed["availability_text"] == "tonight"
    assert parsed["cta_text"] == "View Special"
    assert parsed["tag_keys"] == "seafood,tacos,mexican"
    assert parsed["primary_tag"] == "seafood"
    assert polish_special_text("Taco Tuesday three tacos for $10")["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=TU"
    assert polish_special_text("Tonight only oysters for $12")["recurrence_rule"] is None
    assert create_or_prepare_image(SimpleNamespace(raw_image_url=None, raw_image_path=None)) == {
        "image_url": None,
        "image_path": None,
        "ai_generated_image": False,
        "image_disclaimer": None,
    }


def test_curated_taxonomy_rejects_unknown_tags():
    assert serialize_tag_keys(["burgers", "made_up", "pizza", "Burgers"]) == "burgers,pizza"
    assert tag_label("date_night") == "Date Night"
    assert infer_tags_from_text("Smash burger and pint happy hour") == ["happy_hour", "burgers", "cocktails", "american"]


def test_special_pipeline_uses_openai_polished_fields(client, monkeypatch):
    monkeypatch.setattr(
        "special_pipeline.polish_special_copy",
        lambda raw_text, restaurant=None: {
            "success": True,
            "fields": {
                "title": "Polished Fish Tacos",
                "description": "Crisp fish tacos with house slaw.",
                "price_text": "$14",
                "value_text": "$18 value",
                "availability_text": "tonight",
                "cta_text": "View Special",
                "tag_keys": ["tacos", "mexican", "unknown"],
                "primary_tag": "tacos",
                "add_on_name": "House Margarita",
                "add_on_price": "$6",
                "add_on_value_text": "$9 value",
                "recurrence_rule": "FREQ=WEEKLY;BYDAY=TU",
                "recurrence_label": "Every Tuesday",
                "recurrence_confidence": "high",
            },
            "error": None,
        },
    )
    with app.app_context():
        submission = RawSpecialSubmission(
            restaurant_id=1,
            source_channel="email",
            raw_text="fish tacos tonite 14",
            sender_email="owner@example.com",
        )
        db.session.add(submission)
        db.session.commit()
        draft = SpecialDraft.query.count()
        assert draft == 0
        from special_pipeline import generate_draft_from_submission

        generated = generate_draft_from_submission(submission.id)
        assert generated.title == "Polished Fish Tacos"
        assert generated.description == "Crisp fish tacos with house slaw."
        assert generated.price_text == "$14"
        assert generated.value_text == "$18 value"
        assert generated.tag_keys == "tacos,mexican"
        assert generated.primary_tag == "tacos"
        assert generated.add_on_name == "House Margarita"
        assert generated.recurrence_label == "Every Tuesday"
        from special_pipeline import approve_draft, publish_draft

        approve_draft(generated.approval_token)
        published = publish_draft(generated.id)
        assert published.tag_keys == "tacos,mexican"
        assert published.value_text == "$18 value"
        assert published.add_on_price == "$6"
        assert published.recurrence_rule == "FREQ=WEEKLY;BYDAY=TU"


def test_special_pipeline_uses_cloudinary_enhanced_image(client, monkeypatch):
    monkeypatch.setattr(
        "special_pipeline.enhance_image_url",
        lambda source_url: {
            "success": True,
            "image_url": "https://res.cloudinary.com/demo/image/upload/c_limit,w_1200/e_improve/q_auto/f_auto/appertivo/specials/photo.jpg",
            "image_path": "appertivo/specials/photo",
            "error": None,
        },
    )
    with app.app_context():
        result = create_or_prepare_image(
            SimpleNamespace(raw_image_url="https://images.example/specials/raw.jpg", raw_image_path="specials/raw.jpg")
        )
    assert result["image_url"].startswith("https://res.cloudinary.com/")
    assert result["image_path"] == "appertivo/specials/photo"


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

    assert b"Happy hour oysters" in client.get(f"/specials/preview/{token}").data
    assert client.post(
        f"/specials/preview/{token}/approve", data={"csrf_token": csrf(client)}
    ).status_code == 302
    with app.app_context():
        assert SpecialDraft.query.one().status == "approved"
    login(client)
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


def test_public_preview_publish_button_publishes_special(client):
    client.post(
        "/submit-special",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "raw_text": "Dinner special today $20",
            "sender_email": "owner@example.com",
        },
    )
    with app.app_context():
        token = SpecialDraft.query.one().approval_token
    preview = client.get(f"/specials/preview/{token}")
    assert preview.status_code == 200
    assert b"special-card" in preview.data
    assert b"Publish" in preview.data
    assert b"Edit" in preview.data
    assert b"Draft queue" not in preview.data
    assert b"Send publish email" not in preview.data
    response = client.post(f"/specials/preview/{token}/publish", data={"csrf_token": csrf(client)})
    assert response.status_code == 302
    with app.app_context():
        special = Special.query.one()
        public_id = special.public_id
        assert special.status == "published"
        assert SpecialDraft.query.one().status == "published"
        assert RawSpecialSubmission.query.one().status == "published"
    live_page = client.get(f"/specials/{public_id}")
    assert b"Operator tools" in live_page.data
    assert b"Sold Out" in live_page.data
    assert b"Add Order Now link" in live_page.data
    restaurant_page = client.get("/restaurants/test-kitchen")
    assert b"Operator tools" in restaurant_page.data
    sold_out = client.post(f"/specials/{public_id}/sold-out", data={"csrf_token": csrf(client)})
    assert sold_out.status_code == 302
    with app.app_context():
        assert Special.query.one().status == "expired"
    assert client.get(f"/specials/{public_id}").status_code == 404


def test_first_public_publish_schedules_one_operator_followup(client, monkeypatch):
    sent = []

    def fake_send_email(**kwargs):
        sent.append(kwargs)
        return {"success": True, "provider": "resend", "message_id": f"email-{len(sent)}", "error": None}

    monkeypatch.setattr("email_system.resend_client.send_email", fake_send_email)

    for raw_text in ["Dinner special today $20", "Lunch special today $12"]:
        client.post(
            "/submit-special",
            data={
                "csrf_token": csrf(client),
                "restaurant_id": "1",
                "raw_text": raw_text,
                "sender_email": "owner@example.com",
            },
        )
        with app.app_context():
            token = SpecialDraft.query.order_by(SpecialDraft.created_at.desc()).first().approval_token
        response = client.post(f"/specials/preview/{token}/publish", data={"csrf_token": csrf(client)})
        assert response.status_code == 302

    followups = [email for email in sent if email["subject"] == "Next time you run a special."]
    assert len(followups) == 1
    assert followups[0]["to"] == "owner@example.com"
    assert followups[0]["scheduled_at"] == "in 5 minutes"
    assert followups[0]["from_email"] == app.config["EMAIL_FROM_SPECIALS"]
    assert "specials@appertivo.com" in followups[0]["text"]


def test_published_preview_link_redirects_to_live_special_and_grants_tools(client):
    client.post(
        "/submit-special",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "raw_text": "Dinner special today $20",
            "sender_email": "owner@example.com",
        },
    )
    with app.app_context():
        token = SpecialDraft.query.one().approval_token
    client.post(f"/specials/preview/{token}/publish", data={"csrf_token": csrf(client)})
    followup = client.get(f"/specials/preview/{token}")
    assert followup.status_code == 302
    with app.app_context():
        public_id = Special.query.one().public_id
    assert f"/specials/{public_id}" in followup.location
    assert b"Operator tools" in client.get(f"/specials/{public_id}").data


def test_restaurant_hours_are_human_readable(client):
    with app.app_context():
        restaurant = Restaurant.query.one()
        restaurant.working_hours = {"Monday": ["12-8PM"], "Tuesday": "['Closed']"}
        db.session.commit()
    response = client.get("/restaurants/test-kitchen")
    assert response.status_code == 200
    assert b"12-8PM" in response.data
    assert b"Closed" in response.data
    assert b"['12-8PM']" not in response.data


def test_preview_rejection_updates_submission(client):
    client.post(
        "/submit-special",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "raw_text": "Weekend brunch $18",
            "sender_email": "owner@example.com",
        },
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


def test_public_submit_requires_email_and_searches_pilot_restaurants(client):
    missing_email = client.post(
        "/submit-special",
        data={"csrf_token": csrf(client), "restaurant_id": "1", "raw_text": "Weekend brunch $18"},
    )
    assert missing_email.status_code == 400
    assert b"Email is required" in missing_email.data

    results = client.get("/api/submit-restaurants?q=Test").json
    assert results[0]["status"] == "included"
    assert results[0]["id"] == 1


def test_submit_restaurant_search_marks_google_places_outside_pilot_coming_soon(client, monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "places": [
                    {
                        "displayName": {"text": "Future Cafe"},
                        "formattedAddress": "123 Example St, Mount Vernon, WA",
                    }
                ]
            }

    monkeypatch.setitem(app.config, "GOOGLE_PLACES_API_KEY", "places-key")
    monkeypatch.setattr("app.requests.post", lambda *args, **kwargs: Response())
    results = client.get("/api/submit-restaurants?q=Future").json
    assert results == [
        {
            "id": None,
            "name": "Future Cafe",
            "city": "",
            "address": "123 Example St, Mount Vernon, WA",
            "status": "coming_soon",
        }
    ]


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
            "schedule_option": "till_sold_out",
            "status": "published",
            "source": "manual",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert RawSpecialSubmission.query.one().source_channel == "admin"
        assert SpecialDraft.query.one().status == "published"
        special = Special.query.one()
        assert special.title == "Chef dinner"
        assert special.availability_text == "Until sold out"
        assert special.expires_at == datetime(2099, 6, 6, 6, 59)


def test_admin_special_creation_enhances_and_redirects_to_preview(client, monkeypatch):
    login(client)
    monkeypatch.setattr(
        "special_pipeline.polish_special_copy",
        lambda raw_text, restaurant=None: {
            "success": True,
            "fields": {
                "title": "Enhanced Chef Dinner",
                "description": "A polished three-course dinner.",
                "price_text": "$35",
                "availability_text": "tonight",
                "cta_text": "View Special",
            },
            "error": None,
        },
    )
    response = client.post(
        "/admin/specials/new",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "title": "chef diner",
            "description": "three courses",
            "price": "35",
            "special_date": "2099-06-05",
            "status": "draft",
            "source": "manual",
            "enhance": "on",
        },
    )
    assert response.status_code == 302
    assert "/specials/preview/" in response.location
    with app.app_context():
        draft = SpecialDraft.query.one()
        assert draft.status == "draft"
        assert draft.title == "Enhanced Chef Dinner"
        assert draft.description == "A polished three-course dinner."
        assert Special.query.count() == 0


def test_admin_submission_enhance_action_updates_existing_draft(client, monkeypatch):
    login(client)
    with app.app_context():
        submission = RawSpecialSubmission(
            restaurant_id=1,
            source_channel="email",
            raw_text="burger nite 12",
            sender_email="owner@example.com",
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id
    monkeypatch.setattr(
        "special_pipeline.polish_special_copy",
        lambda raw_text, restaurant=None: {
            "success": True,
            "fields": {
                "title": "Enhanced Burger Night",
                "description": "A polished burger special.",
                "price_text": "$12",
                "availability_text": "tonight",
                "cta_text": "View Special",
            },
            "error": None,
        },
    )
    response = client.post(f"/admin/special-submissions/{submission_id}/enhance", data={"csrf_token": csrf(client)})
    assert response.status_code == 302
    assert "/specials/preview/" in response.location
    with app.app_context():
        draft = SpecialDraft.query.one()
        assert draft.title == "Enhanced Burger Night"
        assert RawSpecialSubmission.query.one().status == "awaiting_approval"


def test_admin_special_form_saves_taxonomy_add_on_and_featured_rank(client):
    login(client)
    response = client.post(
        "/admin/specials/new",
        data={
            "csrf_token": csrf(client),
            "restaurant_id": "1",
            "title": "Burger Date Night",
            "description": "Two burgers and fries.",
            "price": "$30",
            "value_text": "$40 value",
            "special_date": "2099-06-05",
            "status": "published",
            "source": "manual",
            "tag_keys": ["burgers", "date_night", "made_up"],
            "primary_tag": "date_night",
            "add_on_name": "House Margarita",
            "add_on_price": "$7",
            "add_on_value_text": "$10 value",
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=FR",
            "recurrence_label": "Every Friday",
            "recurrence_confidence": "medium",
            "featured_rank": "2",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        special = Special.query.filter_by(title="Burger Date Night").one()
        assert special.tag_keys == "burgers,date_night"
        assert special.primary_tag == "date_night"
        assert special.value_text == "$40 value"
        assert special.add_on_name == "House Margarita"
        assert special.add_on_price == "$7"
        assert special.add_on_value_text == "$10 value"
        assert special.recurrence_rule == "FREQ=WEEKLY;BYDAY=FR"
        assert special.recurrence_label == "Every Friday"
        assert special.recurrence_confidence == "medium"
        assert special.featured_rank == 2


def test_admin_diner_digest_preview_send_and_unsubscribe(client, monkeypatch):
    login(client)
    sent = []

    def fake_send_email(**kwargs):
        sent.append(kwargs)
        return {"success": True, "provider": "resend", "message_id": f"email-{len(sent)}", "error": None}

    monkeypatch.setattr("email_system.resend_client.send_email", fake_send_email)
    with app.app_context():
        special = Special(
            restaurant_id=1,
            title="Halibut Sandwich",
            description="Fresh catch with fries.",
            price="$18",
            status="published",
            expires_at=datetime(2099, 1, 1),
            published_at=datetime(2026, 6, 4),
        )
        db.session.add_all(
            [
                special,
                Subscriber(email="skagit@example.com", city="Mount Vernon", location="Skagit Valley, WA"),
                Subscriber(email="seattle@example.com", city="Seattle", location="Seattle, WA"),
                Subscriber(
                    email="old@example.com",
                    city="Mount Vernon",
                    location="Skagit Valley, WA",
                    is_subscribed=False,
                ),
            ]
        )
        db.session.commit()

    preview = client.get("/admin/diner-digest")
    assert preview.status_code == 200
    assert b"good today in Skagit Valley" in preview.data
    assert b"recipient" in preview.data.lower()
    assert b"Halibut Sandwich" in preview.data
    assert b"channel=email_digest" in preview.data
    assert b"Unsubscribe" in preview.data

    test_response = client.post(
        "/admin/diner-digest", data={"csrf_token": csrf(client), "action": "test"}, follow_redirects=True
    )
    assert test_response.status_code == 200
    assert sent[-1]["to"] == app.config["EMAIL_TEST_RECIPIENT"]
    assert "Unsubscribe" in sent[-1]["text"]

    production_response = client.post(
        "/admin/diner-digest", data={"csrf_token": csrf(client), "action": "production"}, follow_redirects=True
    )
    assert production_response.status_code == 200
    production_sends = [email for email in sent if email["to"] == "skagit@example.com"]
    assert len(production_sends) == 1
    assert all(email["to"] != "seattle@example.com" for email in sent)
    assert all(email["to"] != "old@example.com" for email in sent)
    assert "channel=email_digest" in production_sends[0]["text"]
    assert production_sends[0]["tags"] == [{"name": "channel", "value": "email_digest"}]
    with app.app_context():
        assert DistributionLog.query.filter_by(channel="email_digest").count() == 1

    unsubscribe_link = production_sends[0]["text"].split("Unsubscribe: ")[1].strip().splitlines()[0]
    unsubscribe_response = client.get(unsubscribe_link.replace(app.config["APP_BASE_URL"], ""))
    assert unsubscribe_response.status_code == 200
    with app.app_context():
        subscriber = Subscriber.query.filter_by(email="skagit@example.com").one()
        assert subscriber.is_subscribed is False
        assert subscriber.unsubscribed_at is not None
