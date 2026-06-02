import json
import os
from types import SimpleNamespace

import pytest


os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from email_system import loops_client, resend_client
from email_system.openai_client import generate_outreach_draft
from email_system.outreach_service import receive_resend_email, send_outreach_message
from models import OutreachMessage, Restaurant, db


@pytest.fixture()
def outreach_app():
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite://",
        SECRET_KEY="test-secret",
        ADMIN_PASSWORD="test-password",
        EMAIL_FROM_SALES="ian@appertivo.com",
        EMAIL_REPLY_TO_SALES="ian@appertivo.com",
        RESEND_API_KEY="resend-key",
        RESEND_WEBHOOK_SECRET="whsec_test",
        OPENAI_API_KEY="openai-key",
        OPENAI_OUTREACH_MODEL="gpt-5.4-mini",
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        restaurant = Restaurant(
            name="Test Kitchen",
            slug="test-kitchen",
            city="Mount Vernon",
            contact_email="owner@example.com",
        )
        db.session.add(restaurant)
        db.session.commit()
        yield app
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


def test_openai_draft_uses_restaurant_context(outreach_app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "email_system.openai_client.requests.post",
        lambda url, **kwargs: calls.append((url, kwargs))
        or SimpleNamespace(
            ok=True,
            json=lambda: {"output": [{"type": "message", "content": [{"type": "output_text", "text": "Draft body"}]}]},
        ),
    )
    with app.app_context():
        result = generate_outreach_draft(Restaurant.query.one(), "Keep it short")
    assert result["text"] == "Draft body"
    assert "Test Kitchen" in calls[0][1]["json"]["input"]
    assert calls[0][1]["json"]["model"] == "gpt-5.4-mini"


def test_reviewed_send_updates_message_and_calls_loops(outreach_app, monkeypatch):
    loops_calls = []
    monkeypatch.setattr(
        resend_client,
        "send_email",
        lambda **kwargs: {"success": True, "provider": "resend", "message_id": "email-1", "error": None},
    )
    monkeypatch.setattr(loops_client, "create_or_update_contact", lambda *args, **kwargs: loops_calls.append(("contact", args)))
    monkeypatch.setattr(loops_client, "send_event", lambda *args, **kwargs: loops_calls.append(("event", args)))
    with app.app_context():
        message = OutreachMessage(
            restaurant_id=1,
            sender_email="ian@appertivo.com",
            recipient_email="owner@example.com",
            subject="Hello",
            body_text="A reviewed body.",
        )
        db.session.add(message)
        db.session.commit()
        result = send_outreach_message(message)
        assert message.status == "sent"
        assert message.provider_message_id == "email-1"
    assert result["success"] is True
    assert [call[0] for call in loops_calls] == ["contact", "event"]


def test_inbound_resend_reply_is_stored(outreach_app, monkeypatch):
    monkeypatch.setattr("email_system.outreach_service.resend.Webhooks.verify", lambda options: None)
    monkeypatch.setattr(
        "email_system.outreach_service.resend.Emails.Receiving.get",
        lambda email_id: {"text": "Thanks, tell me more."},
    )
    payload = json.dumps(
        {
            "type": "email.received",
            "data": {
                "email_id": "received-1",
                "from": "owner@example.com",
                "to": ["ian@appertivo.com"],
                "subject": "Re: Appertivo",
                "created_at": "2026-06-01T12:00:00.000Z",
                "message_id": "<reply@example.com>",
            },
        }
    )
    with app.app_context():
        receive_resend_email(payload, {"id": "1", "timestamp": "1", "signature": "v1,test"})
        message = OutreachMessage.query.one()
        assert message.direction == "inbound"
        assert message.restaurant_id == 1
        assert message.body_text == "Thanks, tell me more."


def test_admin_outreach_create_generate_and_email_tool_guard(outreach_app, monkeypatch):
    with app.test_client() as client:
        login(client)
        response = client.post(
            "/admin/outreach",
            data={
                "csrf_token": csrf(client),
                "restaurant_id": "1",
                "recipient_email": "owner@example.com",
                "subject": "Hello",
                "body_text": "Initial",
            },
        )
        assert response.status_code == 302
        monkeypatch.setattr(
            "email_system.openai_client.generate_outreach_draft",
            lambda restaurant, instruction: {"success": True, "text": "Generated", "error": None},
        )
        response = client.post("/admin/outreach/1/generate", data={"csrf_token": csrf(client)})
        assert response.status_code == 302
        app.config["EMAIL_TEST_ENABLED"] = False
        response = client.post("/admin/email-tools", data={"csrf_token": csrf(client)}, follow_redirects=True)
        assert b"Email test sending is disabled" in response.data
    with app.app_context():
        assert OutreachMessage.query.one().body_text == "Generated"
