import hashlib
import hmac
import os
import re
import secrets
from datetime import UTC, datetime, timedelta, time
from functools import wraps
from types import SimpleNamespace
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import click
import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    Response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_migrate import Migrate
from sqlalchemy import func, or_
from werkzeug.exceptions import BadRequest

from email_system.email_service import send_notification_email, send_special_received_email
from markets import SKAGIT_VALLEY, normalize_location, resolve_market
from models import (
    DistributionLog,
    OutreachCampaign,
    OutreachMessage,
    OutreachTemplate,
    Restaurant,
    RestaurantLead,
    RawSpecialSubmission,
    Special,
    SpecialDraft,
    SpecialMetric,
    Subscriber,
    db,
    utc_now,
)
from services import parse_special_text, slugify
from special_pipeline import (
    approve_draft,
    create_raw_submission,
    enhance_draft_from_submission,
    generate_draft_from_submission,
    publish_draft,
    reject_draft,
    schedule_first_special_followup_if_needed,
)
from special_taxonomy import (
    CUISINE_TAG_KEYS,
    feed_tag_options,
    infer_restaurant_cuisine_tags,
    normalize_tag_key,
    parse_tag_text,
    primary_tag_from,
    serialize_tag_keys,
    tag_label,
    tag_labels,
    tag_options,
)
from storage import UploadError, save_special_photo


load_dotenv()
LOCAL_TZ = ZoneInfo("America/Los_Angeles")
METRIC_TYPES = {"view", "directions", "call", "website", "share", "save"}
CHANNELS = ["facebook_page", "facebook_group", "instagram", "email", "other"]
LEAD_STATUSES = {"new", "contacted", "converted", "closed"}
PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
CITY_ALIASES = {
    "Sedro Woolley": "Sedro-Woolley",
}


