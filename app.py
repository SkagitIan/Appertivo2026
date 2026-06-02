import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, time
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_migrate import Migrate
from sqlalchemy import func, or_

from markets import SKAGIT_VALLEY, resolve_market
from models import (
    DistributionLog,
    OutreachMessage,
    Restaurant,
    RestaurantLead,
    Special,
    SpecialMetric,
    Subscriber,
    db,
    utc_now,
)
from services import parse_special_text, slugify
from storage import UploadError, save_special_photo


load_dotenv()
LOCAL_TZ = ZoneInfo("America/Los_Angeles")
METRIC_TYPES = {"view", "directions", "call", "website", "share"}
CHANNELS = ["facebook_page", "facebook_group", "instagram", "email", "other"]
LEAD_STATUSES = {"new", "contacted", "converted", "closed"}


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
    APP_BASE_URL=os.environ.get("APP_BASE_URL", "http://127.0.0.1:5000"),
    EMAIL_TEST_ENABLED=os.environ.get("EMAIL_TEST_ENABLED") == "1",
    EMAIL_TEST_RECIPIENT=os.environ.get("EMAIL_TEST_RECIPIENT", "ian.larsen.1976@gmail.com"),
    RESEND_WEBHOOK_SECRET=os.environ.get("RESEND_WEBHOOK_SECRET"),
    OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY"),
    OPENAI_OUTREACH_MODEL=os.environ.get("OPENAI_OUTREACH_MODEL", "gpt-5.4-mini"),
    GOOGLE_PLACES_API_KEY=os.environ.get("GOOGLE_PLACES_API_KEY"),
)
db.init_app(app)
migrate = Migrate(app, db)


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
            "restaurant_welcome",
            "sales_outreach",
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
    if request.method == "POST" and request.endpoint not in {"admin_login", "resend_webhook"}:
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
        or_(Special.starts_at.is_(None), Special.starts_at <= now),
        or_(Special.expires_at.is_(None), Special.expires_at >= now),
    )


def restaurant_search_filter(search_term):
    pattern = f"%{search_term}%"
    return or_(
        Restaurant.name.ilike(pattern),
        Restaurant.city.ilike(pattern),
        Restaurant.full_address.ilike(pattern),
        Restaurant.street.ilike(pattern),
        Restaurant.category.ilike(pattern),
        Restaurant.subtypes.ilike(pattern),
    )


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
    if favorite_tag:
        tags = {tag.strip() for tag in (subscriber.favorite_tags or "").split(",") if tag.strip()}
        tags.add(favorite_tag)
        subscriber.favorite_tags = ",".join(sorted(tags))
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


def set_special_schedule(special):
    date_value = request.form["special_date"]
    special.starts_at = parse_local_datetime(date_value, request.form.get("start_time") or None)
    special.expires_at = parse_local_datetime(
        date_value, request.form.get("end_time") or None, time(23, 59)
    )


def save_photo_if_present(special):
    upload = request.files.get("photo")
    if upload and upload.filename:
        special.photo_object_key, special.photo_url = save_special_photo(app, upload)


def special_from_form(special=None):
    special = special or Special()
    special.restaurant_id = int(request.form["restaurant_id"])
    special.title = request.form["title"].strip()
    special.description = request.form.get("description", "").strip()
    special.price = request.form.get("price", "").strip()
    set_special_schedule(special)
    special.status = request.form.get("status", "draft")
    special.source = request.form.get("source", "manual")
    special.raw_text = request.form.get("raw_text", "").strip() or None
    if special.status == "published" and not special.published_at:
        special.published_at = utc_now()
    save_photo_if_present(special)
    return special


