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
    primary_type = db.Column(db.String(120), default="")
    primary_type_label = db.Column(db.String(160), default="")
    place_types = db.Column(db.JSON, nullable=True)
    google_photos = db.Column(db.JSON, nullable=True)
    adr_format_address = db.Column(db.Text, default="")
    short_formatted_address = db.Column(db.String(300), default="")
    postal_address = db.Column(db.JSON, nullable=True)
    plus_code = db.Column(db.JSON, nullable=True)
    viewport = db.Column(db.JSON, nullable=True)
    timezone = db.Column(db.String(80), default="")
    utc_offset_minutes = db.Column(db.Integer, nullable=True)
    international_phone = db.Column(db.String(40), default="")
    google_maps_uri = db.Column(db.Text, default="")
    google_maps_links = db.Column(db.JSON, nullable=True)
    containing_places = db.Column(db.JSON, nullable=True)
    sub_destinations = db.Column(db.JSON, nullable=True)
    icon_background_color = db.Column(db.String(20), default="")
    icon_mask_base_uri = db.Column(db.Text, default="")
    pure_service_area_business = db.Column(db.Boolean, nullable=True)
    price_level = db.Column(db.String(40), default="")
    price_range = db.Column(db.JSON, nullable=True)
    current_opening_hours = db.Column(db.JSON, nullable=True)
    current_secondary_opening_hours = db.Column(db.JSON, nullable=True)
    regular_opening_hours = db.Column(db.JSON, nullable=True)
    regular_secondary_opening_hours = db.Column(db.JSON, nullable=True)
    hours_text = db.Column(db.Text, default="")
    opening_date = db.Column(db.JSON, nullable=True)
    editorial_summary = db.Column(db.Text, default="")
    top_review = db.Column(db.Text, default="")
    google_review_texts = db.Column(db.JSON, nullable=True)
    google_photo_count = db.Column(db.Integer, nullable=True)
    google_first_photo_ref = db.Column(db.Text, default="")
    payment_options = db.Column(db.JSON, nullable=True)
    parking_options = db.Column(db.JSON, nullable=True)
    accessibility_options = db.Column(db.JSON, nullable=True)
    delivery = db.Column(db.Boolean, nullable=True)
    dine_in = db.Column(db.Boolean, nullable=True)
    takeout = db.Column(db.Boolean, nullable=True)
    reservable = db.Column(db.Boolean, nullable=True)
    serves_breakfast = db.Column(db.Boolean, nullable=True)
    serves_brunch = db.Column(db.Boolean, nullable=True)
    serves_lunch = db.Column(db.Boolean, nullable=True)
    serves_dinner = db.Column(db.Boolean, nullable=True)
    serves_beer = db.Column(db.Boolean, nullable=True)
    serves_wine = db.Column(db.Boolean, nullable=True)
    serves_cocktails = db.Column(db.Boolean, nullable=True)
    serves_coffee = db.Column(db.Boolean, nullable=True)
    serves_dessert = db.Column(db.Boolean, nullable=True)
    serves_vegetarian = db.Column(db.Boolean, nullable=True)
    outdoor_seating = db.Column(db.Boolean, nullable=True)
    live_music = db.Column(db.Boolean, nullable=True)
    good_for_children = db.Column(db.Boolean, nullable=True)
    good_for_groups = db.Column(db.Boolean, nullable=True)
    allows_dogs = db.Column(db.Boolean, nullable=True)
    restroom = db.Column(db.Boolean, nullable=True)
    good_for_watching_sports = db.Column(db.Boolean, nullable=True)
    google_attributions = db.Column(db.JSON, nullable=True)
    google_place_refreshed_at = db.Column(db.DateTime, nullable=True)
    catalog_status = db.Column(db.String(20), default="included", nullable=False, index=True)
    catalog_reason = db.Column(db.String(300), default="")
    catalog_reviewed_at = db.Column(db.DateTime, nullable=True)
    claimed = db.Column(db.Boolean, default=False, nullable=False)
    submission_token_hash = db.Column(db.String(64), nullable=True, unique=True)
    direct_publish_enabled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    specials = db.relationship("Special", back_populates="restaurant", cascade="all, delete-orphan")
    raw_special_submissions = db.relationship(
        "RawSpecialSubmission", back_populates="restaurant", cascade="all, delete-orphan"
    )
    special_drafts = db.relationship(
        "SpecialDraft", back_populates="restaurant", cascade="all, delete-orphan"
    )
    google_reviews = db.relationship(
        "RestaurantGoogleReview", back_populates="restaurant", cascade="all, delete-orphan"
    )
    outreach_campaigns = db.relationship(
        "OutreachCampaign", back_populates="restaurant", cascade="all, delete-orphan"
    )

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


class RestaurantGoogleReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False, index=True)
    google_review_name = db.Column(db.String(300), nullable=False, unique=True)
    rating = db.Column(db.Float, nullable=True)
    text = db.Column(db.JSON, nullable=True)
    original_text = db.Column(db.JSON, nullable=True)
    relative_publish_time = db.Column(db.String(120), default="")
    publish_time = db.Column(db.String(60), default="")
    author_attribution = db.Column(db.JSON, nullable=True)
    flag_content_uri = db.Column(db.Text, default="")
    google_maps_uri = db.Column(db.Text, default="")
    visit_date = db.Column(db.JSON, nullable=True)
    fetched_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="google_reviews")


class RawSpecialSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=True, index=True)
    source_channel = db.Column(db.String(20), nullable=False, index=True)
    raw_text = db.Column(db.Text, nullable=False)
    raw_image_url = db.Column(db.Text, nullable=True)
    raw_image_path = db.Column(db.String(500), nullable=True)
    sender_email = db.Column(db.String(160), nullable=True)
    sender_phone = db.Column(db.String(40), nullable=True)
    source_url = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="received", index=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="raw_special_submissions")
    draft = db.relationship(
        "SpecialDraft", back_populates="raw_submission", cascade="all, delete-orphan", uselist=False
    )


class SpecialDraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raw_submission_id = db.Column(
        db.Integer, db.ForeignKey("raw_special_submission.id"), nullable=False, unique=True
    )
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=True, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    price_text = db.Column(db.String(40), nullable=True)
    availability_text = db.Column(db.String(120), nullable=True)
    cta_text = db.Column(db.String(120), nullable=True)
    image_url = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.String(500), nullable=True)
    ai_generated_image = db.Column(db.Boolean, nullable=False, default=False)
    image_disclaimer = db.Column(db.String(300), nullable=True)
    starts_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    approval_token = db.Column(
        db.String(64), nullable=False, default=lambda: uuid4().hex, unique=True, index=True
    )
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    raw_submission = db.relationship("RawSpecialSubmission", back_populates="draft")
    restaurant = db.relationship("Restaurant", back_populates="special_drafts")
    published_special = db.relationship("Special", back_populates="draft", uselist=False)


class Special(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    draft_id = db.Column(db.Integer, db.ForeignKey("special_draft.id"), nullable=True, unique=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.String(40), default="")
    availability_text = db.Column(db.String(120), nullable=True)
    cta_text = db.Column(db.String(120), nullable=True)
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
    draft = db.relationship("SpecialDraft", back_populates="published_special")
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


class OutreachCampaign(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=False, index=True)
    recipient_email = db.Column(db.String(160), nullable=False, index=True)
    contact_name = db.Column(db.String(160), default="")
    status = db.Column(db.String(30), nullable=False, default="drafting", index=True)
    current_step = db.Column(db.Integer, nullable=False, default=0, index=True)
    last_sent_at = db.Column(db.DateTime, nullable=True)
    next_follow_up_at = db.Column(db.DateTime, nullable=True, index=True)
    paused = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    personalized_observation = db.Column(db.Text, default="")
    example_special = db.Column(db.Text, default="")
    personalized_reason = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    restaurant = db.relationship("Restaurant", back_populates="outreach_campaigns")
    messages = db.relationship(
        "OutreachMessage",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="OutreachMessage.created_at",
    )

    __table_args__ = (
        db.UniqueConstraint("restaurant_id", "recipient_email", name="uq_outreach_campaign_restaurant_email"),
    )


class OutreachSuppression(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(160), nullable=False, unique=True, index=True)
    reason = db.Column(db.String(80), nullable=False, default="opt_out")
    source = db.Column(db.String(80), nullable=False, default="admin")
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)


class OutreachMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("outreach_campaign.id"), nullable=True, index=True)
    restaurant_id = db.Column(db.Integer, db.ForeignKey("restaurant.id"), nullable=True, index=True)
    direction = db.Column(db.String(20), nullable=False, default="outbound", index=True)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    sender_email = db.Column(db.String(160), nullable=False)
    recipient_email = db.Column(db.String(160), nullable=False, index=True)
    subject = db.Column(db.String(240), nullable=False, default="")
    body_text = db.Column(db.Text, nullable=False, default="")
    tags = db.Column(db.String(300), nullable=False, default="")
    sequence_step = db.Column(db.Integer, nullable=True, index=True)
    template_key = db.Column(db.String(40), nullable=True, index=True)
    reviewed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
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
    campaign = db.relationship("OutreachCampaign", back_populates="messages")
