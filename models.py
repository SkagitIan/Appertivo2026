from datetime import UTC, datetime
from uuid import uuid4

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


class Restaurant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    slug = db.Column(db.String(240), nullable=False, unique=True)
    full_address = db.Column(db.String(300), default="")
    street = db.Column(db.String(200), default="")
    city = db.Column(db.String(80), nullable=False, index=True)
    postal_code = db.Column(db.String(12), default="", index=True)
    us_state = db.Column(db.String(40), default="")
    country = db.Column(db.String(80), default="")
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    site = db.Column(db.String(500), default="")
    phone = db.Column(db.String(40), default="")
    contact_email = db.Column(db.String(160), default="", index=True)
    type = db.Column(db.String(120), default="")
    category = db.Column(db.String(120), default="")
    subtypes = db.Column(db.Text, default="")
    rating = db.Column(db.Float, nullable=True)
    reviews = db.Column(db.Integer, nullable=True)
    business_status = db.Column(db.String(40), default="")
    working_hours = db.Column(db.JSON, nullable=True)
    google_id = db.Column(db.String(120), default="")
    place_id = db.Column(db.String(120), nullable=True, unique=True)
    reviews_link = db.Column(db.Text, default="")
    photo = db.Column(db.Text, default="")
    source_query = db.Column("query", db.String(200), default="")
    scraped_zip = db.Column(db.String(12), default="")
    source = db.Column(db.String(80), default="")
    claimed = db.Column(db.Boolean, default=False, nullable=False)
    submission_token_hash = db.Column(db.String(64), nullable=True, unique=True)
    direct_publish_enabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    specials = db.relationship("Special", back_populates="restaurant", cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("ix_restaurant_city_name", "city", "name"),
        db.Index("ix_restaurant_coordinates", "latitude", "longitude"),
    )

    @property
    def address(self):
        return self.full_address or self.street

    @address.setter
    def address(self, value):
        self.full_address = value
        self.street = value

    @property
    def website(self):
        return self.site

    @website.setter
    def website(self, value):
        self.site = value


class Special(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.String(40), default="")
    starts_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="draft", nullable=False)
    source = db.Column(db.String(20), default="manual", nullable=False)
    raw_text = db.Column(db.Text, nullable=True)
    public_id = db.Column(db.String(36), default=lambda: str(uuid4()), nullable=False, unique=True, index=True)
    photo_object_key = db.Column(db.String(500), nullable=True)
    photo_url = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    restaurant = db.relationship("Restaurant", back_populates="specials")
    distribution_logs = db.relationship(
        "DistributionLog", back_populates="special", cascade="all, delete-orphan"
    )
    metrics = db.relationship("SpecialMetric", back_populates="special", cascade="all, delete-orphan")


class DistributionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    special_id = db.Column(db.Integer, db.ForeignKey("special.id"), nullable=False, index=True)
    channel = db.Column(db.String(40), nullable=False)
    note = db.Column(db.Text, default="")
    posted_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    special = db.relationship("Special", back_populates="distribution_logs")


class SpecialMetric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    special_id = db.Column(db.Integer, db.ForeignKey("special.id"), nullable=False, index=True)
    event_type = db.Column(db.String(20), nullable=False, index=True)
    channel = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    special = db.relationship("Special", back_populates="metrics")


class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), nullable=False, unique=True)
    city = db.Column(db.String(80), nullable=True)
    location = db.Column(db.String(160), nullable=True)
    favorite_tags = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class RestaurantLead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_name = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(160), nullable=False, index=True)
    phone = db.Column(db.String(40), nullable=False)
    city = db.Column(db.String(80), nullable=False, index=True)
    note = db.Column(db.Text, default="")
    status = db.Column(db.String(20), default="new", nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class OutreachMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=True, index=True)
    direction = db.Column(db.String(20), nullable=False, default="outbound", index=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    sender_email = db.Column(db.String(160), nullable=False)
    recipient_email = db.Column(db.String(160), nullable=False, index=True)
    subject = db.Column(db.String(240), nullable=False, default="")
    body_text = db.Column(db.Text, nullable=False, default="")
    tags = db.Column(db.String(300), nullable=False, default="")
    follow_up = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    provider = db.Column(db.String(40), nullable=True)
    provider_message_id = db.Column(db.String(160), nullable=True, index=True)
    external_email_id = db.Column(db.String(160), nullable=True, unique=True)
    in_reply_to = db.Column(db.String(500), nullable=True)
    error = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    restaurant = db.relationship("Restaurant")
