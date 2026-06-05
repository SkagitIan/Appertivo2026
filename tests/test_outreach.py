import json
import os
from types import SimpleNamespace

import pytest


os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from email_system import loops_client, resend_client
from email_system.openai_client import generate_outreach_draft
from email_system.outreach_service import create_campaign_for_restaurant, receive_resend_email, send_outreach_message, suppress_email
from models import OutreachCampaign, OutreachMessage, OutreachSuppression, RawSpecialSubmission, Restaurant, db


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
        campaign = create_campaign_for_restaurant(Restaurant.query.one())
        message = campaign.messages[0]
        message.subject = "Hello"
        message.body_text = "A reviewed body."
        message.reviewed = True
        db.session.commit()
        result = send_outreach_message(message)
        assert message.status == "sent"
        assert message.provider_message_id == "email-1"
        assert campaign.status == "active"
        assert campaign.current_step == 1
        assert campaign.next_follow_up_at is not None
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
        campaign = create_campaign_for_restaurant(Restaurant.query.one())
        receive_resend_email(payload, {"id": "1", "timestamp": "1", "signature": "v1,test"})
        message = OutreachMessage.query.filter_by(direction="inbound").one()
        assert message.direction == "inbound"
        assert message.restaurant_id == 1
        assert message.campaign_id == campaign.id
        assert message.body_text == "Thanks, tell me more."
        assert campaign.status == "replied"
        assert campaign.paused is True


def test_opt_out_blocks_outreach_send(outreach_app, monkeypatch):
    monkeypatch.setattr(
        resend_client,
        "send_email",
        lambda **kwargs: {"success": True, "provider": "resend", "message_id": "email-1", "error": None},
    )
    with app.app_context():
        campaign = create_campaign_for_restaurant(Restaurant.query.one())
        message = campaign.messages[0]
        suppress_email("owner@example.com", source="test")
        db.session.commit()
        result = send_outreach_message(message)
        assert result["success"] is False
        assert message.status == "blocked"
        assert OutreachSuppression.query.filter_by(email="owner@example.com").one()


def test_inbound_special_email_routes_to_special_pipeline(outreach_app, monkeypatch):
    sent = {}
    monkeypatch.setattr("email_system.outreach_service.resend.Webhooks.verify", lambda options: None)
    monkeypatch.setattr(
        "email_system.outreach_service.resend.Emails.Receiving.get",
        lambda email_id: {"text": "Friday fish tacos $12 today."},
    )
    monkeypatch.setattr(
        "email_system.outreach_service.resend.Emails.Receiving.Attachments.list",
        lambda email_id: {
            "data": [
                {
                    "content_type": "image/jpeg",
                    "download_url": "https://inbound-cdn.resend.com/email/attachments/photo",
                }
            ]
        },
    )
    monkeypatch.setattr(
        "special_pipeline.enhance_image_url",
        lambda image_url: {
            "success": True,
            "image_url": "https://res.cloudinary.com/demo/image/upload/c_limit,w_1200/e_improve/q_auto/f_auto/photo.jpg",
            "image_path": "appertivo/specials/photo",
            "error": None,
        },
    )
    monkeypatch.setattr(
        "email_system.resend_client.send_email",
        lambda **kwargs: sent.update(kwargs) or {"success": True, "provider": "resend", "message_id": "publish-email", "error": None},
    )
    monkeypatch.setattr(
        "special_pipeline.polish_special_copy",
        lambda raw_text, restaurant=None: {
            "success": True,
            "fields": {
                "title": "Enhanced Fish Tacos",
                "description": "Polished fish tacos.",
                "price_text": "$12",
                "availability_text": "today",
                "cta_text": "View Special",
            },
            "error": None,
        },
    )
    payload = json.dumps(
        {
            "type": "email.received",
            "data": {
                "email_id": "special-1",
                "from": "Owner <owner@example.com>",
                "to": ["specials@appertivo.com"],
                "subject": "Special",
                "created_at": "2026-06-01T12:00:00.000Z",
                "message_id": "<special@example.com>",
            },
        }
    )
    with app.app_context():
        campaign = create_campaign_for_restaurant(Restaurant.query.one())
        receive_resend_email(payload, {"id": "1", "timestamp": "1", "signature": "v1,test"})
        submission = RawSpecialSubmission.query.one()
        draft = submission.draft
        assert submission.restaurant_id == 1
        assert submission.raw_image_url == "https://inbound-cdn.resend.com/email/attachments/photo"
        assert draft is not None
        assert draft.title == "Enhanced Fish Tacos"
        assert draft.image_url.startswith("https://res.cloudinary.com/")
        assert campaign.status == "special_received"
    assert sent["to"] == "owner@example.com"
    assert "Enhanced Fish Tacos" in sent["html"]
    assert "Publish special" in sent["html"]


def test_admin_outreach_enroll_generate_send_and_email_tool_guard(outreach_app, monkeypatch):
    with app.test_client() as client:
        login(client)
        response = client.post(
            "/admin/outreach",
            data={
                "csrf_token": csrf(client),
                "restaurant_id": "1",
            },
        )
        assert response.status_code == 302
        response = client.get("/admin/outreach")
        assert b"Outreach inbox" in response.data
        response = client.get("/admin/outreach/1")
        assert b"Personalization" in response.data
        monkeypatch.setattr(
            "email_system.openai_client.generate_outreach_draft",
            lambda restaurant, instruction, sequence_step=None, personalization=None: {
                "success": True,
                "text": "Generated",
                "error": None,
            },
        )
        response = client.post("/admin/outreach/1/generate", data={"csrf_token": csrf(client)})
        assert response.status_code == 302
        with app.app_context():
            campaign = OutreachCampaign.query.one()
            draft = OutreachMessage.query.filter_by(campaign_id=campaign.id, body_text="Generated").one()
        response = client.post(
            "/admin/outreach/1",
            data={
                "csrf_token": csrf(client),
                "draft_id": str(draft.id),
                "recipient_email": "owner@example.com",
                "subject": "Hello",
                "body_text": "Reviewed",
                "tags": "test",
                "reviewed": "on",
            },
        )
        assert response.status_code == 302
        app.config["EMAIL_TEST_ENABLED"] = False
        response = client.post("/admin/email-tools", data={"csrf_token": csrf(client)}, follow_redirects=True)
        assert b"Email test sending is disabled" in response.data
    with app.app_context():
        assert OutreachCampaign.query.one().status == "drafting"
        assert OutreachMessage.query.filter_by(body_text="Reviewed", reviewed=True).one()
