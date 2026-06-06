import logging

import requests
from flask import current_app

from email_system.capture import write_capture


logger = logging.getLogger(__name__)
BASE_URL = "https://app.loops.so/api/v1"


def _result(success, error=None, **details):
    return {
        "success": success,
        "provider": "loops",
        "message_id": None,
        "error": error,
        **details,
    }


def _request(method, path, payload):
    api_key = current_app.config.get("LOOPS_API_KEY")
    if not api_key:
        error = "LOOPS_API_KEY is not configured."
        logger.error(error)
        return _result(False, error=error)

    try:
        response = requests.request(
            method,
            f"{BASE_URL}/{path}",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10,
        )
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Loops returned an invalid JSON response.")
        if not response.ok or not data.get("success"):
            error = data.get("message") or f"Loops request failed with HTTP {response.status_code}."
            logger.error("Loops request failed: %s", error)
            return _result(False, error=error)
        return _result(True, contact_id=data.get("id"))
    except requests.RequestException as error:
        logger.exception("Loops request failed.")
        return _result(False, error=str(error))
    except ValueError as error:
        logger.exception("Loops returned an invalid JSON response.")
        return _result(False, error=str(error))


def create_or_update_contact(email, properties=None):
    capture_id = write_capture(
        {
            "kind": "loops_contact",
            "provider_action": "loops.create_or_update_contact",
            "email": email,
            "properties": properties or {},
        }
    )
    if capture_id:
        return _result(True, contact_id=capture_id)
    return _request("PUT", "contacts/update", {"email": email, **(properties or {})})


def send_event(email, event_name, properties=None):
    capture_id = write_capture(
        {
            "kind": "loops_event",
            "provider_action": "loops.send_event",
            "email": email,
            "event_name": event_name,
            "properties": properties or {},
        }
    )
    if capture_id:
        return _result(True, event_id=capture_id)
    payload = {"email": email, "eventName": event_name}
    if properties:
        payload["eventProperties"] = properties
    return _request("POST", "events/send", payload)
