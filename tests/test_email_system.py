import os
import json
from types import SimpleNamespace

import resend


os.environ["DATABASE_URL"] = "sqlite://"

from app import app
from email_system import loops_client, resend_client
from email_system.email_service import (
    SUBJECTS,
    render_email_template,
    send_all_test_emails,
    send_magic_link_email,
    send_sales_outreach_email,
)


def test_all_email_templates_render_html_and_plaintext():
    context = {
        "magic_link_url": "https://example.com/sign-in",
        "verification_url": "https://example.com/verify",
        "user_name": "Alex",
        "message": "A useful update.",
        "restaurant_name": "Example Cafe",
        "special_title": "Friday Fish Tacos",
        "contact_name": "Sam",
        "custom_message": "A short note.",
        "show_unsubscribe_placeholder": True,
    }
    with app.app_context():
        for template_name in SUBJECTS:
            rendered = render_email_template(template_name, context)
            assert "Appertivo" in rendered["html"]
            assert "Appertivo" in rendered["text"]


def test_magic_link_uses_noreply_sender(monkeypatch):
    sent = {}

    def fake_send_email(**kwargs):
        sent.update(kwargs)
        return {"success": True, "provider": "resend", "message_id": "email-1", "error": None}

    monkeypatch.setattr(resend_client, "send_email", fake_send_email)
    with app.app_context():
        app.config["EMAIL_FROM_NOREPLY"] = "system@example.com"
        result = send_magic_link_email("diner@example.com", "https://example.com/sign-in")

    assert result["success"] is True
    assert sent["from_email"] == "system@example.com"
    assert sent["to"] == "diner@example.com"
    assert "https://example.com/sign-in" in sent["text"]


def test_sales_outreach_uses_sales_sender_and_unsubscribe_placeholder(monkeypatch):
    sent = {}

    def fake_send_email(**kwargs):
        sent.update(kwargs)
        return {"success": True, "provider": "resend", "message_id": "email-2", "error": None}

    monkeypatch.setattr(resend_client, "send_email", fake_send_email)
    with app.app_context():
        app.config.update(
            EMAIL_FROM_SALES="ian@example.com",
            EMAIL_REPLY_TO_SALES="reply@example.com",
        )
        send_sales_outreach_email("owner@example.com", contact_name="Owner")

    assert sent["from_email"] == "ian@example.com"
    assert sent["reply_to"] == "reply@example.com"
    assert "Unsubscribe: [unsubscribe link]" in sent["text"]


def test_resend_wrapper_normalizes_success_and_missing_key(monkeypatch):
    sent = {}
    monkeypatch.setattr(resend.Emails, "send", lambda payload: sent.update(payload) or {"id": "resend-1"})

    with app.app_context():
        app.config["RESEND_API_KEY"] = "test-key"
        result = resend_client.send_email(
            to="diner@example.com",
            subject="Subject",
            html="<p>Hello</p>",
            text="Hello",
            from_email="noreply@example.com",
            reply_to="reply@example.com",
            tags=[{"name": "kind", "value": "test"}],
            scheduled_at="in 5 minutes",
        )
        app.config["RESEND_API_KEY"] = None
        missing_key = resend_client.send_email(
            to="diner@example.com",
            subject="Subject",
            html="<p>Hello</p>",
            text="Hello",
            from_email="noreply@example.com",
        )

    assert result == {"success": True, "provider": "resend", "message_id": "resend-1", "error": None}
    assert sent["reply_to"] == "reply@example.com"
    assert sent["tags"] == [{"name": "kind", "value": "test"}]
    assert sent["scheduled_at"] == "in 5 minutes"
    assert missing_key["success"] is False
    assert "RESEND_API_KEY" in missing_key["error"]


