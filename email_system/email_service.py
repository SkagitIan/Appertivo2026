from flask import current_app, render_template

from email_system import loops_client, resend_client


SUBJECTS = {
    "magic_link": "Your Appertivo sign-in link",
    "email_verification": "Verify your Appertivo email",
    "user_signup": "Welcome to Appertivo",
    "notification": "Appertivo notification",
    "special_received": "We received your special",
    "restaurant_welcome": "Welcome to Appertivo",
    "sales_outreach": "Get your restaurant special in front of local diners",
    "diner_digest": "What's good today in Skagit Valley",
}


def render_email_template(template_name, context=None):
    template_context = {
        "app_base_url": current_app.config.get("APP_BASE_URL", ""),
        **(context or {}),
    }
    return {
        "html": render_template(f"emails/{template_name}.html", **template_context),
        "text": render_template(f"emails/{template_name}.txt", **template_context),
    }


def send_rendered_email(to, subject, html, text, from_email=None, reply_to=None, tags=None):
    return resend_client.send_email(
        to=to,
        subject=subject,
        html=html,
        text=text,
        from_email=from_email or current_app.config["EMAIL_FROM_NOREPLY"],
        reply_to=reply_to,
        tags=tags,
    )


def send_transactional_email(
    to,
    subject,
    template_name,
    context=None,
    from_email=None,
    reply_to=None,
    tags=None,
):
    rendered = render_email_template(template_name, context)
    return send_rendered_email(
        to=to,
        subject=subject,
        html=rendered["html"],
        text=rendered["text"],
        from_email=from_email,
        reply_to=reply_to,
        tags=tags,
    )


def send_magic_link_email(to, magic_link_url):
    return send_transactional_email(to, SUBJECTS["magic_link"], "magic_link", {"magic_link_url": magic_link_url})


def send_email_verification(to, verification_url):
    return send_transactional_email(
        to, SUBJECTS["email_verification"], "email_verification", {"verification_url": verification_url}
    )


def send_user_signup_email(to, user_name=None):
    return send_transactional_email(to, SUBJECTS["user_signup"], "user_signup", {"user_name": user_name})


def send_notification_email(to, subject, message):
    return send_transactional_email(to, subject, "notification", {"message": message})


def send_special_received_email(to, restaurant_name=None, special_title=None, approval_url=None):
    return send_transactional_email(
        to,
        SUBJECTS["special_received"],
        "special_received",
        {"restaurant_name": restaurant_name, "special_title": special_title, "approval_url": approval_url},
        from_email=current_app.config["EMAIL_FROM_SPECIALS"],
        reply_to=current_app.config["EMAIL_REPLY_TO_SPECIALS"],
    )


def send_restaurant_welcome_email(to, restaurant_name=None):
    return send_transactional_email(
        to,
        SUBJECTS["restaurant_welcome"],
        "restaurant_welcome",
        {"restaurant_name": restaurant_name},
        from_email=current_app.config["EMAIL_FROM_SPECIALS"],
        reply_to=current_app.config["EMAIL_REPLY_TO_SPECIALS"],
    )


def send_sales_outreach_email(to, restaurant_name=None, contact_name=None, custom_message=None):
    return send_transactional_email(
        to,
        SUBJECTS["sales_outreach"],
        "sales_outreach",
        {
            "restaurant_name": restaurant_name,
            "contact_name": contact_name,
            "custom_message": custom_message,
            "show_unsubscribe_placeholder": True,
        },
        from_email=current_app.config["EMAIL_FROM_SALES"],
        reply_to=current_app.config["EMAIL_REPLY_TO_SALES"],
    )


def create_or_update_marketing_contact(email, properties=None):
    return loops_client.create_or_update_contact(email, properties)


def send_marketing_event(email, event_name, properties=None):
    return loops_client.send_event(email, event_name, properties)


def send_test_email(to, template_name):
    base_url = current_app.config["APP_BASE_URL"]
    senders = {
        "magic_link": lambda: send_magic_link_email(to, f"{base_url}/test-sign-in"),
        "email_verification": lambda: send_email_verification(to, f"{base_url}/test-verify"),
        "user_signup": lambda: send_user_signup_email(to, "Test User"),
        "notification": lambda: send_notification_email(
            to, SUBJECTS["notification"], "This is an Appertivo email system test."
        ),
        "special_received": lambda: send_special_received_email(to, "Example Cafe", "Friday Fish Tacos"),
        "restaurant_welcome": lambda: send_restaurant_welcome_email(to, "Example Cafe"),
        "sales_outreach": lambda: send_sales_outreach_email(
            to,
            "Example Cafe",
            "Restaurant Owner",
            "We would like to help share your specials with local diners.",
        ),
        "diner_digest": lambda: send_transactional_email(
            to,
            SUBJECTS["diner_digest"],
            "diner_digest",
            {
                "specials": [],
                "unsubscribe_url": f"{base_url}/unsubscribe?email=test@example.com&token=test",
            },
            from_email=current_app.config["EMAIL_FROM_SPECIALS"],
            reply_to=current_app.config["EMAIL_REPLY_TO_SPECIALS"],
        ),
    }
    return senders[template_name]()


def send_all_test_emails(to):
    return {template_name: send_test_email(to, template_name) for template_name in SUBJECTS}


def render_test_email(template_name):
    base_url = current_app.config["APP_BASE_URL"]
    return render_email_template(
        template_name,
        {
            "magic_link_url": f"{base_url}/test-sign-in",
            "verification_url": f"{base_url}/test-verify",
            "user_name": "Test User",
            "message": "This is an Appertivo email system test.",
            "restaurant_name": "Example Cafe",
            "special_title": "Friday Fish Tacos",
            "contact_name": "Restaurant Owner",
            "custom_message": "We would like to help share your specials with local diners.",
            "show_unsubscribe_placeholder": template_name in {"sales_outreach", "diner_digest"},
            "specials": [],
            "preview_note": "Digest preview",
        },
    )
