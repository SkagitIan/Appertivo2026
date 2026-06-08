import logging
import json
import re

import requests
from flask import current_app

from special_taxonomy import primary_tag_from, serialize_tag_keys


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


def _clean_recurrence_rule(value):
    rule = _clean_field(value).upper()
    if not rule.startswith("FREQ=") or "WEEKLY" not in rule:
        return None
    return rule[:120]


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
        "Use only these tag keys when clearly supported by the submission or restaurant context: "
        "happy_hour, pizza, burgers, seafood, date_night, brunch, cocktails, pasta, tacos, sushi, steak, dessert, "
        "italian, mexican, japanese, american, bbq, bakery, coffee. "
        "Do not use LTO or limited time offer language. "
        "Detect recurring specials only when clearly stated or strongly implied by a named weekday pattern. "
        "Examples: Taco Tuesday means FREQ=WEEKLY;BYDAY=TU, every Friday means FREQ=WEEKLY;BYDAY=FR, "
        "weekdays means FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR. Today only, tonight only, this weekend, or one-time dates are not recurring. "
        "If a field is unknown, return null or an empty string. Return only JSON with these flat keys: "
        "title, description, price_text, value_text, availability_text, cta_text, tag_keys, primary_tag, "
        "add_on_name, add_on_price, add_on_value_text, recurrence_rule, recurrence_label, recurrence_confidence, starts_at, expires_at. "
        "Return recurrence_rule as a simple RRULE string only for recurring specials, recurrence_label as plain English, "
        "and recurrence_confidence as high, medium, or low. "
        "Return starts_at and expires_at only as ISO 8601 strings when the raw submission clearly states them.\n\n"
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
        tag_keys = serialize_tag_keys(parsed.get("tag_keys") or [])
        tag_key_list = [key for key in tag_keys.split(",") if key]
        fields = {
            "title": (_clean_field(parsed.get("title")) or "Today's Special")[:160],
            "description": _clean_field(parsed.get("description")) or _clean_field(raw_text),
            "price_text": _clean_field(parsed.get("price_text")) or None,
            "value_text": _clean_field(parsed.get("value_text")) or None,
            "availability_text": _clean_field(parsed.get("availability_text")) or None,
            "cta_text": _clean_field(parsed.get("cta_text")) or "View Special",
            "tag_keys": tag_keys,
            "primary_tag": primary_tag_from(tag_key_list, parsed.get("primary_tag")),
            "add_on_name": _clean_field(parsed.get("add_on_name"))[:120] or None,
            "add_on_price": _clean_field(parsed.get("add_on_price")) or None,
            "add_on_value_text": _clean_field(parsed.get("add_on_value_text")) or None,
            "recurrence_rule": _clean_recurrence_rule(parsed.get("recurrence_rule")),
            "recurrence_label": _clean_field(parsed.get("recurrence_label"))[:120] or None,
            "recurrence_confidence": (
                _clean_field(parsed.get("recurrence_confidence")).lower()
                if _clean_field(parsed.get("recurrence_confidence")).lower() in {"high", "medium", "low"}
                else None
            ),
            "starts_at": _clean_field(parsed.get("starts_at")) or None,
            "expires_at": _clean_field(parsed.get("expires_at")) or None,
        }
        return {"success": True, "fields": fields, "error": None}
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as error:
        logger.exception("OpenAI special polishing failed.")
        return {"success": False, "fields": None, "error": str(error)}
