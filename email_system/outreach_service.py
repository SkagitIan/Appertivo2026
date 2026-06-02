import logging
import re
from datetime import datetime, timedelta

import resend
from flask import current_app, render_template

from email_system import loops_client, resend_client
from models import OutreachCampaign, OutreachMessage, OutreachSuppression, Restaurant, db, utc_now
from special_pipeline import create_raw_submission, generate_draft_from_submission


logger = logging.getLogger(__name__)
OPT_OUT_RE = re.compile(r"\b(no thanks|unsubscribe|remove me|stop emailing|do not email|don't email)\b", re.I)
SEQUENCE_TEMPLATES = {
    1: {
        "key": "personal_intro",
        "subject": "Quick idea for {restaurant_name}",
        "body": """Hi {greeting},

I'm Ian. I used to own restaurants here in Skagit Valley, and I'm building a simple local dining project called Appertivo.

The idea is straightforward:

Send us your special. We make it look good and get it in front of local diners.

I noticed {personalized_observation} and thought {restaurant_name} would be a good fit.

If you ever have a lunch special, dinner special, happy hour item, or slow-night promo, you can just send it to:

specials@appertivo.com

I'll feature the first one free while I'm getting this started.

No call needed.

Ian
Appertivo
ian@appertivo.com

Unsubscribe: reply "no thanks" """,
    },
    2: {
        "key": "specific_example",
        "subject": "Could feature {restaurant_name} this week",
        "body": """Hi {greeting},

Just following up once.

I'm starting with a small group of Skagit restaurants and featuring real specials people can act on today.

For {restaurant_name}, something like this would work well:

{example_special}

You would not need to learn software. Just email the special to specials@appertivo.com and I'll clean it up.

Ian""",
    },
    3: {
        "key": "free_special_offer",
        "subject": "Free special feature?",
        "body": """Hi {greeting},

Simple offer:

Send me one special, and I'll feature it free on Appertivo while I'm launching.

This is built for restaurants that do not have time to mess with another marketing tool.

If it helps, great. If not, no pressure.

Ian""",
    },
    4: {
        "key": "close_loop",
        "subject": "Should I close the loop?",
        "body": """Hi {greeting},

Last note from me.

I'm putting together the first batch of local restaurants for Appertivo. I thought {restaurant_name} might be a good fit because {personalized_reason}.

If you want to try it, send a special anytime to specials@appertivo.com.

If not, no problem - I won't keep following up.

Ian""",
    },
}


def normalize_email(email):
    return (email or "").strip().lower()


def is_suppressed(email):
    return bool(OutreachSuppression.query.filter_by(email=normalize_email(email)).first())


def suppress_email(email, reason="opt_out", source="admin"):
    normalized = normalize_email(email)
    if not normalized:
        return None
    suppression = OutreachSuppression.query.filter_by(email=normalized).first()
    if not suppression:
        suppression = OutreachSuppression(email=normalized, reason=reason, source=source)
        db.session.add(suppression)
    return suppression


def restaurant_is_eligible(restaurant):
    return bool(restaurant and restaurant.catalog_status == "included" and normalize_email(restaurant.contact_email))


def followup_days_for_step(step):
    values = current_app.config.get("OUTREACH_FOLLOWUP_DAYS", "3,4,5")
    if isinstance(values, str):
        days = [int(value.strip()) for value in values.split(",") if value.strip()]
    else:
        days = list(values)
    return days[max(0, min(step - 1, len(days) - 1))] if days else 3


def _fallback(value, fallback):
    value = (value or "").strip()
    return value or fallback


def render_sequence_template(campaign, step):
    template = SEQUENCE_TEMPLATES[step]
    restaurant = campaign.restaurant
    context = {
        "restaurant_name": restaurant.name,
        "greeting": _fallback(campaign.contact_name, restaurant.name),
        "personalized_observation": _fallback(
            campaign.personalized_observation,
            f"{restaurant.name} is part of the local {restaurant.city} dining scene",
        ),
        "example_special": _fallback(
            campaign.example_special,
            "a lunch special, dinner special, happy hour item, or slow-night promo",
        ),
        "personalized_reason": _fallback(
            campaign.personalized_reason,
            f"you're a local restaurant in {restaurant.city}",
        ),
    }
    return {
        "template_key": template["key"],
        "subject": template["subject"].format(**context),
        "body_text": template["body"].format(**context),
    }


def create_campaign_for_restaurant(restaurant, recipient_email=None):
    if not restaurant_is_eligible(restaurant):
        raise ValueError("Only included restaurants with contact email can be enrolled.")
    recipient = normalize_email(recipient_email or restaurant.contact_email)
    if is_suppressed(recipient):
        raise ValueError("This email address has opted out.")
    campaign = OutreachCampaign.query.filter_by(restaurant_id=restaurant.id, recipient_email=recipient).first()
    if campaign:
        return campaign
    campaign = OutreachCampaign(
        restaurant_id=restaurant.id,
        recipient_email=recipient,
        status="drafting",
    )
    db.session.add(campaign)
    db.session.flush()
    create_sequence_draft(campaign, 1, commit=False)
    db.session.commit()
    return campaign


