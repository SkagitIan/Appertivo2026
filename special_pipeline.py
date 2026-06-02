import re

from models import RawSpecialSubmission, Restaurant, Special, SpecialDraft, db, utc_now


AVAILABILITY_PHRASES = ("happy hour", "this week", "weekend", "tonight", "today")


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
    return {
        "title": title,
        "description": raw_text or normalized,
        "price_text": price_match.group(0).replace(" ", "") if price_match else None,
        "availability_text": availability,
        "cta_text": "View Special",
    }


def create_or_prepare_image(raw_submission):
    if raw_submission.raw_image_url or raw_submission.raw_image_path:
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


def generate_draft_from_submission(raw_submission_id):
    submission = db.session.get(RawSpecialSubmission, raw_submission_id)
    if not submission:
        raise ValueError("Raw special submission was not found.")
    if submission.draft:
        return submission.draft
    draft = SpecialDraft(
        raw_submission_id=submission.id,
        restaurant_id=submission.restaurant_id,
        status="draft" if submission.source_channel == "admin" else "awaiting_approval",
        **polish_special_text(submission.raw_text),
        **create_or_prepare_image(submission),
    )
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
    special = Special(
        draft_id=draft.id,
        restaurant_id=draft.restaurant_id,
        title=draft.title,
        description=draft.description,
        price=draft.price_text or "",
        availability_text=draft.availability_text,
        cta_text=draft.cta_text,
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
    return special
