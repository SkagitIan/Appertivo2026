import logging

import requests
from flask import current_app


logger = logging.getLogger(__name__)


def _output_text(data):
    return "".join(
        content.get("text", "")
        for item in data.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    ).strip()


def generate_outreach_draft(restaurant, instruction=None):
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        return {"success": False, "text": None, "error": "OPENAI_API_KEY is not configured."}

    context = {
        "name": restaurant.name,
        "city": restaurant.city,
        "category": restaurant.category,
        "address": restaurant.address,
        "website": restaurant.website,
        "phone": restaurant.phone,
    }
    prompt = (
        "Write a concise founder outreach email for this local restaurant. "
        "Ask them to send today's specials to Appertivo. Keep it warm, direct, and under 140 words. "
        "Do not invent facts. Return only the email body, without a subject line.\n\n"
        f"Restaurant context: {context}\n"
        f"Additional instruction: {instruction or 'None'}"
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": current_app.config["OPENAI_OUTREACH_MODEL"],
                "instructions": "You write practical restaurant outreach for Appertivo.",
                "input": prompt,
                "max_output_tokens": 300,
            },
            timeout=30,
        )
        data = response.json()
        if not response.ok:
            return {"success": False, "text": None, "error": data.get("error", {}).get("message", "OpenAI request failed.")}
        text = _output_text(data)
        if not text:
            return {"success": False, "text": None, "error": "OpenAI returned an empty draft."}
        return {"success": True, "text": text, "error": None}
    except (requests.RequestException, ValueError) as error:
        logger.exception("OpenAI outreach draft generation failed.")
        return {"success": False, "text": None, "error": str(error)}