def create_sequence_draft(campaign, step=None, commit=True):
    if is_suppressed(campaign.recipient_email):
        raise ValueError("This email address has opted out.")
    step = step or min(campaign.current_step + 1, 4)
    if step < 1 or step > 4:
        raise ValueError("Outreach sequence only supports steps 1 through 4.")
    rendered = render_sequence_template(campaign, step)
    message = OutreachMessage(
        campaign_id=campaign.id,
        restaurant_id=campaign.restaurant_id,
        direction="outbound",
        status="draft",
        sender_email=current_app.config["EMAIL_FROM_SALES"],
        recipient_email=campaign.recipient_email,
        subject=rendered["subject"],
        body_text=rendered["body_text"],
        sequence_step=step,
        template_key=rendered["template_key"],
        due_at=campaign.next_follow_up_at,
    )
    campaign.status = "drafting"
    db.session.add(message)
    if commit:
        db.session.commit()
    return message


def send_outreach_message(message):
    if is_suppressed(message.recipient_email):
        message.status = "blocked"
        message.error = "This email address has opted out."
        db.session.commit()
        return {"success": False, "provider": None, "message_id": None, "error": message.error}
    rendered = render_template("emails/outreach_message.html", message=message)
    result = resend_client.send_email(
        to=message.recipient_email,
        subject=message.subject,
        html=rendered,
        text=message.body_text,
        from_email=current_app.config["EMAIL_FROM_SALES"],
        reply_to=current_app.config["EMAIL_REPLY_TO_SALES"],
        tags=[{"name": "outreach_id", "value": str(message.id)}],
    )
    message.provider = result["provider"]
    message.provider_message_id = result["message_id"]
    message.error = result["error"]
    message.status = "sent" if result["success"] else "failed"
    message.sent_at = utc_now() if result["success"] else None
    message.reviewed = True if result["success"] else message.reviewed
    if result["success"] and message.campaign:
        campaign = message.campaign
        campaign.current_step = max(campaign.current_step, message.sequence_step or 0)
        campaign.last_sent_at = message.sent_at
        campaign.status = "active" if campaign.current_step < 4 else "closed"
        campaign.paused = False
        campaign.next_follow_up_at = (
            message.sent_at + timedelta(days=followup_days_for_step(campaign.current_step))
            if campaign.current_step < 4
            else None
        )
    db.session.commit()
    if result["success"]:
        loops_client.create_or_update_contact(
            message.recipient_email,
            {"source": "appertivo-outreach", "restaurantName": message.restaurant.name if message.restaurant else ""},
        )
        loops_client.send_event(message.recipient_email, "founderOutreachSent", {"outreachId": str(message.id)})
    return result


def _value(item, key, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def receive_resend_email(payload, headers):
    secret = current_app.config.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        raise ValueError("RESEND_WEBHOOK_SECRET is not configured.")
    resend.Webhooks.verify({"payload": payload, "headers": headers, "webhook_secret": secret})

    event = current_app.json.loads(payload)
    if event.get("type") != "email.received":
        return None
    data = event["data"]
    if OutreachMessage.query.filter_by(external_email_id=data["email_id"]).first():
        return None

    resend.api_key = current_app.config["RESEND_API_KEY"]
    received = resend.Emails.Receiving.get(data["email_id"])
    sender = data.get("from", "")
    recipients = [normalize_email(item) for item in data.get("to", [])]
    restaurant = Restaurant.query.filter(db.func.lower(Restaurant.contact_email) == sender.lower()).first()
    campaign = OutreachCampaign.query.filter_by(recipient_email=normalize_email(sender)).order_by(
        OutreachCampaign.updated_at.desc()
    ).first()
    body_text = _value(received, "text", "") or ""
    received_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    if normalize_email(current_app.config["EMAIL_FROM_SPECIALS"]) in recipients:
        submission = create_raw_submission(
            source_channel="email",
            restaurant_id=restaurant.id if restaurant else (campaign.restaurant_id if campaign else None),
            raw_text=body_text or data.get("subject", "Email special submission"),
            sender_email=sender,
            source_url=f"resend:{data['email_id']}",
        )
        generate_draft_from_submission(submission.id)
        if campaign:
            campaign.status = "special_received"
            campaign.paused = True
            loops_client.send_event(campaign.recipient_email, "restaurantSpecialReceived", {"outreachId": str(campaign.id)})
            db.session.commit()
        return submission
    message = OutreachMessage(
        campaign_id=campaign.id if campaign else None,
        restaurant_id=restaurant.id if restaurant else None,
        direction="inbound",
        status="received",
        sender_email=sender,
        recipient_email=", ".join(data.get("to", [])),
        subject=data.get("subject", ""),
        body_text=body_text,
        provider="resend",
        external_email_id=data["email_id"],
        in_reply_to=data.get("message_id"),
        received_at=received_at,
    )
    if campaign:
        message.restaurant_id = campaign.restaurant_id
        campaign.status = "replied"
        campaign.paused = True
        campaign.next_follow_up_at = None
    if OPT_OUT_RE.search(body_text or ""):
        suppress_email(sender, reason="opt_out", source="inbound_reply")
        message.status = "opted_out"
        if campaign:
            campaign.status = "opted_out"
        loops_client.send_event(normalize_email(sender), "restaurantOutreachOptedOut", {"source": "inbound_reply"})
    elif campaign:
        loops_client.send_event(campaign.recipient_email, "founderOutreachReplied", {"outreachId": str(campaign.id)})
    db.session.add(message)
    db.session.commit()
    return message
