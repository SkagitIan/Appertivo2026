"""add google places enrichment fields

Revision ID: 20260602_00
Revises: 20260601_06
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_00"
down_revision = "20260601_06"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.add_column(sa.Column("primary_type", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("primary_type_label", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("place_types", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("google_photos", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("adr_format_address", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("short_formatted_address", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("postal_address", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("plus_code", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("viewport", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("timezone", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("utc_offset_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("international_phone", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("google_maps_uri", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("google_maps_links", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("containing_places", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("sub_destinations", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("icon_background_color", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("icon_mask_base_uri", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("pure_service_area_business", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("price_level", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("price_range", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("current_opening_hours", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("current_secondary_opening_hours", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("regular_opening_hours", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("regular_secondary_opening_hours", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("hours_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("opening_date", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("editorial_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("top_review", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("google_review_texts", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("google_photo_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("google_first_photo_ref", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("payment_options", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("parking_options", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("accessibility_options", sa.JSON(), nullable=True))
        for column in [
            "delivery",
            "dine_in",
            "takeout",
            "reservable",
            "serves_breakfast",
            "serves_brunch",
            "serves_lunch",
            "serves_dinner",
            "serves_beer",
            "serves_wine",
            "serves_cocktails",
            "serves_coffee",
            "serves_dessert",
            "serves_vegetarian",
            "outdoor_seating",
            "live_music",
            "good_for_children",
            "good_for_groups",
            "allows_dogs",
            "restroom",
            "good_for_watching_sports",
        ]:
            batch_op.add_column(sa.Column(column, sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("google_attributions", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("google_place_refreshed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "restaurant_google_review",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("google_review_name", sa.String(length=300), nullable=False, unique=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("text", sa.JSON(), nullable=True),
        sa.Column("original_text", sa.JSON(), nullable=True),
        sa.Column("relative_publish_time", sa.String(length=120), nullable=True),
        sa.Column("publish_time", sa.String(length=60), nullable=True),
        sa.Column("author_attribution", sa.JSON(), nullable=True),
        sa.Column("flag_content_uri", sa.Text(), nullable=True),
        sa.Column("google_maps_uri", sa.Text(), nullable=True),
        sa.Column("visit_date", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_restaurant_google_review_restaurant_id",
        "restaurant_google_review",
        ["restaurant_id"],
    )


def downgrade():
    op.drop_table("restaurant_google_review")
    with op.batch_alter_table("restaurant") as batch_op:
        for column in [
            "google_place_refreshed_at",
            "google_attributions",
            "good_for_watching_sports",
            "restroom",
            "allows_dogs",
            "good_for_groups",
            "good_for_children",
            "live_music",
            "outdoor_seating",
            "serves_vegetarian",
            "serves_dessert",
            "serves_coffee",
            "serves_cocktails",
            "serves_wine",
            "serves_beer",
            "serves_dinner",
            "serves_lunch",
            "serves_brunch",
            "serves_breakfast",
            "reservable",
            "takeout",
            "dine_in",
            "delivery",
            "accessibility_options",
            "parking_options",
            "payment_options",
            "editorial_summary",
            "google_first_photo_ref",
            "google_photo_count",
            "google_review_texts",
            "top_review",
            "opening_date",
            "hours_text",
            "regular_opening_hours",
            "regular_secondary_opening_hours",
            "current_secondary_opening_hours",
            "current_opening_hours",
            "price_range",
            "price_level",
            "pure_service_area_business",
            "icon_mask_base_uri",
            "icon_background_color",
            "sub_destinations",
            "containing_places",
            "google_maps_links",
            "google_maps_uri",
            "international_phone",
            "utc_offset_minutes",
            "timezone",
            "viewport",
            "plus_code",
            "postal_address",
            "short_formatted_address",
            "adr_format_address",
            "google_photos",
            "place_types",
            "primary_type_label",
            "primary_type",
        ]:
            batch_op.drop_column(column)
