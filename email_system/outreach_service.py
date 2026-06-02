import logging
from datetime import datetime

import resend
from flask import current_app, render_template

from email_system import loops_client, resend_client
from models import OutreachMessage, Restaurant, db, utc_now


logger = logging.getLogger(__name__)


def send_outreach_message(message):
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
    restaurant = Restaurant.query.filter(db.func.lower(Restaurant.contact_email) == sender.lower()).first()
    message = OutreachMessage(
        restaurant_id=restaurant.id if restaurant else None,
        direction="inbound",
        status="received",
        sender_email=sender,
        recipient_email=", ".join(data.get("to", [])),
        subject=data.get("subject", ""),
        body_text=_value(received, "text", "") or "",
        provider="resend",
        external_email_id=data["email_id"],
        in_reply_to=data.get("message_id"),
        received_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")).replace(tzinfo=None),
    )
    db.session.add(message)
    db.session.commit()
    return message
