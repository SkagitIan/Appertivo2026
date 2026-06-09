import re
import secrets
from datetime import UTC, datetime

from flask import current_app

from email_system.cloudinary_client import enhance_image_url
from email_system.openai_client import polish_special_copy
from models import RawSpecialSubmission, Restaurant, Special, SpecialDraft, db, utc_now
from special_taxonomy import infer_tags_from_text, primary_tag_from, serialize_tag_keys


AVAILABILITY_PHRASES = ("happy hour", "this week", "weekend", "tonight", "today")
WEEKDAY_RULES = {
    "monday": ("MO", "Monday"),
    "tuesday": ("TU", "Tuesday"),
    "wednesday": ("WE", "Wednesday"),
    "thursday": ("TH", "Thursday"),
    "friday": ("FR", "Friday"),
    "saturday": ("SA", "Saturday"),
    "sunday": ("SU", "Sunday"),
}
WEEKDAY_ALIASES = {
    "mon": "monday",
    "tue": "tuesday",
    "tues": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "thur": "thursday",
    "thurs": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}
RECURRENCE_CONFIDENCE_VALUES = {"high", "medium", "low"}


def parse_iso_datetime(value):
    value = str(value or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def extract_value_text(text):
    normalized = " ".join((text or "").split())
    patterns = [
        r"\(\s*(\$\s?\d+(?:\.\d{2})?)\s+value\s*\)",
        r"\bvalue\s*:?\s*(\$\s?\d+(?:\.\d{2})?)",
        r"\bregularly\s+(\$\s?\d+(?:\.\d{2})?)",
        r"\bwas\s+(\$\s?\d+(?:\.\d{2})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, re.I)
        if match:
            return f"{match.group(1).replace(' ', '')} value"
    return None


def extract_add_on_fields(text):
    match = re.search(r"\badd-?on\b[:\s-]*(.{1,140})", text or "", re.I)
    if not match:
        return {"add_on_name": None, "add_on_price": None, "add_on_value_text": None}
    snippet = re.split(r"[.;\n]", match.group(1), maxsplit=1)[0].strip()
    price_match = re.search(r"\$\s?\d+(?:\.\d{2})?", snippet)
    value_text = extract_value_text(snippet)
    name = snippet
    price = None
    if price_match:
        price = price_match.group(0).replace(" ", "")
        name = snippet[: price_match.start()].strip(" :-,") or snippet[price_match.end() :].strip(" :-,")
    name = re.sub(r"\([^)]*value[^)]*\)", "", name, flags=re.I).strip(" :-,")
    return {
        "add_on_name": name[:120] or None,
        "add_on_price": price,
        "add_on_value_text": value_text,
    }


def clean_recurrence_fields(fields):
    rule = str(fields.get("recurrence_rule") or "").strip().upper()
    label = str(fields.get("recurrence_label") or "").strip()
    confidence = str(fields.get("recurrence_confidence") or "").strip().lower()
    if not rule.startswith("FREQ=") or "WEEKLY" not in rule:
        rule = ""
    if confidence not in RECURRENCE_CONFIDENCE_VALUES:
        confidence = ""
    if not rule:
        return {"recurrence_rule": None, "recurrence_label": None, "recurrence_confidence": None}
    return {
        "recurrence_rule": rule[:120],
        "recurrence_label": (label or rule)[:120],
        "recurrence_confidence": confidence or "medium",
    }


def infer_recurrence_from_text(text):
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return {"recurrence_rule": None, "recurrence_label": None, "recurrence_confidence": None}
    if re.search(r"\b(today|tonight|one night|one day|only)\s+only\b", normalized):
        return {"recurrence_rule": None, "recurrence_label": None, "recurrence_confidence": None}
    if re.search(r"\bweekdays?\b", normalized):
        return {
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
            "recurrence_label": "Every weekday",
            "recurrence_confidence": "high",
        }
    for key, (byday, label) in WEEKDAY_RULES.items():
        aliases = [key, *(alias for alias, canonical in WEEKDAY_ALIASES.items() if canonical == key)]
        phrase_pattern = "|".join(re.escape(alias) for alias in aliases)
        if re.search(rf"\b(every|each)\s+({phrase_pattern})\b", normalized) or re.search(
            rf"\b({phrase_pattern})s?\b", normalized
        ):
            return {
                "recurrence_rule": f"FREQ=WEEKLY;BYDAY={byday}",
                "recurrence_label": f"Every {label}",
                "recurrence_confidence": "high" if re.search(rf"\b(every|each)\s+({phrase_pattern})\b", normalized) else "medium",
            }
    return {"recurrence_rule": None, "recurrence_label": None, "recurrence_confidence": None}


def finalize_special_fields(fields, raw_text, restaurant=None):
    fields = dict(fields or {})
    tags = serialize_tag_keys(fields.get("tag_keys") or [])
    if not tags:
        tags = serialize_tag_keys(
            infer_tags_from_text(
                raw_text,
                fields.get("title"),
                fields.get("description"),
                getattr(restaurant, "name", ""),
                getattr(restaurant, "category", ""),
                getattr(restaurant, "subtypes", ""),
                getattr(restaurant, "cuisine_tags", ""),
            )
        )
    tag_keys = [key for key in tags.split(",") if key]
    fields["tag_keys"] = tags
    fields["primary_tag"] = primary_tag_from(tag_keys, fields.get("primary_tag"))
    fields["value_text"] = fields.get("value_text") or extract_value_text(raw_text)
    add_on_fields = extract_add_on_fields(raw_text)
    for key, value in add_on_fields.items():
        fields[key] = fields.get(key) or value
    recurrence_fields = clean_recurrence_fields(fields)
    if not recurrence_fields["recurrence_rule"]:
        recurrence_fields = infer_recurrence_from_text(raw_text)
    fields.update(recurrence_fields)
    fields["starts_at"] = parse_iso_datetime(fields.get("starts_at"))
    fields["expires_at"] = parse_iso_datetime(fields.get("expires_at"))
    return fields


def polish_special_text(raw_text):
    raw_text = (raw_text or "").strip()
    normalized = " ".join(raw_text.split())
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    first_line = lines[0] if len(lines) > 1 else ""
    first_sentence = re.split(r"[.!?]", normalized, maxsplit=1)[0].strip()
    title = first_line or first_sentence or "Today's Special"
    if len(title) > 160:
        title = title[:157].rstrip() + "..."
    price_match = re.search(r"\$\s?\d+(?:\.\d{2})?", normalized)
    availability = next(
        (phrase for phrase in AVAILABILITY_PHRASES if re.search(rf"\b{re.escape(phrase)}\b", normalized, re.I)),
        None,
    )
    fields = {
        "title": title,
        "description": raw_text or normalized,
        "price_text": price_match.group(0).replace(" ", "") if price_match else None,
        "value_text": extract_value_text(raw_text),
        "availability_text": availability,
        "cta_text": "View Special",
        "tag_keys": serialize_tag_keys(infer_tags_from_text(raw_text)),
        "primary_tag": None,
        **extract_add_on_fields(raw_text),
        **infer_recurrence_from_text(raw_text),
        "starts_at": None,
        "expires_at": None,
    }
    fields["primary_tag"] = primary_tag_from(fields["tag_keys"].split(","))
    return fields


def enhanced_special_text(raw_text, restaurant=None):
    result = polish_special_copy(raw_text, restaurant=restaurant)
    if result["success"]:
        return finalize_special_fields(result["fields"], raw_text, restaurant)
    if result["error"] != "OPENAI_API_KEY is not configured.":
        current_app.logger.warning("OpenAI special polish skipped: %s", result["error"])
    return finalize_special_fields(polish_special_text(raw_text), raw_text, restaurant)


def create_or_prepare_image(raw_submission):
    if raw_submission.raw_image_url or raw_submission.raw_image_path:
        if raw_submission.raw_image_url and raw_submission.raw_image_url.startswith(("http://", "https://")):
            enhanced = enhance_image_url(raw_submission.raw_image_url)
            if enhanced["success"]:
                return {
                    "image_url": enhanced["image_url"],
                    "image_path": enhanced["image_path"],
                    "ai_generated_image": False,
                    "image_disclaimer": None,
                }
            if enhanced["error"] != "Cloudinary is not configured.":
                current_app.logger.warning("Cloudinary image enhancement skipped: %s", enhanced["error"])
        return {
            "image_url": raw_submission.raw_image_url,
            "image_path": raw_submission.raw_image_path,
            "ai_generated_image": False,
            "image_disclaimer": None,
        }
    # TODO: Add optional AI image generation here when a provider and review policy are configured.
    return {
        "image_url": None,
        "image_path": None,
        "ai_generated_image": False,
        "image_disclaimer": None,
    }


def create_raw_submission(
    *,
    source_channel,
    raw_text,
    restaurant_id=None,
    raw_image_url=None,
    raw_image_path=None,
    sender_email=None,
    sender_phone=None,
    source_url=None,
):
    submission = RawSpecialSubmission(
        restaurant_id=restaurant_id,
        source_channel=source_channel,
        raw_text=(raw_text or "").strip(),
        raw_image_url=raw_image_url,
        raw_image_path=raw_image_path,
        sender_email=sender_email,
        sender_phone=sender_phone,
        source_url=source_url,
    )
    db.session.add(submission)
    db.session.commit()
    return submission


def notify_admin_of_new_submission(draft):
    admin_email = current_app.config.get("ADMIN_NOTIFICATION_EMAIL", "").strip()
    if not admin_email:
        return None
    from email_system.email_service import send_notification_email
    base_url = current_app.config.get("APP_BASE_URL", "").rstrip("/")
    preview_url = f"{base_url}/specials/preview/{draft.approval_token}" if draft.approval_token else None
    restaurant_name = draft.restaurant.name if draft.restaurant else "Unknown restaurant"
    source = draft.raw_submission.source_channel if draft.raw_submission else "unknown"
    parts = [f"New special from {restaurant_name} via {source}."]
    if draft.title:
        parts.append(f"Title: {draft.title}")
    if preview_url:
        parts.append(f"\nPreview: {preview_url}")
    return send_notification_email(admin_email, f"New special — {restaurant_name}", "\n".join(parts))


def generate_draft_from_submission(raw_submission_id):
    submission = db.session.get(RawSpecialSubmission, raw_submission_id)
    if not submission:
        raise ValueError("Raw special submission was not found.")
    if submission.draft:
        return submission.draft
    fields = enhanced_special_text(submission.raw_text, restaurant=submission.restaurant)
    image_fields = create_or_prepare_image(submission)
    draft = SpecialDraft(
        raw_submission_id=submission.id,
        restaurant_id=submission.restaurant_id,
        status="draft" if submission.source_channel == "admin" else "awaiting_approval",
        **fields,
        **image_fields,
    )
    submission.status = "drafted" if draft.status == "draft" else "awaiting_approval"
    db.session.add(draft)
    db.session.commit()
    if draft.status == "awaiting_approval":
        notify_admin_of_new_submission(draft)
    return draft


def enhance_draft_from_submission(raw_submission_id):
    submission = db.session.get(RawSpecialSubmission, raw_submission_id)
    if not submission:
        raise ValueError("Raw special submission was not found.")
    draft = submission.draft or SpecialDraft(
        raw_submission_id=submission.id,
        restaurant_id=submission.restaurant_id,
        status="draft" if submission.source_channel == "admin" else "awaiting_approval",
    )
    fields = enhanced_special_text(submission.raw_text, restaurant=submission.restaurant)
    image_fields = create_or_prepare_image(submission)
    for key, value in {**fields, **image_fields}.items():
        setattr(draft, key, value)
    draft.restaurant_id = submission.restaurant_id
    submission.status = "drafted" if draft.status == "draft" else "awaiting_approval"
    db.session.add(draft)
    db.session.commit()
    return draft


def approve_draft(token):
    draft = SpecialDraft.query.filter_by(approval_token=token).first()
    if not draft:
        raise ValueError("Special draft was not found.")
    if not draft.restaurant_id or not Restaurant.query.filter_by(
        id=draft.restaurant_id, catalog_status="included"
    ).first():
        raise ValueError("Assign an included restaurant before approving this draft.")
    draft.status = "approved"
    draft.raw_submission.status = "approved"
    db.session.commit()
    return draft


def reject_draft(token):
    draft = SpecialDraft.query.filter_by(approval_token=token).first()
    if not draft:
        raise ValueError("Special draft was not found.")
    draft.status = "rejected"
    draft.raw_submission.status = "rejected"
    db.session.commit()
    return draft


def _ensure_call_schedule_token(restaurant):
    if not restaurant.call_schedule_token:
        restaurant.call_schedule_token = secrets.token_hex(24)
        db.session.commit()
    return restaurant.call_schedule_token


def schedule_first_special_followup_if_needed(special, recipient_email=None):
    recipient = (recipient_email or getattr(special.restaurant, "contact_email", "") or "").strip().lower()
    if not recipient:
        return None
    previous_special = (
        Special.query.filter(
            Special.restaurant_id == special.restaurant_id,
            Special.id != special.id,
            Special.published_at.isnot(None),
        )
        .order_by(Special.published_at.asc())
        .first()
    )
    if previous_special:
        return None

    from email_system.email_service import send_first_special_followup_email

    base_url = current_app.config["APP_BASE_URL"].rstrip("/")
    restaurant_url = f"{base_url}/restaurants/{special.restaurant.slug}" if special.restaurant else None
    token = _ensure_call_schedule_token(special.restaurant) if special.restaurant else None
    schedule_call_url = f"{base_url}/schedule-call/{token}" if token else None
    return send_first_special_followup_email(
        recipient,
        restaurant_name=special.restaurant.name if special.restaurant else None,
        restaurant_url=restaurant_url,
        schedule_call_url=schedule_call_url,
        scheduled_at="in 5 minutes",
    )


def publish_draft(draft_id):
    draft = db.session.get(SpecialDraft, draft_id)
    if not draft:
        raise ValueError("Special draft was not found.")
    if draft.published_special:
        return draft.published_special
    if draft.status != "approved":
        raise ValueError("Approve this draft before publishing it.")
    if not draft.restaurant_id:
        raise ValueError("Assign a restaurant before publishing this draft.")
    first_published_special = not Special.query.filter(
        Special.restaurant_id == draft.restaurant_id,
        Special.published_at.isnot(None),
    ).first()
    special = Special(
        draft_id=draft.id,
        restaurant_id=draft.restaurant_id,
        title=draft.title,
        description=draft.description,
        price=draft.price_text or "",
        value_text=draft.value_text,
        availability_text=draft.availability_text,
        cta_text=draft.cta_text,
        tag_keys=draft.tag_keys or "",
        primary_tag=draft.primary_tag,
        add_on_name=draft.add_on_name,
        add_on_price=draft.add_on_price,
        add_on_value_text=draft.add_on_value_text,
        recurrence_rule=draft.recurrence_rule,
        recurrence_label=draft.recurrence_label,
        recurrence_confidence=draft.recurrence_confidence,
        featured_rank=draft.featured_rank,
        starts_at=draft.starts_at,
        expires_at=draft.expires_at,
        status="published",
        source=draft.raw_submission.source_channel,
        raw_text=draft.raw_submission.raw_text,
        photo_url=draft.image_url,
        photo_object_key=draft.image_path,
        submitted_at=draft.raw_submission.created_at,
        published_at=utc_now(),
    )
    draft.status = "published"
    draft.raw_submission.status = "published"
    db.session.add(special)
    db.session.commit()
    if first_published_special:
        schedule_first_special_followup_if_needed(special, draft.raw_submission.sender_email)
    return special