def restaurant_from_form(restaurant=None):
    restaurant = restaurant or Restaurant()
    restaurant.name = request.form["name"].strip()
    restaurant.slug = slugify(request.form.get("slug") or restaurant.name)
    restaurant.city = request.form["city"].strip()
    restaurant.address = request.form.get("address", "").strip()
    restaurant.postal_code = request.form.get("postal_code", "").strip()
    restaurant.us_state = request.form.get("us_state", "").strip()
    restaurant.phone = request.form.get("phone", "").strip()
    restaurant.contact_email = request.form.get("contact_email", "").strip().lower()
    restaurant.website = request.form.get("website", "").strip()
    restaurant.category = request.form.get("category", "").strip()
    restaurant.subtypes = request.form.get("subtypes", "").strip()
    restaurant.claimed = request.form.get("claimed") == "on"
    restaurant.direct_publish_enabled = request.form.get("direct_publish_enabled") == "on"
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


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        location = request.form.get("location", "").strip()
        market, _ = resolve_market(location)
        if email:
            subscribe(email, city=request.form.get("city", "").strip(), location=location)
            if market:
                flash("You're on the early list. Skagit Valley specials alerts are coming soon.")
            else:
                flash(f"You're on the waitlist. We'll let you know when Appertivo reaches {location}.")
        return redirect(url_for("home", location=location))
    location = request.args.get("location", "").strip()
    market, matched_city = resolve_market(location)
    city = request.args.get("city", "").strip()
    if not city and matched_city:
        city = matched_city
    if market:
        query = active_specials_query().filter(Restaurant.city.in_(market["cities"]))
        if city:
            query = query.filter(Restaurant.city.ilike(city))
        specials = query.order_by(Special.published_at.desc(), Special.created_at.desc()).all()
        cities = market["cities"]
    else:
        specials = []
        cities = []
    return render_template(
        "home.html",
        specials=specials,
        cities=cities,
        city=city,
        location=location or SKAGIT_VALLEY["label"],
        market=market,
        map_center=(market or SKAGIT_VALLEY)["center"],
        map_zoom=(market or SKAGIT_VALLEY)["zoom"],
        map_specials=special_map_data(specials),
    )


@app.get("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")


@app.get("/for-restaurants")
def for_restaurants():
    return render_template("for_restaurants.html")


@app.get("/for-diners")
def for_diners():
    return render_template("for_diners.html")


@app.route("/get-started", methods=["GET", "POST"])
def get_started():
    if request.method == "POST":
        fields = {
            name: request.form.get(name, "").strip()
            for name in ["restaurant_name", "contact_name", "email", "phone", "city"]
        }
        if not all(fields.values()):
            flash("Please complete each required field so we can follow up.")
            return render_template("get_started.html", form=request.form), 400
        lead = RestaurantLead(**fields, note=request.form.get("note", "").strip())
        db.session.add(lead)
        db.session.commit()
        return redirect(url_for("get_started", submitted="1"))
    return render_template("get_started.html", submitted=request.args.get("submitted") == "1")


@app.route("/restaurants")
def restaurants():
    city = request.args.get("city", "").strip()
    search_term = request.args.get("q", "").strip()
    query = Restaurant.query
    if city:
        query = query.filter(Restaurant.city.ilike(city))
    if search_term:
        query = query.filter(restaurant_search_filter(search_term))
    items = query.order_by(Restaurant.name).all()
    cities = [row[0] for row in db.session.query(Restaurant.city).distinct().order_by(Restaurant.city)]
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
    items = Restaurant.query.filter(restaurant_search_filter(term)).order_by(Restaurant.name).limit(8)
    return jsonify([{"name": item.name, "location": item.city, "url": url_for("restaurant_detail", slug=item.slug)} for item in items])


@app.route("/restaurants/<slug>", methods=["GET", "POST"])
def restaurant_detail(slug):
    restaurant = Restaurant.query.filter_by(slug=slug).first_or_404()
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
    return render_template("restaurant.html", restaurant=restaurant, specials=specials)


@app.route("/submit/<token>", methods=["GET", "POST"])
def submit_special(token):
    restaurant = Restaurant.query.filter_by(submission_token_hash=hash_token(token)).first_or_404()
    if request.method == "POST":
        special = Special(
            restaurant_id=restaurant.id,
            title=request.form["title"].strip(),
            description=request.form.get("description", "").strip(),
            price=request.form.get("price", "").strip(),
            source="restaurant",
            status="published" if restaurant.direct_publish_enabled else "draft",
            submitted_at=utc_now(),
        )
        set_special_schedule(special)
        if special.status == "published":
            special.published_at = utc_now()
        try:
            save_photo_if_present(special)
        except UploadError as error:
            flash(str(error))
            return render_template("submit.html", restaurant=restaurant), 400
        db.session.add(special)
        db.session.commit()
        return render_template("submit_success.html", restaurant=restaurant, special=special)
    return render_template("submit.html", restaurant=restaurant)


@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_ROOT"], filename)


@app.get("/specials/<public_id>")
def special_detail(public_id):
    special = Special.query.filter_by(public_id=public_id, status="published").first_or_404()
    record_metric(special, "view", request.args.get("channel"))
    return render_template("special.html", special=special)


