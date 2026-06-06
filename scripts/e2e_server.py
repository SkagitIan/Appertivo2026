import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "playwright"
DB_PATH = ROOT / "instance" / "e2e.sqlite"
CAPTURE_PATH = OUTPUT_DIR / "email-capture.jsonl"
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5012")
sys.path.insert(0, str(ROOT))

os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{DB_PATH.as_posix()}",
        "SECRET_KEY": "e2e-secret",
        "ADMIN_PASSWORD": "e2e-password",
        "APP_BASE_URL": BASE_URL,
        "EMAIL_CAPTURE_PATH": str(CAPTURE_PATH),
        "EMAIL_TEST_RECIPIENT": "e2e-digest@example.com",
        "EMAIL_FROM_NOREPLY": "noreply@appertivo.test",
        "EMAIL_FROM_SPECIALS": "specials@appertivo.test",
        "EMAIL_FROM_SALES": "ian@appertivo.test",
        "EMAIL_REPLY_TO_SPECIALS": "specials@appertivo.test",
        "EMAIL_REPLY_TO_SALES": "ian@appertivo.test",
        "SPECIAL_WEBHOOK_TEST_ENABLED": "1",
        "RESEND_API_KEY": "",
        "LOOPS_API_KEY": "",
        "OPENAI_API_KEY": "",
        "CLOUDINARY_CLOUD_NAME": "",
        "CLOUDINARY_API_KEY": "",
        "CLOUDINARY_API_SECRET": "",
        "R2_ENDPOINT": "",
    }
)

from app import app
from models import Restaurant, Special, Subscriber, db


def capture_records():
    if not CAPTURE_PATH.exists():
        return []
    return [json.loads(line) for line in CAPTURE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def clear_capture():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_PATH.write_text("", encoding="utf-8")


def seed_e2e_data():
    ROOT.joinpath("instance").mkdir(exist_ok=True)
    clear_capture()
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.create_all()
        test_kitchen = Restaurant(
            name="E2E Test Kitchen",
            slug="e2e-test-kitchen",
            city="Mount Vernon",
            full_address="101 First St, Mount Vernon, WA",
            phone="360-555-0100",
            site="https://example.com/e2e-test-kitchen",
            contact_email="owner@example.com",
            latitude=48.421,
            longitude=-122.334,
            category="Seafood",
        )
        trusted_taco = Restaurant(
            name="Trusted Taco",
            slug="trusted-taco",
            city="Burlington",
            full_address="202 Taco Ave, Burlington, WA",
            phone="360-555-0200",
            site="https://example.com/trusted-taco",
            contact_email="trusted@example.com",
            latitude=48.475,
            longitude=-122.325,
            category="Tacos",
            direct_publish_enabled=True,
        )
        outreach_bistro = Restaurant(
            name="Outreach Bistro",
            slug="outreach-bistro",
            city="Anacortes",
            full_address="303 Commercial Ave, Anacortes, WA",
            phone="360-555-0300",
            site="https://example.com/outreach-bistro",
            contact_email="outreach@example.com",
            latitude=48.512,
            longitude=-122.612,
            category="Bistro",
        )
        db.session.add_all([test_kitchen, trusted_taco, outreach_bistro])
        db.session.flush()
        db.session.add(
            Special(
                restaurant_id=test_kitchen.id,
                title="E2E Halibut Sandwich",
                description="Fresh catch with fries and slaw.",
                price="$18",
                status="published",
                source="manual",
                published_at=datetime(2026, 6, 5, 12, 0),
                expires_at=datetime(2099, 1, 1, 23, 59),
            )
        )
        db.session.add_all(
            [
                Subscriber(email="skagit@example.com", city="Mount Vernon", location="Skagit Valley, WA"),
                Subscriber(email="seattle@example.com", city="Seattle", location="Seattle, WA"),
                Subscriber(
                    email="unsubscribed@example.com",
                    city="Mount Vernon",
                    location="Skagit Valley, WA",
                    is_subscribed=False,
                ),
            ]
        )
        db.session.commit()


@app.get("/__e2e/reset")
def e2e_reset():
    seed_e2e_data()
    return {"status": "ok"}


@app.get("/__e2e/capture")
def e2e_capture():
    return {"records": capture_records()}


if __name__ == "__main__":
    app.config.update(
        TESTING=False,
        EMAIL_CAPTURE_PATH=str(CAPTURE_PATH),
        APP_BASE_URL=BASE_URL,
        EMAIL_TEST_RECIPIENT="e2e-digest@example.com",
    )
    seed_e2e_data()
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5012")), debug=False, threaded=True, use_reloader=False)
