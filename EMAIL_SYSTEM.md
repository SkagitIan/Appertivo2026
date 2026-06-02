# Appertivo Email System

## Provider Roles

- Resend sends transactional email: sign-in links, verification, signup confirmations,
  app notifications, special confirmations, and system notices.
- Loops stores marketing contacts and receives lifecycle or outreach events. Campaigns,
  sequences, and newsletters are configured later.
- `specials@appertivo.com` is the monitored restaurant-specials inbox.
- `ian@appertivo.com` is the founder sales sender.
- `noreply@appertivo.com` is the system sender.

Inbound parsing, Resend webhooks, newsletter sends, unsubscribe management, and campaign
reporting are future extension points. They are not implemented yet.

## Environment

Copy the email settings from `.env.example` into the deployment environment:

```text
RESEND_API_KEY=
LOOPS_API_KEY=
EMAIL_FROM_NOREPLY=noreply@appertivo.com
EMAIL_FROM_SPECIALS=specials@appertivo.com
EMAIL_FROM_SALES=ian@appertivo.com
EMAIL_REPLY_TO_SPECIALS=specials@appertivo.com
EMAIL_REPLY_TO_SALES=ian@appertivo.com
APP_BASE_URL=https://appertivo.com
EMAIL_TEST_ENABLED=0
EMAIL_TEST_RECIPIENT=ian.larsen.1976@gmail.com
RESEND_WEBHOOK_SECRET=
OPENAI_API_KEY=
OPENAI_OUTREACH_MODEL=gpt-5.4-mini
```

Verify `appertivo.com` in Resend before production sends. Provision monitored inboxes
separately from this application.

## Send Transactional Email

Use a purpose-specific helper where one exists:

```python
from email_system.email_service import send_special_received_email

result = send_special_received_email(
    to="owner@example.com",
    restaurant_name="Example Cafe",
    special_title="Friday Fish Tacos",
)
```

Use `send_transactional_email()` for a new system message. It returns:

```python
{
    "success": True,
    "provider": "resend",
    "message_id": "...",
    "error": None,
}
```

Failures are logged and returned without crashing the caller.

## Send Loops Data

```python
from email_system.email_service import (
    create_or_update_marketing_contact,
    send_marketing_event,
)

create_or_update_marketing_contact("owner@example.com", {"source": "restaurant-lead"})
send_marketing_event("owner@example.com", "restaurantLeadCreated", {"city": "Anacortes"})
```

## Add A Template

1. Add `templates/emails/<name>.html` extending `emails/base.html`.
2. Add `templates/emails/<name>.txt` extending `emails/base.txt`.
3. Add a subject and a focused helper in `email_system/email_service.py`.
4. Add rendering and wrapper tests.

## Sender Selection

| Purpose | Sender | Reply-to |
| --- | --- | --- |
| Sign-in, verification, signup, notices | `EMAIL_FROM_NOREPLY` | None |
| Restaurant specials and onboarding | `EMAIL_FROM_SPECIALS` | `EMAIL_REPLY_TO_SPECIALS` |
| Founder sales outreach | `EMAIL_FROM_SALES` | `EMAIL_REPLY_TO_SALES` |

## Test Sending

Test sends are disabled by default. Enable them only in a development environment:

```bat
set EMAIL_TEST_ENABLED=1
flask --app app email-test --to ian@example.com --template magic_link
```

Send all system templates to the configured review recipient:

```bat
set EMAIL_TEST_ENABLED=1
flask --app app email-test-all
```

The same batch is available at `/admin/email-tools` and through:

```bat
python scripts/send_test_emails.py
```

## Outreach Inbox

`/admin/outreach` stores reviewed founder outreach and received replies in the local
database. Outbound free-form messages send through Resend from `EMAIL_FROM_SALES`.
After a successful send, the app updates the Loops marketing contact and emits a
`founderOutreachSent` event for later automation.

The message editor can request a draft from the OpenAI Responses API using restaurant
context. Drafts are never sent automatically.

Loops is not a mailbox provider. Inbound replies are received through Resend:

1. Configure the receiving domain in Resend.
2. Add an `email.received` webhook pointing to `/api/webhooks/resend`.
3. Set the webhook signing secret as `RESEND_WEBHOOK_SECRET`.

The webhook signature is verified before a received email is stored. The inbox supports
archive state, free-form tags, and follow-up flags.