@app.get("/specials/<public_id>/action/<event_type>")
def special_action(public_id, event_type):
    special = Special.query.filter_by(public_id=public_id, status="published").first_or_404()
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
        "drafts awaiting review": Special.query.filter_by(status="draft").count(),
        "active specials": active_count,
        "undistributed specials": active_specials_query().filter(~Special.id.in_(distributed)).count(),
        "subscribers": Subscriber.query.count(),
        "views": SpecialMetric.query.filter_by(event_type="view").count(),
        "action clicks": SpecialMetric.query.filter(SpecialMetric.event_type != "view").count(),
        "outreach follow-ups": OutreachMessage.query.filter_by(follow_up=True, archived=False).count(),
    }
    return render_template("admin/dashboard.html", counts=counts)


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


@app.route("/admin/outreach", methods=["GET", "POST"])
@admin_required
def admin_outreach():
    if request.method == "POST":
        restaurant_id = request.form.get("restaurant_id") or None
        message = OutreachMessage(
            restaurant_id=int(restaurant_id) if restaurant_id else None,
            sender_email=app.config["EMAIL_FROM_SALES"],
            recipient_email=request.form["recipient_email"].strip().lower(),
            subject=request.form.get("subject", "").strip()
            or "Get your restaurant special in front of local diners",
            body_text=request.form.get("body_text", "").strip(),
            tags=request.form.get("tags", "").strip(),
        )
        db.session.add(message)
        db.session.commit()
        return redirect(url_for("admin_outreach_message", message_id=message.id))
    messages = OutreachMessage.query.filter_by(archived=False).order_by(OutreachMessage.updated_at.desc()).all()
    restaurants = Restaurant.query.order_by(Restaurant.name).all()
    return render_template("admin/outreach.html", messages=messages, restaurants=restaurants)


@app.route("/admin/outreach/<int:message_id>", methods=["GET", "POST"])
@admin_required
def admin_outreach_message(message_id):
    message = OutreachMessage.query.get_or_404(message_id)
    if request.method == "POST" and message.direction == "outbound" and message.status in {"draft", "failed"}:
        message.recipient_email = request.form["recipient_email"].strip().lower()
        message.subject = request.form["subject"].strip()
        message.body_text = request.form["body_text"].strip()
        message.tags = request.form.get("tags", "").strip()
        db.session.commit()
        flash("Draft saved.")
        return redirect(url_for("admin_outreach_message", message_id=message.id))
    return render_template("admin/outreach_message.html", message=message)


@app.post("/admin/outreach/<int:message_id>/generate")
@admin_required
def admin_outreach_generate(message_id):
    from email_system.openai_client import generate_outreach_draft

    message = OutreachMessage.query.get_or_404(message_id)
    if message.direction != "outbound" or not message.restaurant:
        abort(400, "Choose a restaurant before generating a draft.")
    result = generate_outreach_draft(message.restaurant, request.form.get("instruction", "").strip())
    if result["success"]:
        message.body_text = result["text"]
        db.session.commit()
        flash("OpenAI draft generated. Review it before sending.")
    else:
        flash(f"Draft generation failed: {result['error']}")
    return redirect(url_for("admin_outreach_message", message_id=message.id))


@app.post("/admin/outreach/<int:message_id>/send")
@admin_required
def admin_outreach_send(message_id):
    from email_system.outreach_service import send_outreach_message

    message = OutreachMessage.query.get_or_404(message_id)
    if message.direction != "outbound" or message.status not in {"draft", "failed"}:
        abort(400)
    result = send_outreach_message(message)
    flash("Outreach email sent." if result["success"] else f"Send failed: {result['error']}")
    return redirect(url_for("admin_outreach_message", message_id=message.id))


@app.post("/admin/outreach/<int:message_id>/<action>")
@admin_required
def admin_outreach_action(message_id, action):
    message = OutreachMessage.query.get_or_404(message_id)
    if action == "archive":
        message.archived = True
    elif action == "follow-up":
        message.follow_up = not message.follow_up
    else:
        abort(404)
    db.session.commit()
    return redirect(request.referrer or url_for("admin_outreach"))


@app.post("/api/webhooks/resend")
def resend_webhook():
    from email_system.outreach_service import receive_resend_email

    try:
        receive_resend_email(
            request.get_data(as_text=True),
            {
                "id": request.headers.get("svix-id"),
                "timestamp": request.headers.get("svix-timestamp"),
                "signature": request.headers.get("svix-signature"),
            },
        )
    except ValueError as error:
        abort(400, str(error))
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
    query = Restaurant.query
    if term:
        query = query.filter(restaurant_search_filter(term))
    return render_template("admin/restaurants.html", restaurants=query.order_by(Restaurant.name).all(), search_term=term)