def normalize_database_url(database_url):
    """Use the installed Psycopg 3 driver for provider-style PostgreSQL URLs."""
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
    ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "admin"),
    SQLALCHEMY_DATABASE_URI=normalize_database_url(os.environ.get("DATABASE_URL", "sqlite:///appertivo.db")),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=int(os.environ.get("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)),
    UPLOAD_ROOT=os.environ.get("UPLOAD_ROOT", str(Path(app.instance_path) / "uploads")),
    R2_ENDPOINT=os.environ.get("R2_ENDPOINT"),
    R2_BUCKET=os.environ.get("R2_BUCKET"),
    R2_ACCESS_KEY_ID=os.environ.get("R2_ACCESS_KEY_ID"),
    R2_SECRET_ACCESS_KEY=os.environ.get("R2_SECRET_ACCESS_KEY"),
    R2_PUBLIC_BASE_URL=os.environ.get("R2_PUBLIC_BASE_URL"),
    RESEND_API_KEY=os.environ.get("RESEND_API_KEY"),
    LOOPS_API_KEY=os.environ.get("LOOPS_API_KEY"),
    EMAIL_FROM_NOREPLY=os.environ.get("EMAIL_FROM_NOREPLY", "noreply@appertivo.com"),
    EMAIL_FROM_SPECIALS=os.environ.get("EMAIL_FROM_SPECIALS", "specials@appertivo.com"),
    EMAIL_FROM_SALES=os.environ.get("EMAIL_FROM_SALES", "ian@appertivo.com"),
    EMAIL_REPLY_TO_SPECIALS=os.environ.get("EMAIL_REPLY_TO_SPECIALS", "specials@appertivo.com"),
    EMAIL_REPLY_TO_SALES=os.environ.get("EMAIL_REPLY_TO_SALES", "ian@appertivo.com"),
    ADMIN_NOTIFICATION_EMAIL=os.environ.get("ADMIN_NOTIFICATION_EMAIL", "ian@appertivo.com"),
    APP_BASE_URL=os.environ.get("APP_BASE_URL", "http://127.0.0.1:5000"),
    EMAIL_TEST_ENABLED=os.environ.get("EMAIL_TEST_ENABLED") == "1",
    EMAIL_TEST_RECIPIENT=os.environ.get("EMAIL_TEST_RECIPIENT", "ian.larsen.1976@gmail.com"),
    EMAIL_CAPTURE_PATH=os.environ.get("EMAIL_CAPTURE_PATH"),
    RESEND_WEBHOOK_SECRET=os.environ.get("RESEND_WEBHOOK_SECRET"),
    OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY"),
    OPENAI_OUTREACH_MODEL=os.environ.get("OPENAI_OUTREACH_MODEL", "gpt-5.4-mini"),
    OPENAI_SPECIAL_MODEL=os.environ.get(
        "OPENAI_SPECIAL_MODEL", os.environ.get("OPENAI_OUTREACH_MODEL", "gpt-5.4-mini")
    ),
    OUTREACH_DAILY_SEND_CAP=int(os.environ.get("OUTREACH_DAILY_SEND_CAP", 20)),
    OUTREACH_FOLLOWUP_DAYS=os.environ.get("OUTREACH_FOLLOWUP_DAYS", "3,4,5"),
    OUTREACH_REQUIRE_APPROVAL=os.environ.get("OUTREACH_REQUIRE_APPROVAL", "1") == "1",
    GOOGLE_PLACES_API_KEY=os.environ.get("GOOGLE_PLACES_API_KEY"),
    CLOUDINARY_CLOUD_NAME=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    CLOUDINARY_API_KEY=os.environ.get("CLOUDINARY_API_KEY"),
    CLOUDINARY_API_SECRET=os.environ.get("CLOUDINARY_API_SECRET"),
    CLOUDINARY_FOLDER=os.environ.get("CLOUDINARY_FOLDER", "appertivo/specials"),
    SPECIAL_WEBHOOK_TEST_ENABLED=os.environ.get("SPECIAL_WEBHOOK_TEST_ENABLED") == "1",
    SITEMAP_CACHE_SECONDS=int(os.environ.get("SITEMAP_CACHE_SECONDS", 4 * 60 * 60)),
)
db.init_app(app)
migrate = Migrate(app, db)
SITEMAP_CACHE = {"generated_at": None, "body": None}


@app.cli.command("seed-demo-specials")
def seed_demo_specials_command():
    """Add or refresh launch-preview specials for the current market."""
    from demo_data import seed_demo_specials

    seeded, skipped = seed_demo_specials(db.session)
    click.echo(f"Seeded {seeded} demo specials.")
    if skipped:
        click.echo(f"Skipped {len(skipped)} missing restaurants: {', '.join(skipped)}")


@app.cli.command("seed-launch-data")
def seed_launch_data_command():
    """Seed launch restaurants once and refresh labeled preview specials."""
    from seed import seed_database

    result = seed_database(reset=False)
    click.echo(f"Restaurants: {result['restaurants']}.")
    click.echo(f"Excluded chain locations: {result['excluded_chains']}.")
    click.echo(f"Launch-preview specials: {result['demo_specials']}.")
    if result["demo_skipped"]:
        click.echo(f"Skipped demo restaurants: {', '.join(result['demo_skipped'])}")


@app.cli.command("email-test")
@click.option("--to", "to_email", required=True, help="Recipient email address.")
@click.option(
    "--template",
    "template_name",
    default="magic_link",
    show_default=True,
    type=click.Choice(
        [
            "magic_link",
            "email_verification",
            "user_signup",
            "notification",
            "special_received",
            "first_special_followup",
            "restaurant_welcome",
            "sales_outreach",
            "diner_digest",
        ]
    ),
)
def email_test(to_email, template_name):
    """Send a development-only email template preview through Resend."""
    if not app.config["EMAIL_TEST_ENABLED"]:
        raise click.ClickException("Email test sending is disabled. Set EMAIL_TEST_ENABLED=1.")

    from email_system.email_service import send_test_email

    result = send_test_email(to_email, template_name)
    if not result["success"]:
        raise click.ClickException(result["error"])
    click.echo(f"Sent {template_name} email via {result['provider']}: {result['message_id']}")


@app.cli.command("email-test-all")
@click.option("--to", "to_email", default=None, help="Recipient email address.")
def email_test_all(to_email):
    """Send every email template to one development recipient."""
    if not app.config["EMAIL_TEST_ENABLED"]:
        raise click.ClickException("Email test sending is disabled. Set EMAIL_TEST_ENABLED=1.")

    from email_system.email_service import send_all_test_emails

    recipient = to_email or app.config["EMAIL_TEST_RECIPIENT"]
    results = send_all_test_emails(recipient)
    for template_name, result in results.items():
        status = "sent" if result["success"] else f"failed: {result['error']}"
        click.echo(f"{template_name}: {status}")
    if not all(result["success"] for result in results.values()):
        raise click.ClickException("One or more template sends failed.")


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = csrf_token


def static_asset_version(filename):
    path = Path(app.static_folder) / filename
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return "1"


app.jinja_env.globals["static_asset_version"] = static_asset_version


def require_csrf():
    expected = session.get("csrf_token", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, "Invalid CSRF token.")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def protect_mutations():
    if request.method == "POST" and request.endpoint not in {
        "admin_login",
        "resend_webhook",
        "email_special_webhook",
        "sms_special_webhook",
    }:
        require_csrf()


@app.get("/health")
def health():
    return jsonify(status="ok")


def local_to_utc(value):
    return value.replace(tzinfo=LOCAL_TZ).astimezone(UTC).replace(tzinfo=None)


def parse_local_datetime(date_value, time_value=None, default_time=None):
    day = datetime.strptime(date_value, "%Y-%m-%d").date()
    parsed_time = datetime.strptime(time_value, "%H:%M").time() if time_value else default_time
    return local_to_utc(datetime.combine(day, parsed_time)) if parsed_time else None


def active_specials_query():
    now = utc_now()
    return Special.query.join(Restaurant).filter(
        Special.status == "published",
        Restaurant.catalog_status == "included",
        or_(Special.starts_at.is_(None), Special.starts_at <= now),
        or_(Special.expires_at.is_(None), Special.expires_at >= now),
    )


def special_tag_filter(tag_key):
    return or_(
        Special.primary_tag == tag_key,
        Special.tag_keys == tag_key,
        Special.tag_keys.ilike(f"{tag_key},%"),
        Special.tag_keys.ilike(f"%,{tag_key},%"),
        Special.tag_keys.ilike(f"%,{tag_key}"),
    )


def selected_tag_key(value):
    key = normalize_tag_key(value)
    return key if tag_label(key) else ""


def canonical_market_city(city):
    normalized = normalize_location(city or "")
    city_lookup = {normalize_location(value): value for value in SKAGIT_VALLEY["cities"]}
    alias_lookup = {normalize_location(alias): canonical for alias, canonical in CITY_ALIASES.items()}
    return city_lookup.get(normalized) or alias_lookup.get(normalized) or (city or "").strip()


def market_city_variants(city):
    canonical = canonical_market_city(city)
    variants = {canonical}
    variants.update(alias for alias, target in CITY_ALIASES.items() if target == canonical)
    return [value for value in variants if value]


def market_city_filter(market):
    cities = list((market or SKAGIT_VALLEY)["cities"])
    variants = set(cities)
    for city in cities:
        variants.update(market_city_variants(city))
    return or_(*(Restaurant.city.ilike(city) for city in sorted(variants)))


def city_hub_slug(city):
    return slugify(canonical_market_city(city))


def city_from_hub_slug(slug):
    lookup = {city_hub_slug(city): city for city in SKAGIT_VALLEY["cities"]}
    return lookup.get(slugify(slug))


def restaurant_search_filter(search_term):
    pattern = f"%{search_term}%"
    return or_(
        Restaurant.name.ilike(pattern),
        Restaurant.city.ilike(pattern),
        Restaurant.full_address.ilike(pattern),
        Restaurant.street.ilike(pattern),
        Restaurant.category.ilike(pattern),
        Restaurant.subtypes.ilike(pattern),
        Restaurant.cuisine_tags.ilike(pattern),
    )


def restaurant_submit_result(restaurant, status="included"):
    return {
        "id": restaurant.id if restaurant else None,
        "name": restaurant.name if restaurant else "",
        "city": restaurant.city if restaurant else "",
        "address": restaurant.address if restaurant else "",
        "status": status,
    }


def unique_restaurant_slug(name, current_id=None):
    base = slugify(name) or "restaurant"
    candidate = base
    counter = 2
    while True:
        query = Restaurant.query.filter_by(slug=candidate)
        if current_id:
            query = query.filter(Restaurant.id != current_id)
        if not query.first():
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1


def google_places_submit_suggestions(term, limit=5):
    api_key = app.config.get("GOOGLE_PLACES_API_KEY")
    if not api_key or len(term) < 3:
        return []
    payload = {
        "textQuery": f"{term} restaurant in Skagit Valley Washington",
        "includedType": "restaurant",
        "maxResultCount": limit,
        "locationBias": {
            "rectangle": {
                "low": {"latitude": 48.24, "longitude": -122.72},
                "high": {"latitude": 48.7, "longitude": -121.95},
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress",
    }
    try:
        response = requests.post(PLACES_TEXT_SEARCH_URL, json=payload, headers=headers, timeout=4)
        response.raise_for_status()
    except requests.RequestException:
        return []
    suggestions = []
    for place in response.json().get("places", []):
        name = ((place.get("displayName") or {}).get("text") or "").strip()
        if not name:
            continue
        suggestions.append(
            {
                "id": None,
                "name": name,
                "city": "",
                "address": place.get("formattedAddress", ""),
                "status": "coming_soon",
            }
        )
    return suggestions


def google_places_restaurant_lookup(term, limit=6):
    api_key = app.config.get("GOOGLE_PLACES_API_KEY")
    if not api_key or len(term) < 3:
        return []
    payload = {
        "textQuery": f"{term} restaurant in Skagit Valley Washington",
        "includedType": "restaurant",
        "maxResultCount": limit,
        "locationBias": {
            "rectangle": {
                "low": {"latitude": 48.24, "longitude": -122.72},
                "high": {"latitude": 48.7, "longitude": -121.95},
            }
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri",
    }
    try:
        response = requests.post(PLACES_TEXT_SEARCH_URL, json=payload, headers=headers, timeout=4)
        response.raise_for_status()
    except requests.RequestException:
        return []
    results = []
    for place in response.json().get("places", []):
        name = ((place.get("displayName") or {}).get("text") or "").strip()
        if not name:
            continue
        address = place.get("formattedAddress", "")
        city = canonical_market_city(city_from_address(address))
        status = "google_place" if city in SKAGIT_VALLEY["cities"] else "coming_soon"
        results.append(
            {
                "id": None,
                "place_id": place.get("id"),
                "name": name,
                "city": city,
                "address": address,
                "phone": place.get("nationalPhoneNumber", ""),
                "website": place.get("websiteUri", ""),
                "status": status,
            }
        )
    return results


def subscribe(email, city=None, location=None, favorite_tag=None):
    subscriber = Subscriber.query.filter_by(email=email).first()
    if not subscriber:
        subscriber = Subscriber(
            email=email,
            city=city or None,
            location=location or None,
            favorite_tags=favorite_tag or None,
        )
        db.session.add(subscriber)
    else:
        if city:
            subscriber.city = city
        if location:
            subscriber.location = location
        subscriber.is_subscribed = True
        subscriber.unsubscribed_at = None
    if favorite_tag:
        tags = {tag.strip() for tag in (subscriber.favorite_tags or "").split(",") if tag.strip()}
        tags.add(favorite_tag)
        subscriber.favorite_tags = ",".join(sorted(tags))
    db.session.commit()


def city_from_address(address):
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    if len(parts) >= 3:
        return parts[-3]
    if len(parts) >= 2:
        return parts[-2]
    return ""


def restaurant_from_get_started_form():
    restaurant_id = request.form.get("restaurant_id", type=int)
    email = request.form["sender_email"].strip().lower()
    if restaurant_id:
        restaurant = included_restaurant_or_404(restaurant_id)
        if email and not restaurant.contact_email:
            restaurant.contact_email = email
        return restaurant
    place_id = request.form.get("place_id", "").strip() or None
    submitted_city = canonical_market_city(
        request.form.get("restaurant_city", "").strip()
        or city_from_address(request.form.get("restaurant_address", ""))
    )
    if place_id and submitted_city not in SKAGIT_VALLEY["cities"]:
        abort(400, "Appertivo is coming soon for that restaurant.")
    restaurant = Restaurant.query.filter_by(place_id=place_id).first() if place_id else None
    if restaurant:
        if restaurant.catalog_status != "included":
            restaurant.catalog_status = "included"
            restaurant.catalog_reason = "restaurant submitted first special"
            restaurant.catalog_reviewed_at = utc_now()
        if email and not restaurant.contact_email:
            restaurant.contact_email = email
        return restaurant
    name = request.form.get("restaurant_name", "").strip()
    if not name:
        abort(400, "Choose or enter your restaurant.")
    restaurant = Restaurant(
        name=name,
        slug=unique_restaurant_slug(name),
        city=submitted_city or "Skagit Valley",
        full_address=request.form.get("restaurant_address", "").strip(),
        contact_email=email,
        phone=request.form.get("restaurant_phone", "").strip(),
        site=request.form.get("restaurant_website", "").strip(),
        place_id=place_id,
        catalog_status="included",
        catalog_reason="restaurant submitted first special",
        catalog_reviewed_at=utc_now(),
    )
    db.session.add(restaurant)
    db.session.flush()
    return restaurant


def unsubscribe_signature(email):
    return hmac.new(
        app.config["SECRET_KEY"].encode("utf-8"),
        email.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def unsubscribe_url_for_email(email):
    normalized_email = email.strip().lower()
    token = unsubscribe_signature(normalized_email)
    return url_for("unsubscribe", email=normalized_email, token=token, _external=True)


def valid_unsubscribe_token(email, token):
    return hmac.compare_digest(unsubscribe_signature(email), token or "")


def skagit_specials_query():
    return active_specials_query().filter(market_city_filter(SKAGIT_VALLEY))


def skagit_subscribers_query():
    location_filters = [Subscriber.location.ilike("%Skagit%")]
    location_filters.extend(Subscriber.location.ilike(f"%{city}%") for city in SKAGIT_VALLEY["cities"])
    city_filters = [Subscriber.city.ilike(city) for city in SKAGIT_VALLEY["cities"]]
    for alias in CITY_ALIASES:
        city_filters.append(Subscriber.city.ilike(alias))
    return Subscriber.query.filter(
        Subscriber.is_subscribed.is_(True),
        or_(*city_filters, *location_filters),
    )


def digest_subject():
    return "What's good today in Skagit Valley"


def digest_special_rows(specials):
    rows = []
    for special in specials:
        rows.append(
            {
                "title": special.title,
                "description": special.description,
                "price": special.price,
                "availability_text": special.availability_text,
                "restaurant_name": special.restaurant.name,
                "city": special.restaurant.city,
                "url": url_for("special_detail", public_id=special.public_id, channel="email_digest", _external=True),
            }
        )
    return rows


def build_diner_digest(unsubscribe_url=None):
    specials = skagit_specials_query().order_by(Special.published_at.desc(), Special.created_at.desc()).all()
    context = {
        "specials": digest_special_rows(specials),
        "unsubscribe_url": unsubscribe_url
        or url_for("unsubscribe", email="preview@example.com", token="preview", _external=True),
    }
    return {
        "subject": digest_subject(),
        "html": render_template("emails/diner_digest.html", **context),
        "text": render_template("emails/diner_digest.txt", **context),
        "specials": specials,
        "recipient_count": skagit_subscribers_query().count(),
    }


def send_diner_digest_to(email):
    from email_system.email_service import send_rendered_email

    digest = build_diner_digest(unsubscribe_url_for_email(email))
    return send_rendered_email(
        to=email,
        subject=digest["subject"],
        html=digest["html"],
        text=digest["text"],
        from_email=app.config["EMAIL_FROM_SPECIALS"],
        reply_to=app.config["EMAIL_REPLY_TO_SPECIALS"],
        tags=[{"name": "channel", "value": "email_digest"}],
    )


def record_digest_distribution(specials):
    for special in specials:
        db.session.add(DistributionLog(special_id=special.id, channel="email_digest", note="Manual diner digest"))
    db.session.commit()


def record_metric(special, event_type, channel=None):
    if event_type not in METRIC_TYPES:
        abort(404)
    db.session.add(SpecialMetric(special_id=special.id, event_type=event_type, channel=channel or None))
    db.session.commit()


def metric_counts(special_id=None):
    query = db.session.query(SpecialMetric.event_type, func.count(SpecialMetric.id))
    if special_id:
        query = query.filter(SpecialMetric.special_id == special_id)
    return dict(query.group_by(SpecialMetric.event_type).all())


def special_date_value(special):
    moment = special.starts_at or special.expires_at or utc_now()
    return moment.replace(tzinfo=UTC).astimezone(LOCAL_TZ).strftime("%Y-%m-%d")


app.jinja_env.globals["special_date_value"] = special_date_value


def special_time_value(moment):
    if not moment:
        return ""
    return moment.replace(tzinfo=UTC).astimezone(LOCAL_TZ).strftime("%H:%M")


app.jinja_env.globals["special_time_value"] = special_time_value


def smart_image_url(url, width=900, height=620):
    if not url or "/upload/" not in url or "res.cloudinary.com" not in url:
        return url
    transformation = f"c_fill,g_auto,w_{int(width)},h_{int(height)}/e_improve/q_auto/f_auto"
    return url.replace("/upload/", f"/upload/{transformation}/", 1)


app.jinja_env.globals["smart_image_url"] = smart_image_url


def local_iso(value):
    if not value:
        return ""
    return value.replace(tzinfo=UTC).astimezone(LOCAL_TZ).isoformat()


def special_timestamp(special):
    return (
        getattr(special, "starts_at", None)
        or getattr(special, "published_at", None)
        or getattr(special, "updated_at", None)
        or getattr(special, "created_at", None)
        or getattr(special, "expires_at", None)
    )


def special_timestamp_iso(special):
    return local_iso(special_timestamp(special))


app.jinja_env.globals["special_timestamp_iso"] = special_timestamp_iso


def clean_schema(value):
    if isinstance(value, dict):
        cleaned = {key: clean_schema(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item not in (None, "", [], {})}
    if isinstance(value, list):
        return [clean_schema(item) for item in value if item not in (None, "", [], {})]
    return value


def parse_price_amount(price):
    match = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", price or "")
    return f"{float(match.group(1)):.2f}" if match else None


def restaurant_schema(restaurant):
    address = None
    if restaurant.address or restaurant.city or restaurant.postal_code:
        address = {
            "@type": "PostalAddress",
            "streetAddress": restaurant.address,
            "addressLocality": restaurant.city,
            "addressRegion": restaurant.us_state or "WA",
            "postalCode": restaurant.postal_code,
            "addressCountry": restaurant.country or "US",
        }
    opening_hours = []
    for day, hours in (restaurant.working_hours or {}).items():
        formatted = format_hours_value(hours)
        if formatted:
            opening_hours.append(f"{day} {formatted}")
    return clean_schema(
        {
            "@context": "https://schema.org",
            "@type": ["Restaurant", "FoodEstablishment"],
            "@id": url_for("restaurant_detail", slug=restaurant.slug, _external=True) + "#restaurant",
            "name": restaurant.name,
            "url": url_for("restaurant_detail", slug=restaurant.slug, _external=True),
            "telephone": restaurant.phone,
            "address": address,
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": restaurant.latitude,
                "longitude": restaurant.longitude,
            }
            if restaurant.latitude is not None and restaurant.longitude is not None
            else None,
            "servesCuisine": tag_labels(restaurant.cuisine_tags) or restaurant.category,
            "sameAs": restaurant.site,
            "aggregateRating": {
                "@type": "AggregateRating",
                "ratingValue": restaurant.rating,
                "reviewCount": restaurant.reviews,
            }
            if restaurant.rating
            else None,
            "openingHours": opening_hours,
        }
    )


def offer_schema(special):
    amount = parse_price_amount(special.price)
    schema = {
        "@type": "Offer",
        "@id": url_for("special_detail", public_id=special.public_id, _external=True) + "#offer",
        "name": special.title,
        "description": special.description,
        "url": url_for("special_detail", public_id=special.public_id, _external=True),
        "validFrom": local_iso(special.starts_at or special.published_at or special.created_at),
        "validThrough": local_iso(special.expires_at),
        "price": amount,
        "priceCurrency": "USD" if amount else None,
        "availability": "https://schema.org/InStock",
        "offeredBy": {
            "@type": "Restaurant",
            "@id": url_for("restaurant_detail", slug=special.restaurant.slug, _external=True) + "#restaurant",
            "name": special.restaurant.name,
        },
        "itemOffered": {
            "@type": "MenuItem",
            "name": special.title,
            "description": special.description,
            "menuAddOn": special.add_on_name,
            "category": special_tag_labels(special),
        },
    }
    pickup_text = " ".join([special.cta_text or "", special.raw_text or "", special.description or ""]).casefold()
    if "pickup" in pickup_text or "order" in pickup_text or "takeout" in pickup_text:
        schema["availableDeliveryMethod"] = "https://schema.org/OnSitePickup"
    return clean_schema(schema)


def restaurant_graph_schema(restaurant, specials):
    return {"@context": "https://schema.org", "@graph": [restaurant_schema(restaurant), *[offer_schema(special) for special in specials]]}


def special_display_date(special):
    moment = special.starts_at or special.expires_at or special.created_at or utc_now()
    local_moment = moment.replace(tzinfo=UTC).astimezone(LOCAL_TZ)
    return local_moment.strftime("%b %d").replace(" 0", " ")


app.jinja_env.globals["special_display_date"] = special_display_date


def special_is_today(special):
    moment = special.starts_at or special.expires_at or special.created_at
    if not moment:
        return False
    local_date = moment.replace(tzinfo=UTC).astimezone(LOCAL_TZ).date()
    return local_date == datetime.now(LOCAL_TZ).date()


app.jinja_env.globals["special_is_today"] = special_is_today


def special_timing_badge(special):
    if special.availability_text:
        return special.availability_text
    if special.recurrence_label:
        return special.recurrence_label
    if special.expires_at and special.expires_at.replace(tzinfo=UTC).astimezone(LOCAL_TZ).date() == datetime.now(LOCAL_TZ).date():
        return "Ends Today"
    if special.starts_at or special.expires_at:
        return special_display_date(special)
    return "All Day"


def special_tag_labels(special):
    labels = tag_labels(getattr(special, "tag_keys", ""))
    primary_label = tag_label(getattr(special, "primary_tag", ""))
    if primary_label and primary_label not in labels:
        labels.insert(0, primary_label)
    return labels[:3]


def saved_special_ids():
    ids = set()
    for special_id in session.get("saved_special_ids", []):
        try:
            ids.add(int(special_id))
        except (TypeError, ValueError):
            continue
    return ids


def is_special_saved(special):
    return special.id in saved_special_ids()


def selected_tag_options(value):
    return set(parse_tag_text(value))


app.jinja_env.globals["special_timing_badge"] = special_timing_badge
app.jinja_env.globals["special_tag_labels"] = special_tag_labels
app.jinja_env.globals["is_special_saved"] = is_special_saved
app.jinja_env.globals["tag_label"] = tag_label
app.jinja_env.globals["tag_labels"] = tag_labels
app.jinja_env.globals["tag_options"] = tag_options
app.jinja_env.globals["feed_tag_options"] = feed_tag_options
app.jinja_env.globals["selected_tag_options"] = selected_tag_options


def format_hours_value(hours):
    if isinstance(hours, list):
        return ", ".join(str(hour).strip() for hour in hours if str(hour).strip())
    if isinstance(hours, tuple):
        return ", ".join(str(hour).strip() for hour in hours if str(hour).strip())
    if isinstance(hours, str):
        value = hours.strip()
        if value.startswith("[") and value.endswith("]"):
            return value.strip("[]").replace("'", "").replace('"', "")
        return value
    return str(hours or "")


app.jinja_env.globals["format_hours_value"] = format_hours_value


def remember_operator_special(special):
    ids = {int(special_id) for special_id in session.get("operator_special_ids", [])}
    ids.add(special.id)
    session["operator_special_ids"] = sorted(ids)


def can_manage_special(special):
    if session.get("admin_authenticated"):
        return True
    return special.id in {int(special_id) for special_id in session.get("operator_special_ids", [])}


app.jinja_env.globals["can_manage_special"] = can_manage_special


def draft_as_preview_special(draft):
    return SimpleNamespace(
        title=draft.title,
        description=draft.description,
        price=draft.price_text,
        value_text=draft.value_text,
        photo_url=draft.image_url,
        restaurant=draft.restaurant or SimpleNamespace(name="Restaurant to be assigned", city=""),
        availability_text=draft.availability_text,
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
        created_at=draft.created_at,
        source="draft",
        public_id=None,
    )


def schedule_window_from_form():
    date_value = request.form["special_date"]
    schedule_option = request.form.get("schedule_option", "today")
    start = parse_local_datetime(date_value, default_time=time(0, 0))
    end_date_value = date_value
    availability_text = None

    if schedule_option == "this_weekend":
        selected_day = datetime.strptime(date_value, "%Y-%m-%d").date()
        days_until_sunday = (6 - selected_day.weekday()) % 7
        weekend_end = selected_day + timedelta(days=days_until_sunday)
        end_date_value = weekend_end.strftime("%Y-%m-%d")
        availability_text = "This weekend"
    elif schedule_option == "till_sold_out":
        availability_text = "Until sold out"
    elif schedule_option == "custom":
        availability_text = request.form.get("availability_text", "").strip() or None

    end = parse_local_datetime(end_date_value, default_time=time(23, 59))
    return start, end, availability_text


def set_special_schedule(special):
    special.starts_at, special.expires_at, availability_text = schedule_window_from_form()
    special.availability_text = availability_text


def optional_int_from_form(name):
    value = request.form.get(name, "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        abort(400, f"{name} must be a number.")


def selected_special_tag_keys_from_form():
    values = request.form.getlist("tag_keys")
    values.extend(parse_tag_text(request.form.get("tag_keys_text", "")))
    return serialize_tag_keys(values)


def set_special_taxonomy_fields(item):
    submitted_tag_values = request.form.getlist("tag_keys")
    submitted_tag_text = request.form.get("tag_keys_text", "").strip()
    tag_input_present = bool(submitted_tag_values or submitted_tag_text or request.form.get("tag_keys_present"))
    tag_keys = selected_special_tag_keys_from_form() if tag_input_present else (item.tag_keys or "")
    if tag_input_present:
        item.tag_keys = tag_keys
    if tag_input_present or request.form.get("primary_tag"):
        item.primary_tag = primary_tag_from(tag_keys.split(","), request.form.get("primary_tag"))
    item.value_text = request.form.get("value_text", "").strip() or None
    item.add_on_name = request.form.get("add_on_name", "").strip() or None
    item.add_on_price = request.form.get("add_on_price", "").strip() or None
    item.add_on_value_text = request.form.get("add_on_value_text", "").strip() or None
    item.featured_rank = optional_int_from_form("featured_rank")


def set_special_recurrence_fields(item):
    item.recurrence_rule = request.form.get("recurrence_rule", "").strip() or None
    item.recurrence_label = request.form.get("recurrence_label", "").strip() or None
    confidence = request.form.get("recurrence_confidence", "").strip().lower()
    item.recurrence_confidence = confidence if confidence in {"high", "medium", "low"} else None


def has_special_taxonomy_overrides():
    if request.form.getlist("tag_keys") or request.form.get("tag_keys_text", "").strip():
        return True
    return any(
        request.form.get(name, "").strip()
        for name in ["primary_tag", "value_text", "add_on_name", "add_on_price", "add_on_value_text", "featured_rank"]
    )


def save_photo_if_present(special):
    upload = request.files.get("photo")
    if upload and upload.filename:
        special.photo_object_key, special.photo_url = save_special_photo(app, upload)


def save_submitted_photo():
    upload = request.files.get("photo")
    if upload and upload.filename:
        return save_special_photo(app, upload)
    return None, None


def structured_draft_from_form(source_channel, restaurant_id, enhance=True):
    image_path, image_url = save_submitted_photo()
    title = request.form["title"].strip()
    description = request.form.get("description", "").strip()
    price = request.form.get("price", "").strip()
    raw_text = request.form.get("raw_text", "").strip() or "\n".join(
        value for value in [title, description, price] if value
    )
    submission = create_raw_submission(
        source_channel=source_channel,
        restaurant_id=restaurant_id,
        raw_text=raw_text,
        raw_image_url=image_url,
        raw_image_path=image_path,
        sender_email=request.form.get("sender_email", "").strip().lower() or None,
    )
    draft = generate_draft_from_submission(submission.id)
    if not enhance:
        draft.title = title
        draft.description = description
        draft.price_text = price or None
        set_special_taxonomy_fields(draft)
    draft.starts_at, draft.expires_at, availability_text = schedule_window_from_form()
    draft.availability_text = availability_text
    set_special_recurrence_fields(draft)
    if enhance and has_special_taxonomy_overrides():
        set_special_taxonomy_fields(draft)
    db.session.commit()
    return draft


def special_from_form(special=None):
    special = special or Special()
    special.restaurant_id = included_restaurant_id_from_form()
    special.title = request.form["title"].strip()
    special.description = request.form.get("description", "").strip()
    special.price = request.form.get("price", "").strip()
    set_special_schedule(special)
    set_special_taxonomy_fields(special)
    special.status = request.form.get("status", "draft")
    special.source = request.form.get("source", "manual")
    special.raw_text = request.form.get("raw_text", "").strip() or None
    set_special_recurrence_fields(special)
    if special.status == "published" and not special.published_at:
        special.published_at = utc_now()
    save_photo_if_present(special)
    return special


def draft_from_form(draft):
    draft.restaurant_id = included_restaurant_id_from_form()
    draft.raw_submission.restaurant_id = draft.restaurant_id
    draft.title = request.form["title"].strip()
    draft.description = request.form.get("description", "").strip()
    draft.price_text = request.form.get("price", "").strip() or None
    draft.starts_at, draft.expires_at, availability_text = schedule_window_from_form()
    draft.availability_text = availability_text
    draft.status = request.form.get("status", draft.status)
    set_special_taxonomy_fields(draft)
    set_special_recurrence_fields(draft)
    image_path, image_url = save_submitted_photo()
    if image_url or image_path:
        draft.image_path = image_path
        draft.image_url = image_url
    return draft


def included_restaurants_query():
    return Restaurant.query.filter_by(catalog_status="included")


def included_restaurant_or_404(restaurant_id):
    return included_restaurants_query().filter_by(id=restaurant_id).first_or_404()


def included_restaurant_id_from_form():
    try:
        restaurant_id = int(request.form["restaurant_id"])
    except (KeyError, ValueError):
        abort(400, "Choose an included restaurant.")
    if not included_restaurants_query().filter_by(id=restaurant_id).first():
        abort(400, "Choose an included restaurant.")
    return restaurant_id


def included_special_or_404(special_id):
    return (
        Special.query.join(Restaurant)
        .filter(Special.id == special_id, Restaurant.catalog_status == "included")
        .first_or_404()
    )


def operational_outreach_messages_query():
    return OutreachMessage.query.outerjoin(Restaurant).filter(
        or_(OutreachMessage.restaurant_id.is_(None), Restaurant.catalog_status == "included")
    )


def operational_outreach_campaigns_query():
    return OutreachCampaign.query.join(Restaurant).filter(Restaurant.catalog_status == "included")


def operational_outreach_campaign_or_404(campaign_id):
    return operational_outreach_campaigns_query().filter(OutreachCampaign.id == campaign_id).first_or_404()


def operational_outreach_message_or_404(message_id):
    return operational_outreach_messages_query().filter(OutreachMessage.id == message_id).first_or_404()


def restaurant_from_form(restaurant=None):
    is_new = restaurant is None
    restaurant = restaurant or Restaurant()
    place_id = request.form.get("place_id", "").strip()
    if is_new and not place_id:
        abort(400, "Choose a Google Places match before adding a restaurant.")
    if place_id:
        duplicate_query = Restaurant.query.filter_by(place_id=place_id)
        if restaurant.id:
            duplicate_query = duplicate_query.filter(Restaurant.id != restaurant.id)
        if duplicate_query.first():
            abort(400, "That Google Places restaurant is already in Appertivo.")
    restaurant.name = request.form["name"].strip()
    restaurant.city = canonical_market_city(request.form["city"].strip())
    if is_new and restaurant.city not in SKAGIT_VALLEY["cities"]:
        abort(400, "Appertivo is coming soon for that restaurant.")
    restaurant.slug = unique_restaurant_slug(request.form.get("slug") or restaurant.name, restaurant.id)
    restaurant.address = request.form.get("address", "").strip()
    restaurant.postal_code = request.form.get("postal_code", "").strip()
    restaurant.us_state = request.form.get("us_state", "").strip()
    restaurant.phone = request.form.get("phone", "").strip()
    restaurant.contact_email = request.form.get("contact_email", "").strip().lower()
    restaurant.website = request.form.get("website", "").strip()
    if place_id:
        restaurant.place_id = place_id
    restaurant.category = request.form.get("category", "").strip()
    restaurant.subtypes = request.form.get("subtypes", "").strip()
    cuisine_tags = serialize_tag_keys(request.form.getlist("cuisine_tags"), allowed=CUISINE_TAG_KEYS)
    restaurant.cuisine_tags = cuisine_tags or serialize_tag_keys(infer_restaurant_cuisine_tags(restaurant), allowed=CUISINE_TAG_KEYS)
    restaurant.claimed = request.form.get("claimed") == "on"
    restaurant.direct_publish_enabled = request.form.get("direct_publish_enabled") == "on"
    if is_new:
        restaurant.catalog_status = "included"
        restaurant.catalog_reason = "admin Google Places add"
        restaurant.catalog_reviewed_at = utc_now()
    return restaurant


def map_data(restaurants):
    return [
        {
            "name": item.name,
            "city": item.city,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "url": url_for("restaurant_detail", slug=item.slug),
        }
        for item in restaurants
        if item.latitude is not None and item.longitude is not None
    ]


def special_map_data(specials):
    return [
        {
            "title": special.title,
            "price": special.price,
            "restaurant": special.restaurant.name,
            "city": special.restaurant.city,
            "latitude": special.restaurant.latitude,
            "longitude": special.restaurant.longitude,
            "url": url_for("special_detail", public_id=special.public_id),
        }
        for special in specials
        if special.restaurant.latitude is not None and special.restaurant.longitude is not None
    ]


def feed_url_args(location=None, city=None, tag=None, view=None):
    args = {}
    if location:
        args["location"] = location
    if city:
        args["city"] = city
    if tag:
        args["tag"] = tag
    if view:
        args["view"] = view
    return args


def select_featured_special(specials):
    ranked = [special for special in specials if special.featured_rank is not None]
    if ranked:
        return sorted(ranked, key=lambda special: special.featured_rank)[0]
    return next((special for special in specials if special.photo_url), None) or (specials[0] if specials else None)


def nearby_specials_for_city(city, limit=6):
    return (
        active_specials_query()
        .filter(market_city_filter(SKAGIT_VALLEY))
        .filter(~or_(*(Restaurant.city.ilike(value) for value in market_city_variants(city))))
        .order_by(Special.published_at.desc(), Special.created_at.desc())
        .limit(limit)
        .all()
    )


def render_specials_feed(
    forced_city=None,
    forced_tag=None,
    page_title=None,
    page_description=None,
    canonical_url=None,
    hub_label=None,
    hub_heading=None,
):
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        location = request.form.get("location", "").strip() or SKAGIT_VALLEY["label"]
        city = forced_city or request.form.get("city", "").strip()
        tag = forced_tag or selected_tag_key(request.form.get("tag", ""))
        market, _ = resolve_market(location)
        if email:
            favorite_tag = f"special_tag:{tag}" if tag else None
            subscribe(email, city=city, location=location, favorite_tag=favorite_tag)
            if market:
                flash("You're on the early list. Skagit Valley specials alerts are coming soon.")
            else:
                flash(f"You're on the waitlist. We'll let you know when Appertivo reaches {location}.")
        return redirect(url_for(request.endpoint, **feed_url_args(location=location, city=city, tag=tag)))
    location = request.args.get("location", "").strip()
    market, matched_city = resolve_market(location)
    city = forced_city or request.args.get("city", "").strip()
    active_tag = forced_tag or selected_tag_key(request.args.get("tag", ""))
    view = "map" if request.args.get("view") == "map" else "list"
    if not city and matched_city:
        city = matched_city
    if market:
        query = active_specials_query().filter(market_city_filter(market))
        if city:
            query = query.filter(or_(*(Restaurant.city.ilike(value) for value in market_city_variants(city))))
        if active_tag:
            query = query.filter(special_tag_filter(active_tag))
        all_specials = query.order_by(Special.published_at.desc(), Special.created_at.desc()).all()
        cities = market["cities"]
    else:
        all_specials = []
        cities = []
    featured_special = select_featured_special(all_specials)
    specials = [special for special in all_specials if not featured_special or special.id != featured_special.id]
    nearby_specials = nearby_specials_for_city(city) if forced_city and not all_specials else []
    return render_template(
        "home.html",
        specials=specials,
        all_specials=all_specials,
        featured_special=featured_special,
        nearby_specials=nearby_specials,
        cities=cities,
        city=city,
        location=location or SKAGIT_VALLEY["label"],
        active_tag=active_tag,
        view=view,
        feed_tags=feed_tag_options(),
        market=market,
        map_center=(market or SKAGIT_VALLEY)["center"],
        map_zoom=(market or SKAGIT_VALLEY)["zoom"],
        map_specials=special_map_data(all_specials),
        saved_count=len(saved_special_ids()),
        page_title=page_title,
        page_description=page_description,
        canonical_url=canonical_url,
        hub_label=hub_label,
        hub_heading=hub_heading,
        forced_hub=bool(forced_city or forced_tag or hub_label),
    )


@app.route("/", methods=["GET", "POST"])
def home():
    return render_specials_feed()


@app.route("/specials", methods=["GET", "POST"])
def specials_feed():
    return render_specials_feed()


@app.route("/specials/today", methods=["GET", "POST"])
def specials_today():
    return render_specials_feed(
        page_title="Today's Skagit Valley restaurant specials | Appertivo",
        page_description="Browse today's active restaurant specials across Skagit Valley, WA.",
        canonical_url=url_for("specials_today", _external=True),
        hub_label="Skagit Valley - Updated daily",
        hub_heading="Today's Skagit Valley specials",
    )


@app.route("/specials/happy-hour", methods=["GET", "POST"])
def specials_happy_hour():
    return render_specials_feed(
        forced_tag="happy_hour",
        page_title="Happy hour specials in Skagit Valley | Appertivo",
        page_description="Find active happy hour specials from local Skagit Valley restaurants.",
        canonical_url=url_for("specials_happy_hour", _external=True),
        hub_label="Happy Hour - Updated daily",
        hub_heading="Happy hour specials",
    )


@app.get("/how-it-works")
def how_it_works():
    return render_template("faq.html")


@app.get("/for-restaurants")
def for_restaurants():
    return render_template("for_restaurants.html")


@app.get("/for-diners")
def for_diners():
    return redirect(url_for("home"))


@app.get("/faq")
def faq():
    return redirect(url_for("how_it_works"))


@app.get("/contact")
def contact():
    return render_template("contact.html")


@app.get("/unsubscribe")
def unsubscribe():
    email = request.args.get("email", "").strip().lower()
    token = request.args.get("token", "")
    if not email or not valid_unsubscribe_token(email, token):
        abort(404)
    subscriber = Subscriber.query.filter_by(email=email).first()
    if not subscriber:
        subscriber = Subscriber(email=email, is_subscribed=False, unsubscribed_at=utc_now())
        db.session.add(subscriber)
    else:
        subscriber.is_subscribed = False
        subscriber.unsubscribed_at = utc_now()
    db.session.commit()
    return render_template("unsubscribe.html", email=email)


@app.route("/get-started", methods=["GET", "POST"])
def get_started():
    default_date = request.form.get("special_date") or datetime.now(LOCAL_TZ).date().isoformat()
    if request.method == "POST":
        raw_text = request.form.get("raw_text", "").strip()
        sender_email = request.form.get("sender_email", "").strip().lower()
        if not raw_text or not sender_email:
            flash("Choose your restaurant, add an email, and paste the special details.")
            return render_template("get_started.html", form=request.form, special_date=default_date), 400
        try:
            image_path, image_url = save_submitted_photo()
            restaurant = restaurant_from_get_started_form()
        except UploadError as error:
            flash(str(error))
            return render_template("get_started.html", form=request.form, special_date=default_date), 400
        submission = create_raw_submission(
            source_channel="get_started",
            restaurant_id=restaurant.id,
            raw_text=raw_text,
            raw_image_url=image_url,
            raw_image_path=image_path,
            sender_email=sender_email,
        )
        draft = generate_draft_from_submission(submission.id)
        special_date = request.form.get("special_date") or datetime.now(LOCAL_TZ).date().isoformat()
        draft.starts_at = parse_local_datetime(special_date, default_time=time(0, 0))
        draft.expires_at = parse_local_datetime(special_date, default_time=time(23, 59))
        from email_system.outreach_service import send_draft_publish_email

        send_draft_publish_email(draft, sender_email)
        db.session.commit()
        return render_template("submit_success.html", restaurant=restaurant, special=None)
    return render_template("get_started.html", special_date=default_date)


@app.route("/restaurants")
def restaurants():
    city = request.args.get("city", "").strip()
    search_term = request.args.get("q", "").strip()
    query = Restaurant.query.filter_by(catalog_status="included")
    if city:
        query = query.filter(or_(*(Restaurant.city.ilike(value) for value in market_city_variants(city))))
    if search_term:
        query = query.filter(restaurant_search_filter(search_term))
    items = query.order_by(Restaurant.name).all()
    now = utc_now()
    active_counts = dict(
        db.session.query(Special.restaurant_id, func.count(Special.id))
        .filter(
            Special.status == "published",
            or_(Special.starts_at.is_(None), Special.starts_at <= now),
            or_(Special.expires_at.is_(None), Special.expires_at >= now),
        )
        .group_by(Special.restaurant_id)
        .all()
    )
    for r in items:
        r.active_special_count = active_counts.get(r.id, 0)
    items.sort(key=lambda r: (-r.active_special_count, r.name))
    cities = [
        row[0]
        for row in db.session.query(Restaurant.city)
        .filter_by(catalog_status="included")
        .distinct()
        .order_by(Restaurant.city)
    ]
    return render_template(
        "restaurants.html",
        restaurants=items,
        cities=cities,
        city=city,
        search_term=search_term,
        map_restaurants=map_data(items),
    )


@app.get("/api/search")
def search_suggestions():
    term = request.args.get("q", "").strip()
    if len(term) < 2:
        return jsonify([])
    items = (
        Restaurant.query.filter_by(catalog_status="included")
        .filter(restaurant_search_filter(term))
        .order_by(Restaurant.name)
        .limit(8)
    )
    return jsonify([{"name": item.name, "location": item.city, "url": url_for("restaurant_detail", slug=item.slug)} for item in items])


@app.get("/api/submit-restaurants")
def submit_restaurant_suggestions():
    term = request.args.get("q", "").strip()
    if len(term) < 2:
        return jsonify([])
    local_restaurants = (
        included_restaurants_query()
        .filter(restaurant_search_filter(term))
        .order_by(Restaurant.name)
        .limit(8)
        .all()
    )
    results = [restaurant_submit_result(restaurant) for restaurant in local_restaurants]
    local_names = {restaurant.name.lower() for restaurant in local_restaurants}
    for suggestion in google_places_submit_suggestions(term, limit=max(0, 8 - len(results))):
        if suggestion["name"].lower() not in local_names:
            results.append(suggestion)
    return jsonify(results)


@app.get("/api/restaurant-lookup")
def restaurant_lookup():
    term = request.args.get("q", "").strip()
    include_google_duplicates = request.args.get("include_google_duplicates") == "1"
    if len(term) < 2:
        return jsonify([])
    local_restaurants = (
        included_restaurants_query()
        .filter(restaurant_search_filter(term))
        .order_by(Restaurant.name)
        .limit(6)
        .all()
    )
    results = [restaurant_submit_result(restaurant, status="included") for restaurant in local_restaurants]
    seen = set() if include_google_duplicates else {restaurant.name.lower() for restaurant in local_restaurants}
    google_limit = 8 if include_google_duplicates else max(0, 8 - len(results))
    for suggestion in google_places_restaurant_lookup(term, limit=google_limit):
        if suggestion["name"].lower() not in seen:
            results.append(suggestion)
    return jsonify(results)


@app.route("/restaurants/<slug>", methods=["GET", "POST"])
def restaurant_detail(slug):
    restaurant = Restaurant.query.filter_by(slug=slug, catalog_status="included").first_or_404()
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if email:
            subscribe(
                email,
                city=restaurant.city,
                location=SKAGIT_VALLEY["label"],
                favorite_tag=f"restaurant:{restaurant.slug}",
            )
            flash(f"You're following {restaurant.name}. Alerts are coming soon.")
        return redirect(url_for("restaurant_detail", slug=slug))
    specials = active_specials_query().filter(Restaurant.id == restaurant.id).all()
    past_specials = (
        Special.query.filter(
            Special.restaurant_id == restaurant.id,
            Special.status == "expired",
        )
        .order_by(Special.expires_at.desc())
        .limit(8)
        .all()
    )
    return render_template(
        "restaurant.html",
        restaurant=restaurant,
        specials=specials,
        past_specials=past_specials,
        restaurant_graph=restaurant_graph_schema(restaurant, specials),
    )


@app.route("/submit/<token>", methods=["GET", "POST"])
def submit_special(token):
    restaurant = included_restaurants_query().filter_by(submission_token_hash=hash_token(token)).first_or_404()
    if request.method == "POST":
        raw_text = request.form.get("raw_text", "").strip()
        if not raw_text:
            flash("Special details are required.")
            return render_template("submit.html", restaurant=restaurant), 400
        try:
            image_path, image_url = save_submitted_photo()
        except UploadError as error:
            flash(str(error))
            return render_template("submit.html", restaurant=restaurant), 400
        submission = create_raw_submission(
            source_channel="operator_link",
            restaurant_id=restaurant.id,
            raw_text=raw_text,
            raw_image_url=image_url,
            raw_image_path=image_path,
        )
        draft = generate_draft_from_submission(submission.id)
        special = None
        if restaurant.direct_publish_enabled:
            approve_draft(draft.approval_token)
            special = publish_draft(draft.id)
        if restaurant.contact_email:
            if restaurant.direct_publish_enabled and special:
                special_url = f"{app.config['APP_BASE_URL'].rstrip('/')}/specials/{special.public_id}"
                send_notification_email(
                    restaurant.contact_email,
                    f"Your special is live on Appertivo",
                    f"Your special \"{special.title}\" for {restaurant.name} is now live.\n\n{special_url}",
                )
            elif not restaurant.direct_publish_enabled:
                send_notification_email(
                    restaurant.contact_email,
                    f"We received your special for {restaurant.name}",
                    f"We received \"{draft.title}\" for {restaurant.name} and will get it live shortly.",
                )
        return render_template("submit_success.html", restaurant=restaurant, special=special)
    return render_template("submit.html", restaurant=restaurant)


@app.route("/submit-special", methods=["GET", "POST"])
def public_submit_special():
    restaurants = included_restaurants_query().order_by(Restaurant.name).all()
    if request.method == "POST":
        try:
            restaurant_id = included_restaurant_id_from_form()
        except BadRequest:
            flash("That restaurant is coming soon. For now, submissions are open to the Skagit Valley pilot list.")
            return render_template("public_submit_special.html", restaurants=restaurants), 400
        raw_text = request.form.get("raw_text", "").strip()
        if not raw_text:
            flash("Special details are required.")
            return render_template("public_submit_special.html", restaurants=restaurants), 400
        sender_email = request.form.get("sender_email", "").strip()
        if not sender_email:
            flash("Email is required so we can send the approval link.")
            return render_template("public_submit_special.html", restaurants=restaurants), 400
        try:
            image_path, image_url = save_submitted_photo()
        except UploadError as error:
            flash(str(error))
            return render_template("public_submit_special.html", restaurants=restaurants), 400
        submission = create_raw_submission(
            source_channel="public_form",
            restaurant_id=restaurant_id,
            raw_text=raw_text,
            raw_image_url=image_url,
            raw_image_path=image_path,
            sender_email=sender_email,
            sender_phone=request.form.get("sender_phone", "").strip() or None,
        )
        draft = generate_draft_from_submission(submission.id)
        send_special_received_email(
            sender_email,
            restaurant_name=submission.restaurant.name if submission.restaurant else None,
            special_title=draft.title,
            approval_url=None,
            publish_url=url_for("special_preview", approval_token=draft.approval_token, _external=True),
            special_description=draft.description,
            price_text=draft.price_text,
            availability_text=draft.availability_text,
            image_url=draft.image_url,
        )
        return render_template("submit_success.html", restaurant=submission.restaurant, special=None)
    return render_template("public_submit_special.html", restaurants=restaurants)


def special_webhook_response(source_channel):
    if not (app.config["TESTING"] or app.config["SPECIAL_WEBHOOK_TEST_ENABLED"]):
        abort(404)
    payload = request.get_json(silent=True) or {}
    raw_text = (payload.get("raw_text") or "").strip()
    if not raw_text:
        abort(400, "raw_text is required.")
    restaurant_id = payload.get("restaurant_id")
    if restaurant_id is not None and not included_restaurants_query().filter_by(id=restaurant_id).first():
        abort(400, "restaurant_id must reference an included restaurant.")
    submission = create_raw_submission(
        source_channel=source_channel,
        restaurant_id=restaurant_id,
        raw_text=raw_text,
        raw_image_url=payload.get("image_url"),
        sender_email=payload.get("sender_email"),
        sender_phone=payload.get("sender_phone"),
    )
    draft = generate_draft_from_submission(submission.id)
    return jsonify(
        {
            "raw_submission_id": submission.id,
            "draft_id": draft.id,
            "preview_url": url_for("special_preview", approval_token=draft.approval_token, _external=True),
        }
    ), 201


@app.post("/webhooks/email-special")
def email_special_webhook():
    return special_webhook_response("email")


@app.post("/webhooks/sms-special")
def sms_special_webhook():
    return special_webhook_response("sms")


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_ROOT"], filename)


def active_special_by_public_id(public_id):
    return (
        Special.query.join(Restaurant)
        .filter(
            Special.public_id == public_id,
            Special.status == "published",
            Restaurant.catalog_status == "included",
        )
        .first_or_404()
    )


def latest_special_timestamp_expression():
    return func.max(func.coalesce(Special.updated_at, Special.published_at, Special.starts_at, Special.expires_at, Special.created_at))


def date_lastmod(value=None):
    moment = value or utc_now()
    return moment.replace(tzinfo=UTC).astimezone(LOCAL_TZ).date().isoformat()


def sitemap_url(loc, lastmod=None, changefreq="weekly", priority="0.6"):
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{date_lastmod(lastmod)}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


def latest_special_timestamp_for(query):
    row = query.with_entities(latest_special_timestamp_expression()).first()
    return row[0] if row else None


def city_hub_has_content(city):
    own_count = (
        active_specials_query()
        .filter(or_(*(Restaurant.city.ilike(value) for value in market_city_variants(city))))
        .count()
    )
    return own_count > 0 or bool(nearby_specials_for_city(city, limit=1))


def build_sitemap_xml():
    now = utc_now()
    urls = [
        sitemap_url(url_for("home", _external=True), now, "daily", "0.8"),
        sitemap_url(url_for("specials_feed", _external=True), now, "daily", "0.8"),
        sitemap_url(url_for("specials_today", _external=True), now, "daily", "0.8"),
        sitemap_url(url_for("specials_happy_hour", _external=True), now, "daily", "0.8"),
        sitemap_url(url_for("restaurants", _external=True), now, "weekly", "0.6"),
    ]
    happy_hour_lastmod = latest_special_timestamp_for(skagit_specials_query().filter(special_tag_filter("happy_hour")))
    if happy_hour_lastmod:
        urls[3] = sitemap_url(url_for("specials_happy_hour", _external=True), happy_hour_lastmod, "daily", "0.8")

    for city in SKAGIT_VALLEY["cities"]:
        if not city_hub_has_content(city):
            continue
        city_query = skagit_specials_query().filter(
            or_(*(Restaurant.city.ilike(value) for value in market_city_variants(city)))
        )
        urls.append(
            sitemap_url(
                url_for("special_detail", public_id=city_hub_slug(city), _external=True),
                latest_special_timestamp_for(city_query) or now,
                "daily",
                "0.8",
            )
        )

    special_updates = dict(
        db.session.query(
            Special.restaurant_id,
            latest_special_timestamp_expression(),
        )
        .join(Restaurant)
        .filter(Special.status == "published", Restaurant.catalog_status == "included")
        .group_by(Special.restaurant_id)
        .all()
    )
    restaurants = included_restaurants_query().order_by(Restaurant.slug).all()
    for restaurant in restaurants:
        timestamps = [
            restaurant.catalog_reviewed_at,
            restaurant.created_at,
            special_updates.get(restaurant.id),
        ]
        lastmod = max((value for value in timestamps if value), default=now)
        changefreq = "daily" if special_updates.get(restaurant.id) else "weekly"
        urls.append(
            sitemap_url(
                url_for("restaurant_detail", slug=restaurant.slug, _external=True),
                lastmod,
                changefreq,
                "0.8",
            )
        )
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n"


@app.get("/sitemap.xml")
def sitemap_xml():
    cache_seconds = app.config["SITEMAP_CACHE_SECONDS"]
    generated_at = SITEMAP_CACHE.get("generated_at")
    if SITEMAP_CACHE.get("body") and generated_at and (utc_now() - generated_at).total_seconds() < cache_seconds:
        body = SITEMAP_CACHE["body"]
    else:
        body = build_sitemap_xml()
        SITEMAP_CACHE.update(generated_at=utc_now(), body=body)
    return Response(body, mimetype="application/xml")


@app.get("/robots.txt")
def robots_txt():
    body = f"User-agent: *\nAllow: /\nSitemap: {url_for('sitemap_xml', _external=True)}\n"
    return Response(body, mimetype="text/plain")


@app.get("/saved")
def saved_specials():
    ids = saved_special_ids()
    specials = []
    if ids:
        specials = (
            active_specials_query()
            .filter(Special.id.in_(ids))
            .order_by(Special.published_at.desc(), Special.created_at.desc())
            .all()
        )
    return render_template("saved.html", specials=specials, saved_count=len(ids))


@app.get("/specials/<public_id>")
def special_detail(public_id):
    city = city_from_hub_slug(public_id)
    if city:
        return render_specials_feed(
            forced_city=city,
            page_title=f"{city} restaurant specials | Appertivo",
            page_description=f"Find active restaurant specials in {city}, WA, plus nearby Skagit Valley spots when today's board is quiet.",
            canonical_url=url_for("special_detail", public_id=city_hub_slug(city), _external=True),
            hub_label=f"{city} - Updated daily",
            hub_heading=f"{city} restaurant specials",
        )
    special = active_special_by_public_id(public_id)
    record_metric(special, "view", request.args.get("channel"))
    return render_template("special.html", special=special, can_manage=can_manage_special(special))


@app.post("/specials/<public_id>/save")
def save_special(public_id):
    special = active_special_by_public_id(public_id)
    ids = saved_special_ids()
    if special.id in ids:
        ids.remove(special.id)
        flash("Removed from saved specials.")
    else:
        ids.add(special.id)
        record_metric(special, "save", request.args.get("channel"))
        flash("Special saved.")
    session["saved_special_ids"] = sorted(ids)
    return redirect(request.referrer or url_for("special_detail", public_id=public_id))


@app.post("/specials/<public_id>/sold-out")
def mark_special_sold_out(public_id):
    special = active_special_by_public_id(public_id)
    if not can_manage_special(special):
        abort(403)
    special.status = "expired"
    special.expires_at = utc_now()
    db.session.commit()
    flash("Special marked sold out.")
    return redirect(url_for("restaurant_detail", slug=special.restaurant.slug))


@app.get("/specials/<public_id>/action/<event_type>")
def special_action(public_id, event_type):
    special = active_special_by_public_id(public_id)
    destinations = {
        "directions": f"https://www.google.com/maps/search/?api=1&query={special.restaurant.latitude},{special.restaurant.longitude}",
        "call": f"tel:{special.restaurant.phone}",
        "website": special.restaurant.site,
        "share": url_for("special_detail", public_id=special.public_id, _external=True),
    }
    destination = destinations.get(event_type)
    if event_type not in METRIC_TYPES or not destination:
        abort(404)
    record_metric(special, event_type, request.args.get("channel"))
    return redirect(destination)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        require_csrf()
        if hmac.compare_digest(request.form.get("password", ""), app.config["ADMIN_PASSWORD"]):
            session["admin_authenticated"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.")
    return render_template("admin/login.html")


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    active_count = active_specials_query().count()
    distributed = db.session.query(DistributionLog.special_id).distinct()
    counts = {
        "new leads": RestaurantLead.query.filter_by(status="new").count(),
        "drafts awaiting review": (
            Special.query.join(Restaurant)
            .filter(Special.status == "draft", Restaurant.catalog_status == "included")
            .count()
        ),
        "active specials": active_count,
        "undistributed specials": active_specials_query().filter(~Special.id.in_(distributed)).count(),
        "subscribers": Subscriber.query.count(),
        "views": SpecialMetric.query.filter_by(event_type="view").count(),
        "action clicks": SpecialMetric.query.filter(SpecialMetric.event_type != "view").count(),
        "outreach follow-ups": operational_outreach_campaigns_query()
        .filter(
            OutreachCampaign.archived.is_(False),
            OutreachCampaign.paused.is_(False),
            OutreachCampaign.status.in_(["drafting", "active"]),
            or_(OutreachCampaign.next_follow_up_at.is_(None), OutreachCampaign.next_follow_up_at <= utc_now()),
        )
        .count(),
        "catalog reviews": Restaurant.query.filter_by(catalog_status="review").count(),
    }
    return render_template("admin/dashboard.html", counts=counts)


@app.get("/admin/tools")
@admin_required
def admin_tools():
    tools = [
        {
            "title": "Leads",
            "description": "Review restaurant leads and move them through outreach statuses.",
            "url": url_for("admin_leads"),
            "count": RestaurantLead.query.filter_by(status="new").count(),
        },
        {
            "title": "Catalog review",
            "description": "Review venues that need an include or exclude decision.",
            "url": url_for("admin_restaurant_catalog"),
            "count": Restaurant.query.filter_by(catalog_status="review").count(),
        },
        {
            "title": "Enhance restaurants",
            "description": "Attach or pull Google Places details for included restaurants that still need enrichment.",
            "url": url_for("admin_restaurant_enrichment"),
            "count": Restaurant.query.filter(
                Restaurant.google_place_refreshed_at.is_(None),
                Restaurant.catalog_status == "included",
            ).count(),
        },
        {
            "title": "Outreach",
            "description": "Create, review, and manage restaurant outreach campaigns.",
            "url": url_for("admin_outreach"),
            "count": operational_outreach_campaigns_query()
            .filter(
                OutreachCampaign.archived.is_(False),
                OutreachCampaign.paused.is_(False),
                OutreachCampaign.status.in_(["drafting", "active"]),
            )
            .count(),
        },
        {
            "title": "Diner digest",
            "description": "Preview and manually send today's Skagit specials digest.",
            "url": url_for("admin_diner_digest"),
            "count": skagit_subscribers_query().count(),
        },
        {
            "title": "Email tools",
            "description": "Preview transactional templates and send gated test emails.",
            "url": url_for("admin_email_tools"),
            "count": None,
        },
    ]
    return render_template("admin/tools.html", tools=tools)


@app.route("/admin/diner-digest", methods=["GET", "POST"])
@admin_required
def admin_diner_digest():
    digest = build_diner_digest()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "test":
            recipient = app.config["EMAIL_TEST_RECIPIENT"]
            result = send_diner_digest_to(recipient)
            if result["success"]:
                flash(f"Sent diner digest test to {recipient}.")
            else:
                flash(f"Diner digest test failed: {result['error']}")
        elif action == "production":
            subscribers = skagit_subscribers_query().order_by(Subscriber.email).all()
            results = [send_diner_digest_to(subscriber.email) for subscriber in subscribers]
            sent_count = sum(result["success"] for result in results)
            if sent_count:
                record_digest_distribution(digest["specials"])
            failed_count = len(results) - sent_count
            flash(f"Sent diner digest to {sent_count} Skagit subscribers. {failed_count} failed.")
        else:
            abort(400)
        return redirect(url_for("admin_diner_digest"))
    return render_template("admin/diner_digest.html", digest=digest, test_recipient=app.config["EMAIL_TEST_RECIPIENT"])


@app.route("/admin/email-tools", methods=["GET", "POST"])
@admin_required
def admin_email_tools():
    from email_system.email_service import SUBJECTS, render_test_email, send_all_test_emails

    recipient = app.config["EMAIL_TEST_RECIPIENT"]
    if request.method == "POST":
        if not app.config["EMAIL_TEST_ENABLED"]:
            flash("Email test sending is disabled. Set EMAIL_TEST_ENABLED=1.")
        else:
            results = send_all_test_emails(recipient)
            sent_count = sum(result["success"] for result in results.values())
            flash(f"Sent {sent_count} of {len(results)} email templates to {recipient}.")
        return redirect(url_for("admin_email_tools"))
    previews = {name: render_test_email(name)["html"] for name in SUBJECTS}
    return render_template("admin/email_tools.html", previews=previews, recipient=recipient)


def rotate_restaurant_submission_url(restaurant):
    token = secrets.token_urlsafe(24)
    restaurant.submission_token_hash = hash_token(token)
    db.session.commit()
    return url_for("submit_special", token=token, _external=True)


@app.route("/admin/outreach", methods=["GET", "POST"])
@admin_required
def admin_outreach():
    from email_system.outreach_service import ensure_default_outreach_templates

    if request.method == "POST":
        return redirect(url_for("admin_outreach"))
    ensure_default_outreach_templates()
    campaigns = (
        operational_outreach_campaigns_query()
        .filter(OutreachCampaign.archived.is_(False))
        .order_by(OutreachCampaign.updated_at.desc(), OutreachCampaign.last_sent_at.desc())
        .all()
    )
    selected_campaign = None
    selected_id = request.args.get("conversation", type=int)
    if selected_id:
        selected_campaign = (
            operational_outreach_campaigns_query()
            .filter(OutreachCampaign.id == selected_id, OutreachCampaign.archived.is_(False))
            .first()
        )
    if not selected_campaign and campaigns:
        selected_campaign = campaigns[0]
    restaurants = (
        included_restaurants_query()
        .filter(Restaurant.contact_email.isnot(None), Restaurant.contact_email != "")
        .order_by(Restaurant.city, Restaurant.name)
        .all()
    )
    templates = OutreachTemplate.query.filter_by(is_active=True).order_by(OutreachTemplate.name).all()
    return render_template(
        "admin/outreach.html",
        campaigns=campaigns,
        selected_campaign=selected_campaign,
        restaurants=restaurants,
        templates=templates,
    )


@app.post("/admin/outreach/send")
@admin_required
def admin_outreach_send_direct():
    from email_system.outreach_service import render_outreach_text, send_direct_outreach

    restaurant = included_restaurant_or_404(included_restaurant_id_from_form())
    subject = request.form.get("subject", "").strip()
    body_text = request.form.get("body_text", "").strip()
    if not subject or not body_text:
        flash("Add a subject and message before sending.")
        return redirect(url_for("admin_outreach"))
    submission_url = request.form.get("submission_url", "").strip()
    if "{{ submission_url" in subject or "{{ submission_url" in body_text:
        submission_url = submission_url or rotate_restaurant_submission_url(restaurant)
    subject = render_outreach_text(subject, restaurant, submission_url)
    body_text = render_outreach_text(body_text, restaurant, submission_url)
    template_id = request.form.get("template_id", "").strip() or None
    try:
        message, result = send_direct_outreach(
            restaurant,
            subject,
            body_text,
            recipient_email=restaurant.contact_email,
            template_key=template_id,
        )
    except ValueError as error:
        flash(str(error))
        return redirect(url_for("admin_outreach"))
    flash("Outreach email sent." if result["success"] else f"Send failed: {result['error']}")
    return redirect(url_for("admin_outreach", conversation=message.campaign_id))


@app.post("/admin/outreach/restaurants/<int:restaurant_id>/submission-link")
@admin_required
def admin_outreach_submission_link(restaurant_id):
    restaurant = included_restaurant_or_404(restaurant_id)
    if not restaurant.contact_email:
        abort(400, "Choose a restaurant with a contact email.")
    return jsonify({"submission_url": rotate_restaurant_submission_url(restaurant)})


@app.post("/admin/outreach/templates")
@admin_required
def admin_outreach_create_template():
    template = OutreachTemplate(
        name=request.form.get("name", "").strip(),
        subject=request.form.get("subject", "").strip(),
        body_text=request.form.get("body_text", "").strip(),
        is_active=True,
    )
    if not template.name or not template.subject or not template.body_text:
        flash("Template name, subject, and body are required.")
        return redirect(url_for("admin_outreach"))
    db.session.add(template)
    try:
        db.session.commit()
        flash("Template saved.")
    except Exception:
        db.session.rollback()
        flash("Template names must be unique.")
    return redirect(url_for("admin_outreach"))


@app.post("/admin/outreach/templates/<int:template_id>")
@admin_required
def admin_outreach_update_template(template_id):
    template = OutreachTemplate.query.get_or_404(template_id)
    if request.form.get("action") == "deactivate":
        template.is_active = False
        db.session.commit()
        flash("Template archived.")
        return redirect(url_for("admin_outreach"))
    template.name = request.form.get("name", "").strip()
    template.subject = request.form.get("subject", "").strip()
    template.body_text = request.form.get("body_text", "").strip()
    if not template.name or not template.subject or not template.body_text:
        flash("Template name, subject, and body are required.")
        return redirect(url_for("admin_outreach"))
    db.session.commit()
    flash("Template updated.")
    return redirect(url_for("admin_outreach"))


@app.post("/api/webhooks/resend")
def resend_webhook():
    from email_system.outreach_service import receive_resend_email

    try:
        result = receive_resend_email(
            request.get_data(as_text=True),
            {
                "id": request.headers.get("svix-id"),
                "timestamp": request.headers.get("svix-timestamp"),
                "signature": request.headers.get("svix-signature"),
            },
        )
    except ValueError as error:
        app.logger.warning("Resend webhook rejected: %s", error)
        abort(400, str(error))
    except Exception:
        app.logger.exception("Resend webhook processing failed.")
        abort(500)
    if result:
        app.logger.info("Resend webhook processed into %s id=%s", type(result).__name__, getattr(result, "id", None))
    else:
        app.logger.info("Resend webhook received no-op event.")
    return jsonify({"received": True})


@app.get("/admin/leads")
@admin_required
def admin_leads():
    status = request.args.get("status", "")
    query = RestaurantLead.query
    if status in LEAD_STATUSES:
        query = query.filter_by(status=status)
    return render_template(
        "admin/leads.html",
        leads=query.order_by(RestaurantLead.created_at.desc()).all(),
        status=status,
    )


@app.post("/admin/leads/<int:lead_id>/<action>")
@admin_required
def admin_lead_action(lead_id, action):
    if action not in LEAD_STATUSES:
        abort(404)
    lead = RestaurantLead.query.get_or_404(lead_id)
    lead.status = action
    db.session.commit()
    flash(f"{lead.restaurant_name} marked {action}.")
    return redirect(request.referrer or url_for("admin_leads"))


@app.route("/admin/restaurants", methods=["GET", "POST"])
@admin_required
def admin_restaurants():
    if request.method == "POST":
        db.session.add(restaurant_from_form())
        db.session.commit()
        flash("Restaurant added.")
        return redirect(url_for("admin_restaurants"))
    term = request.args.get("q", "").strip()
    query = included_restaurants_query()
    if term:
        query = query.filter(restaurant_search_filter(term))
    return render_template("admin/restaurants.html", restaurants=query.order_by(Restaurant.name).all(), search_term=term)


@app.get("/admin/restaurant-catalog")
@admin_required
def admin_restaurant_catalog():
    return render_template(
        "admin/restaurant_catalog.html",
        restaurants=Restaurant.query.filter_by(catalog_status="review").order_by(Restaurant.city, Restaurant.name).all(),
    )


@app.post("/admin/restaurants/<int:restaurant_id>/catalog/<status>")
@admin_required
def admin_restaurant_catalog_action(restaurant_id, status):
    if status not in {"included", "excluded"}:
        abort(404)
    restaurant = Restaurant.query.filter_by(id=restaurant_id, catalog_status="review").first_or_404()
    restaurant.catalog_status = status
    restaurant.catalog_reason = "manual admin review"
    restaurant.catalog_reviewed_at = utc_now()
    db.session.commit()
    flash(f"{restaurant.name} marked {status}.")
    return redirect(request.referrer or url_for("admin_restaurant_catalog"))


@app.post("/admin/restaurants/catalog/<status>")
@admin_required
def admin_restaurant_catalog_bulk_action(status):
    if status not in {"included", "excluded"}:
        abort(404)
    submitted_ids = request.form.getlist("restaurant_ids")
    if not submitted_ids:
        abort(400, "Select at least one venue.")
    try:
        restaurant_ids = [int(restaurant_id) for restaurant_id in submitted_ids]
    except ValueError:
        abort(400, "One or more selected restaurant IDs are invalid.")
    restaurants = Restaurant.query.filter(
        Restaurant.id.in_(restaurant_ids),
        Restaurant.catalog_status == "review",
    ).all()
    if len(restaurants) != len(set(restaurant_ids)):
        abort(400, "One or more selected venues are not pending review.")
    for restaurant in restaurants:
        restaurant.catalog_status = status
        restaurant.catalog_reason = "manual admin review"
        restaurant.catalog_reviewed_at = utc_now()
    db.session.commit()
    flash(f"{len(restaurants)} venues marked {status}.")
    return redirect(request.referrer or url_for("admin_restaurant_catalog"))


@app.get("/admin/restaurant-enrichment")
@admin_required
def admin_restaurant_enrichment():
    restaurants = (
        Restaurant.query.filter(
            Restaurant.google_place_refreshed_at.is_(None),
            Restaurant.catalog_status == "included",
        )
        .order_by(Restaurant.city, Restaurant.name)
        .all()
    )
    return render_template("admin/restaurant_enrichment.html", restaurants=restaurants)


def validate_restaurant_enrichment_request():
    if request.form.get("confirm_api_cost") != "on":
        abort(400, "Confirm the Places API cost before enhancing a restaurant.")
    if request.form.get("confirm_storage_terms") != "on":
        abort(400, "Confirm your Google Maps storage terms before enhancing a restaurant.")
    api_key = app.config["GOOGLE_PLACES_API_KEY"]
    if not api_key:
        flash("Set GOOGLE_PLACES_API_KEY before using restaurant enrichment.")
        return None
    return api_key


def enhance_restaurant(restaurant, api_key):
    from scripts.enrich_restaurants_google import enrich_restaurant, load_application

    load_application()
    enrich_restaurant(restaurant, api_key)
    if not restaurant.cuisine_tags:
        restaurant.cuisine_tags = serialize_tag_keys(infer_restaurant_cuisine_tags(restaurant), allowed=CUISINE_TAG_KEYS)
    db.session.commit()


@app.post("/admin/restaurants/<int:restaurant_id>/enhance")
@admin_required
def admin_enhance_restaurant(restaurant_id):
    api_key = validate_restaurant_enrichment_request()
    if not api_key:
        return redirect(url_for("admin_restaurant_enrichment"))
    restaurant = included_restaurant_or_404(restaurant_id)
    if not restaurant.place_id:
        abort(400, "This restaurant does not have a Google place ID.")

    try:
        enhance_restaurant(restaurant, api_key)
    except Exception:
        db.session.rollback()
        app.logger.exception("Google Places enrichment failed for restaurant %s", restaurant.id)
        flash(f"Could not enhance {restaurant.name}. Check the application logs.")
    else:
        flash(f"Enhanced {restaurant.name}.")
    return redirect(url_for("admin_restaurant_enrichment"))


@app.post("/admin/restaurants/enhance")
@admin_required
def admin_enhance_restaurants():
    api_key = validate_restaurant_enrichment_request()
    if not api_key:
        return redirect(url_for("admin_restaurant_enrichment"))
    submitted_ids = request.form.getlist("restaurant_ids")
    if not submitted_ids:
        abort(400, "Select at least one restaurant to enhance.")
    try:
        restaurant_ids = [int(restaurant_id) for restaurant_id in submitted_ids]
    except ValueError:
        abort(400, "One or more selected restaurant IDs are invalid.")
    restaurants = (
        Restaurant.query.filter(
            Restaurant.id.in_(restaurant_ids),
            Restaurant.place_id.isnot(None),
            Restaurant.place_id != "",
            Restaurant.google_place_refreshed_at.is_(None),
            Restaurant.catalog_status == "included",
        )
        .order_by(Restaurant.id)
        .all()
    )
    if len(restaurants) != len(set(restaurant_ids)):
        abort(400, "One or more selected restaurants cannot be enhanced.")

    enhanced = 0
    failed = []
    for restaurant in restaurants:
        try:
            enhance_restaurant(restaurant, api_key)
            enhanced += 1
        except Exception:
            db.session.rollback()
            app.logger.exception("Google Places enrichment failed for restaurant %s", restaurant.id)
            failed.append(restaurant.name)
    if enhanced:
        flash(f"Enhanced {enhanced} restaurants.")
    if failed:
        flash(f"Could not enhance {len(failed)} restaurants: {', '.join(failed)}.")
    return redirect(url_for("admin_restaurant_enrichment"))


@app.post("/admin/restaurants/enrichment/exclude")
@admin_required
def admin_exclude_restaurants_from_enrichment():
    submitted_ids = request.form.getlist("restaurant_ids")
    if not submitted_ids:
        abort(400, "Select at least one restaurant to exclude.")
    try:
        restaurant_ids = [int(restaurant_id) for restaurant_id in submitted_ids]
    except ValueError:
        abort(400, "One or more selected restaurant IDs are invalid.")
    restaurants = Restaurant.query.filter(
        Restaurant.id.in_(restaurant_ids),
        Restaurant.place_id.isnot(None),
        Restaurant.place_id != "",
        Restaurant.google_place_refreshed_at.is_(None),
        Restaurant.catalog_status == "included",
    ).all()
    if len(restaurants) != len(set(restaurant_ids)):
        abort(400, "One or more selected restaurants cannot be excluded from this queue.")
    for restaurant in restaurants:
        restaurant.catalog_status = "excluded"
        restaurant.catalog_reason = "excluded from enrichment queue"
        restaurant.catalog_reviewed_at = utc_now()
    db.session.commit()
    flash(f"{len(restaurants)} restaurants excluded from the active catalog.")
    return redirect(url_for("admin_restaurant_enrichment"))


@app.route("/admin/restaurants/<int:restaurant_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_restaurant(restaurant_id):
    restaurant = included_restaurant_or_404(restaurant_id)
    if request.method == "POST":
        restaurant_from_form(restaurant)
        db.session.commit()
        flash("Restaurant updated.")
        return redirect(url_for("admin_edit_restaurant", restaurant_id=restaurant.id))
    return render_template("admin/restaurant_form.html", restaurant=restaurant)


@app.post("/admin/restaurants/<int:restaurant_id>/token")
@admin_required
def admin_restaurant_token(restaurant_id):
    restaurant = included_restaurant_or_404(restaurant_id)
    token = secrets.token_urlsafe(24)
    restaurant.submission_token_hash = hash_token(token)
    db.session.commit()
    submission_url = url_for("submit_special", token=token, _external=True)
    return render_template("admin/token_created.html", restaurant=restaurant, submission_url=submission_url)


@app.post("/admin/restaurants/<int:restaurant_id>/delete")
@admin_required
def admin_delete_restaurant(restaurant_id):
    restaurant = included_restaurant_or_404(restaurant_id)
    db.session.delete(restaurant)
    db.session.commit()
    flash("Restaurant deleted.")
    return redirect(url_for("admin_restaurants"))


@app.get("/admin/specials")
@admin_required
def admin_specials():
    status = request.args.get("status", "")
    query = Special.query.join(Restaurant).filter(Restaurant.catalog_status == "included")
    if status in {"draft", "published", "expired"}:
        query = query.filter(Special.status == status)
    return render_template("admin/specials.html", specials=query.order_by(Special.created_at.desc()).all(), status=status)


@app.get("/admin/special-submissions")
@admin_required
def admin_special_submissions():
    submissions = RawSpecialSubmission.query.order_by(RawSpecialSubmission.created_at.desc()).all()
    return render_template("admin/special_submissions.html", submissions=submissions)


@app.post("/admin/special-submissions/<int:submission_id>/enhance")
@admin_required
def admin_enhance_special_submission(submission_id):
    try:
        draft = enhance_draft_from_submission(submission_id)
    except ValueError as error:
        abort(400, str(error))
    flash("Submission enhanced into a draft.")
    return redirect(url_for("special_preview", approval_token=draft.approval_token))


@app.get("/admin/special-drafts")
@admin_required
def admin_special_drafts():
    drafts = SpecialDraft.query.order_by(SpecialDraft.created_at.desc()).all()
    restaurants = included_restaurants_query().order_by(Restaurant.name).all()
    return render_template("admin/special_drafts.html", drafts=drafts, restaurants=restaurants)


@app.route("/admin/special-drafts/<int:draft_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_special_draft(draft_id):
    draft = SpecialDraft.query.get_or_404(draft_id)
    if request.method == "POST":
        try:
            draft_from_form(draft)
            db.session.commit()
        except UploadError as error:
            flash(str(error))
            return redirect(url_for("admin_edit_special_draft", draft_id=draft.id))
        flash("Draft updated.")
        return redirect(url_for("special_preview", approval_token=draft.approval_token))
    return render_template(
        "admin/special_draft_form.html",
        draft=draft,
        restaurants=included_restaurants_query().order_by(Restaurant.name),
    )


@app.post("/admin/special-drafts/<int:draft_id>/assign")
@admin_required
def admin_assign_special_draft(draft_id):
    draft = SpecialDraft.query.get_or_404(draft_id)
    draft.restaurant_id = included_restaurant_id_from_form()
    draft.raw_submission.restaurant_id = draft.restaurant_id
    db.session.commit()
    flash("Restaurant assigned.")
    return redirect(request.referrer or url_for("admin_special_drafts"))


@app.post("/admin/special-drafts/<int:draft_id>/enhance")
@admin_required
def admin_enhance_special_draft(draft_id):
    draft = SpecialDraft.query.get_or_404(draft_id)
    try:
        draft = enhance_draft_from_submission(draft.raw_submission_id)
    except ValueError as error:
        abort(400, str(error))
    flash("Draft enhanced.")
    return redirect(url_for("special_preview", approval_token=draft.approval_token))


@app.post("/admin/special-drafts/<int:draft_id>/send-publish-email")
@admin_required
def admin_send_special_publish_email(draft_id):
    from email_system.outreach_service import send_draft_publish_email

    draft = SpecialDraft.query.get_or_404(draft_id)
    sender_email = draft.raw_submission.sender_email
    if not sender_email:
        abort(400, "This draft does not have a sender email.")
    if not draft.restaurant_id:
        abort(400, "Assign a restaurant before sending the publish email.")
    result = send_draft_publish_email(draft, sender_email)
    if result and result["success"]:
        flash("Publish email sent.")
    else:
        flash(f"Publish email failed: {(result or {}).get('error', 'unknown error')}")
    return redirect(url_for("special_preview", approval_token=draft.approval_token))


@app.post("/admin/special-drafts/<int:draft_id>/publish")
@admin_required
def admin_publish_special_draft(draft_id):
    try:
        special = publish_draft(draft_id)
    except ValueError as error:
        abort(400, str(error))
    flash("Special published.")
    return redirect(url_for("admin_edit_special", special_id=special.id))


@app.get("/specials/preview/<approval_token>")
def special_preview(approval_token):
    draft = SpecialDraft.query.filter_by(approval_token=approval_token).first_or_404()
    if draft.published_special:
        remember_operator_special(draft.published_special)
        return redirect(url_for("special_detail", public_id=draft.published_special.public_id))
    return render_template("special_preview.html", draft=draft, preview_special=draft_as_preview_special(draft))


@app.post("/specials/preview/<approval_token>/approve")
def approve_special_preview(approval_token):
    try:
        approve_draft(approval_token)
    except ValueError as error:
        abort(400, str(error))
    flash("Draft approved.")
    return redirect(url_for("special_preview", approval_token=approval_token))


@app.post("/specials/preview/<approval_token>/publish")
def publish_special_preview(approval_token):
    try:
        draft = approve_draft(approval_token)
        special = publish_draft(draft.id)
    except ValueError as error:
        abort(400, str(error))
    remember_operator_special(special)
    flash("Special published.")
    return redirect(url_for("special_detail", public_id=special.public_id))


@app.post("/specials/preview/<approval_token>/reject")
def reject_special_preview(approval_token):
    try:
        reject_draft(approval_token)
    except ValueError as error:
        abort(400, str(error))
    flash("Draft rejected.")
    return redirect(url_for("special_preview", approval_token=approval_token))


@app.route("/admin/specials/new", methods=["GET", "POST"])
@app.route("/admin/specials/create", methods=["GET", "POST"])
@admin_required
def admin_new_special():
    if request.method == "POST":
        try:
            draft = structured_draft_from_form(
                "admin",
                included_restaurant_id_from_form(),
                enhance=request.form.get("enhance") == "on",
            )
            if request.form.get("notify_operator") == "on" and draft.restaurant and draft.restaurant.contact_email:
                from email_system.outreach_service import send_draft_publish_email
                send_draft_publish_email(draft, draft.restaurant.contact_email)
            if request.form.get("status", "draft") == "published":
                approve_draft(draft.approval_token)
                special = publish_draft(draft.id)
                return redirect(url_for("admin_edit_special", special_id=special.id))
        except UploadError as error:
            flash(str(error))
            return redirect(url_for("admin_new_special"))
        return redirect(url_for("special_preview", approval_token=draft.approval_token))
    special = Special(status="draft", source="manual")
    restaurant_id = request.args.get("restaurant_id", type=int)
    if restaurant_id and included_restaurants_query().filter_by(id=restaurant_id).first():
        special.restaurant_id = restaurant_id
    return render_template("admin/special_form.html", restaurants=included_restaurants_query().order_by(Restaurant.name), special=special)


@app.route("/admin/specials/<int:special_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_special(special_id):
    special = included_special_or_404(special_id)
    if request.method == "POST":
        was_published = bool(special.published_at)
        try:
            special_from_form(special)
            db.session.commit()
        except UploadError as error:
            flash(str(error))
        else:
            if special.status == "published" and special.published_at and not was_published:
                schedule_first_special_followup_if_needed(special)
        return redirect(url_for("admin_edit_special", special_id=special.id))
    return render_template("admin/special_form.html", restaurants=included_restaurants_query().order_by(Restaurant.name), special=special)


@app.post("/admin/specials/<int:special_id>/<action>")
@admin_required
def admin_special_action(special_id, action):
    special = included_special_or_404(special_id)
    if action == "approve":
        was_published = bool(special.published_at)
        special.status = "published"
        special.published_at = special.published_at or utc_now()
    elif action == "expire":
        special.status = "expired"
        special.expires_at = utc_now()
    elif action == "delete":
        db.session.delete(special)
    else:
        abort(404)
    db.session.commit()
    if action == "approve" and not was_published:
        schedule_first_special_followup_if_needed(special)
    return redirect(request.referrer or url_for("admin_specials"))


@app.route("/admin/specials/<int:special_id>/distribution", methods=["GET", "POST"])
@admin_required
def admin_distribution(special_id):
    special = included_special_or_404(special_id)
    if request.method == "POST":
        channel = request.form["channel"]
        if channel not in CHANNELS:
            abort(400)
        db.session.add(DistributionLog(special_id=special.id, channel=channel, note=request.form.get("note", "").strip()))
        db.session.commit()
        return redirect(url_for("admin_distribution", special_id=special.id))
    caption = f"{special.restaurant.name}: {special.title}"
    if special.price:
        caption += f" - {special.price}"
    caption += f"\n{special.description}\nSee today's special:"
    return render_template("admin/distribution.html", special=special, channels=CHANNELS, caption=caption, metrics=metric_counts(special.id))


@app.route("/admin/intake", methods=["GET", "POST"])
@admin_required
def admin_intake():
    restaurants = included_restaurants_query().order_by(Restaurant.name).all()
    draft = None
    if request.method == "POST":
        raw_text = request.form["raw_text"].strip()
        parsed = parse_special_text(raw_text)
        if request.form.get("save") == "1":
            submission = create_raw_submission(
                source_channel="admin",
                restaurant_id=included_restaurant_id_from_form(),
                raw_text=raw_text,
            )
            special = generate_draft_from_submission(submission.id)
            special.title = request.form["title"].strip()
            special.description = request.form.get("description", "").strip()
            special.price_text = request.form.get("price", "").strip() or None
            special.expires_at = parse_local_datetime(request.form["special_date"], default_time=time(23, 59))
            db.session.commit()
            return redirect(url_for("admin_special_drafts"))
        draft = {"raw_text": raw_text, "restaurant_id": included_restaurant_id_from_form(), **parsed}
    return render_template("admin/intake.html", restaurants=restaurants, draft=draft)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1", threaded=True, use_reloader=False)
