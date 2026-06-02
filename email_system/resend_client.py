import logging

import resend
from flask import current_app


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


def send_email(to, subject, html, text, from_email, reply_to=None, tags=None):
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

    try:
        resend.api_key = api_key
        response = resend.Emails.send(payload)
        return _result(True, message_id=_message_id(response))
    except Exception as error:  # Provider failures should not crash request handlers.
        logger.exception("Resend email send failed.")
        return _result(False, error=str(error))
