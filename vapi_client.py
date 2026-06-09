import logging

import requests
from flask import current_app


logger = logging.getLogger(__name__)

VAPI_PHONE_URL = "https://api.vapi.ai/call/phone"

_SYSTEM_PROMPT = """\
You are Julie, a brief and friendly caller from Appertivo — a restaurant specials platform in the Pacific Northwest. Your only job is to collect this week's special from the restaurant you're calling.

Ask for, in order:
1. The name of the special (and a short description if they offer one)
2. The price
3. When it runs until — tonight only, this weekend, every Thursday, etc.

Keep the whole call under 60 seconds. Be warm but efficient — the person you're calling is likely at work.

If they have questions you can't answer, or want to discuss anything else, say exactly:
"I can have Ian call you back for that — what's the best number to reach you?"

Once you have all three details, say:
"Perfect, I've got everything I need — we'll get that posted right away. Have a great day!"
Then end the call.

Never invent information about Appertivo. Never discuss pricing, contracts, or anything outside of collecting the special.
"""

_FIRST_MESSAGE = (
    "Hi, this is Julie calling from Appertivo! "
    "Just a quick call to grab your special for this week — what are you running?"
)


def _result(success, call_id=None, error=None):
    return {"success": success, "call_id": call_id, "error": error}


def trigger_julie_call(restaurant):
    api_key = (current_app.config.get("VAPI_API_KEY") or "").strip()
    if not api_key:
        return _result(False, error="VAPI_API_KEY is not configured.")

    phone_number_id = (current_app.config.get("VAPI_PHONE_NUMBER_ID") or "").strip()
    if not phone_number_id:
        return _result(False, error="VAPI_PHONE_NUMBER_ID is not configured.")

    customer_phone = (restaurant.international_phone or restaurant.phone or "").strip()
    if not customer_phone:
        return _result(False, error=f"Restaurant {restaurant.id} has no phone number.")

    voice_id = current_app.config.get("VAPI_JULIE_VOICE_ID", "").strip()
    voice = (
        {"provider": "11labs", "voiceId": voice_id}
        if voice_id
        else {"provider": "openai", "voiceId": "alloy"}
    )

    payload = {
        "assistant": {
            "firstMessage": _FIRST_MESSAGE,
            "model": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "systemPrompt": _SYSTEM_PROMPT,
            },
            "voice": voice,
            "maxDurationSeconds": 120,
        },
        "phoneNumberId": phone_number_id,
        "customer": {"number": customer_phone},
        "metadata": {"restaurant_id": restaurant.id},
    }

    try:
        response = requests.post(
            VAPI_PHONE_URL,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        call_id = response.json().get("id")
        logger.info("Vapi call triggered for restaurant %s, call_id=%s", restaurant.id, call_id)
        return _result(True, call_id=call_id)
    except Exception:
        logger.exception("Vapi call trigger failed for restaurant %s.", restaurant.id)
        return _result(False, error="Vapi API request failed.")