@app.get("/admin/restaurant-enrichment")
@admin_required
def admin_restaurant_enrichment():
    restaurants = (
        Restaurant.query.filter(
            Restaurant.place_id.isnot(None),
            Restaurant.place_id != "",
            Restaurant.google_place_refreshed_at.is_(None),
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
    db.session.commit()


@app.post("/admin/restaurants/<int:restaurant_id>/enhance")
@admin_required
def admin_enhance_restaurant(restaurant_id):
    api_key = validate_restaurant_enrichment_request()
    if not api_key:
        return redirect(url_for("admin_restaurant_enrichment"))
    restaurant = Restaurant.query.get_or_404(restaurant_id)
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
    restaurant_ids = request.form.getlist("restaurant_ids")
    if not restaurant_ids:
        abort(400, "Select at least one restaurant to enhance.")
    restaurants = (
        Restaurant.query.filter(
            Restaurant.id.in_(restaurant_ids),
            Restaurant.place_id.isnot(None),
            Restaurant.place_id != "",
            Restaurant.google_place_refreshed_at.is_(None),
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


@app.route("/admin/restaurants/<int:restaurant_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    if request.method == "POST":
        restaurant_from_form(restaurant)
        db.session.commit()
        flash("Restaurant updated.")
        return redirect(url_for("admin_edit_restaurant", restaurant_id=restaurant.id))
    return render_template("admin/restaurant_form.html", restaurant=restaurant)


@app.post("/admin/restaurants/<int:restaurant_id>/token")
@admin_required
def admin_restaurant_token(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    token = secrets.token_urlsafe(24)
    restaurant.submission_token_hash = hash_token(token)
    db.session.commit()
    submission_url = url_for("submit_special", token=token, _external=True)
    return render_template("admin/token_created.html", restaurant=restaurant, submission_url=submission_url)


@app.post("/admin/restaurants/<int:restaurant_id>/delete")
@admin_required
def admin_delete_restaurant(restaurant_id):
    restaurant = Restaurant.query.get_or_404(restaurant_id)
    db.session.delete(restaurant)
    db.session.commit()
    flash("Restaurant deleted.")
    return redirect(url_for("admin_restaurants"))


@app.get("/admin/specials")
@admin_required
def admin_specials():
    status = request.args.get("status", "")
    query = Special.query.join(Restaurant)
    if status in {"draft", "published", "expired"}:
        query = query.filter(Special.status == status)
    return render_template("admin/specials.html", specials=query.order_by(Special.created_at.desc()).all(), status=status)


@app.route("/admin/specials/new", methods=["GET", "POST"])
@admin_required
def admin_new_special():
    if request.method == "POST":
        try:
            db.session.add(special_from_form())
            db.session.commit()
        except UploadError as error:
            flash(str(error))
            return redirect(url_for("admin_new_special"))
        return redirect(url_for("admin_specials"))
    return render_template("admin/special_form.html", restaurants=Restaurant.query.order_by(Restaurant.name), special=Special(status="published", source="manual"))


@app.route("/admin/specials/<int:special_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_special(special_id):
    special = Special.query.get_or_404(special_id)
    if request.method == "POST":
        try:
            special_from_form(special)
            db.session.commit()
        except UploadError as error:
            flash(str(error))
        return redirect(url_for("admin_edit_special", special_id=special.id))
    return render_template("admin/special_form.html", restaurants=Restaurant.query.order_by(Restaurant.name), special=special)


@app.post("/admin/specials/<int:special_id>/<action>")
@admin_required
def admin_special_action(special_id, action):
    special = Special.query.get_or_404(special_id)
    if action == "approve":
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
    return redirect(request.referrer or url_for("admin_specials"))


@app.route("/admin/specials/<int:special_id>/distribution", methods=["GET", "POST"])
@admin_required
def admin_distribution(special_id):
    special = Special.query.get_or_404(special_id)
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
    restaurants = Restaurant.query.order_by(Restaurant.name).all()
    draft = None
    if request.method == "POST":
        raw_text = request.form["raw_text"].strip()
        parsed = parse_special_text(raw_text)
        if request.form.get("save") == "1":
            special = Special(
                restaurant_id=int(request.form["restaurant_id"]),
                title=request.form["title"].strip(),
                description=request.form.get("description", "").strip(),
                price=request.form.get("price", "").strip(),
                raw_text=raw_text,
                status="draft",
                source="intake",
                submitted_at=utc_now(),
            )
            special.expires_at = parse_local_datetime(request.form["special_date"], default_time=time(23, 59))
            db.session.add(special)
            db.session.commit()
            return redirect(url_for("admin_specials", status="draft"))
        draft = {"raw_text": raw_text, "restaurant_id": int(request.form["restaurant_id"]), **parsed}
    return render_template("admin/intake.html", restaurants=restaurants, draft=draft)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1", threaded=True, use_reloader=False)
