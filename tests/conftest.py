import json
import os

import pytest


os.environ.setdefault("DATABASE_URL", "sqlite://")

from app import app
from models import Restaurant, db


def csrf(client):
    client.get("/")
    with client.session_transaction() as flask_session:
        return flask_session["csrf_token"]


def login(client, password="test-password"):
    return client.post(
        "/admin/login",
        data={"password": password, "csrf_token": csrf(client)},
        follow_redirects=True,
    )


def seed_restaurant(**overrides):
    defaults = {
        "name": "Test Kitchen",
        "slug": "test-kitchen",
        "city": "Mount Vernon",
        "phone": "360-555-0100",
        "site": "https://example.com",
        "latitude": 48.42,
        "longitude": -122.33,
    }
    defaults.update(overrides)
    restaurant = Restaurant(**defaults)
    db.session.add(restaurant)
    db.session.commit()
    return restaurant


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture()
def captured_email_path(tmp_path):
    previous = app.config.get("EMAIL_CAPTURE_PATH")
    path = tmp_path / "email-capture.jsonl"
    app.config["EMAIL_CAPTURE_PATH"] = str(path)
    try:
        yield path
    finally:
        app.config["EMAIL_CAPTURE_PATH"] = previous


@pytest.fixture()
def isolated_app():
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SECRET_KEY="test-secret",
        ADMIN_PASSWORD="test-password",
        EMAIL_CAPTURE_PATH=None,
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