def test_loops_contact_and_event_payloads(monkeypatch):
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return SimpleNamespace(ok=True, status_code=200, json=lambda: {"success": True, "id": "contact-1"})

    monkeypatch.setattr(loops_client.requests, "request", fake_request)
    with app.app_context():
        app.config["LOOPS_API_KEY"] = "loops-key"
        contact = loops_client.create_or_update_contact("owner@example.com", {"source": "lead"})
        event = loops_client.send_event("owner@example.com", "restaurantLeadCreated", {"city": "Anacortes"})

    assert contact["contact_id"] == "contact-1"
    assert calls[0][0:2] == ("PUT", "https://app.loops.so/api/v1/contacts/update")
    assert calls[0][2]["json"] == {"email": "owner@example.com", "source": "lead"}
    assert calls[1][0:2] == ("POST", "https://app.loops.so/api/v1/events/send")
    assert calls[1][2]["json"] == {
        "email": "owner@example.com",
        "eventName": "restaurantLeadCreated",
        "eventProperties": {"city": "Anacortes"},
    }


def test_email_and_loops_capture_backend(tmp_path):
    capture_path = tmp_path / "email-capture.jsonl"
    with app.app_context():
        previous_capture = app.config.get("EMAIL_CAPTURE_PATH")
        previous_resend_key = app.config.get("RESEND_API_KEY")
        previous_loops_key = app.config.get("LOOPS_API_KEY")
        app.config.update(EMAIL_CAPTURE_PATH=str(capture_path), RESEND_API_KEY=None, LOOPS_API_KEY=None)
        try:
            email = resend_client.send_email(
                to="owner@example.com",
                subject="Captured",
                html="<p>Captured</p>",
                text="Captured",
                from_email="specials@example.com",
                reply_to="reply@example.com",
                tags=[{"name": "channel", "value": "test"}],
                scheduled_at="in 5 minutes",
            )
            contact = loops_client.create_or_update_contact("owner@example.com", {"source": "test"})
            event = loops_client.send_event("owner@example.com", "restaurantSpecialReceived", {"draft": "1"})
        finally:
            app.config.update(
                EMAIL_CAPTURE_PATH=previous_capture,
                RESEND_API_KEY=previous_resend_key,
                LOOPS_API_KEY=previous_loops_key,
            )

    records = [json.loads(line) for line in capture_path.read_text(encoding="utf-8").splitlines()]
    assert email["success"] is True
    assert email["message_id"].startswith("capture-")
    assert contact["contact_id"].startswith("capture-")
    assert event["event_id"].startswith("capture-")
    assert [record["kind"] for record in records] == ["email", "loops_contact", "loops_event"]
    assert records[0]["to"] == "owner@example.com"
    assert records[0]["tags"] == [{"name": "channel", "value": "test"}]
    assert records[0]["scheduled_at"] == "in 5 minutes"
    assert records[1]["properties"] == {"source": "test"}
    assert records[2]["event_name"] == "restaurantSpecialReceived"


def test_email_test_cli_is_disabled_by_default(monkeypatch):
    app.config["EMAIL_TEST_ENABLED"] = False
    result = app.test_cli_runner().invoke(args=["email-test", "--to", "ian@example.com"])
    assert result.exit_code == 1
    assert "Email test sending is disabled" in result.output


def test_email_test_cli_sends_when_enabled(monkeypatch):
    monkeypatch.setattr(
        "email_system.email_service.send_test_email",
        lambda to, template: {
            "success": True,
            "provider": "resend",
            "message_id": "email-3",
            "error": None,
        },
    )
    app.config["EMAIL_TEST_ENABLED"] = True
    result = app.test_cli_runner().invoke(
        args=["email-test", "--to", "ian@example.com", "--template", "magic_link"]
    )
    assert result.exit_code == 0
    assert "Sent magic_link email via resend: email-3" in result.output


def test_send_all_test_emails_sends_each_template(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "email_system.email_service.send_test_email",
        lambda to, template: sent.append((to, template))
        or {"success": True, "provider": "resend", "message_id": template, "error": None},
    )
    with app.app_context():
        results = send_all_test_emails("ian.larsen.1976@gmail.com")
    assert list(results) == list(SUBJECTS)
    assert len(sent) == 9
