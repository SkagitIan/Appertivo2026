import logging
import json
import re

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


def _json_from_text(text):
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.I | re.M).strip()
    return json.loads(cleaned)


def _clean_field(value):
    return str(value or "").strip()


def generate_outreach_draft(restaurant, instruction=None, sequence_step=None, personalization=None):
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
    personalization = personalization or {}
    prompt = (
        "Write a concise founder outreach email for this local restaurant. "
        "Ask them to send today's specials to Appertivo. Keep it warm, direct, and under 140 words. "
        "Do not invent facts. Return only the email body, without a subject line. "
        "Use Ian's local restaurant-founder voice and keep it low-pressure.\n\n"
        f"Restaurant context: {context}\n"
        f"Sequence step: {sequence_step or 'unspecified'}\n"
        f"Personalization fields: {personalization}\n"
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


def polish_special_copy(raw_text, restaurant=None):
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key:
        return {"success": False, "fields": None, "error": "OPENAI_API_KEY is not configured."}

    restaurant_context = {}
    if restaurant:
        restaurant_context = {
            "name": restaurant.name,
            "city": restaurant.city,
            "category": restaurant.category,
            "address": restaurant.address,
        }
    prompt = (
        "Turn this restaurant special submission into clean structured fields for Appertivo. "
        "Correct spelling and grammar. Add light appetizing polish, but do not invent facts, ingredients, prices, dates, or availability. "
        "If a field is unknown, return null or an empty string. Return only JSON with these keys: "
        "title, description, price_text, availability_text, cta_text.\n\n"
        f"Restaurant context: {restaurant_context}\n"
        f"Raw special submission:\n{raw_text or ''}"
    )
    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": current_app.config["OPENAI_SPECIAL_MODEL"],
                "instructions": "You produce factual, polished JSON for local restaurant specials.",
                "input": prompt,
                "max_output_tokens": 450,
            },
            timeout=30,
        )
        data = response.json()
        if not response.ok:
            return {"success": False, "fields": None, "error": data.get("error", {}).get("message", "OpenAI request failed.")}
        parsed = _json_from_text(_output_text(data))
        fields = {
            "title": (_clean_field(parsed.get("title")) or "Today's Special")[:160],
            "description": _clean_field(parsed.get("description")) or _clean_field(raw_text),
            "price_text": _clean_field(parsed.get("price_text")) or None,
            "availability_text": _clean_field(parsed.get("availability_text")) or None,
            "cta_text": _clean_field(parsed.get("cta_text")) or "View Special",
        }
        return {"success": True, "fields": fields, "error": None}
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as error:
        logger.exception("OpenAI special polishing failed.")
        return {"success": False, "fields": None, "error": str(error)}
