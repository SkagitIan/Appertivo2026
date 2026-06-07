import logging

import resend
from flask import current_app

from email_system.capture import write_capture


logger = logging.getLogger(__name__)


def _result(success, message_id=None, error=None):
    return {
        "success": success,
        "provider": "resend",
        "message_id": message_id,
        "error": error,
    }


def _message_id(response):
    if isinstance(response, dict):
        return response.get("id")
    return getattr(response, "id", None)


def send_email(to, subject, html, text, from_email, reply_to=None, tags=None, scheduled_at=None):
    capture_id = write_capture(
        {
            "kind": "email",
            "provider_action": "resend.send_email",
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
            "from_email": from_email,
            "reply_to": reply_to,
            "tags": tags or [],
            "scheduled_at": scheduled_at,
        }
    )
    if capture_id:
        return _result(True, message_id=capture_id)

    api_key = current_app.config.get("RESEND_API_KEY")
    if not api_key:
        error = "RESEND_API_KEY is not configured."
        logger.error(error)
        return _result(False, error=error)

    payload = {
        "from": from_email,
        "to": to,
        "subject": subject,
        "html": html,
        "text": text,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    if tags:
        payload["tags"] = tags
    if scheduled_at:
        payload["scheduled_at"] = scheduled_at

    try:
        resend.api_key = api_key
        response = resend.Emails.send(payload)
        return _result(True, message_id=_message_id(response))
    except Exception as error:  # Provider failures should not crash request handlers.
        logger.exception("Resend email send failed.")
        return _result(False, error=str(error))
