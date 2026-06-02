"""baseline existing appertivo schema

Revision ID: 20260601_00
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_00"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "restaurant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=240), nullable=False, unique=True),
        sa.Column("full_address", sa.String(length=300), nullable=True),
        sa.Column("street", sa.String(length=200), nullable=True),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("postal_code", sa.String(length=12), nullable=True),
        sa.Column("us_state", sa.String(length=40), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("site", sa.String(length=500), nullable=True),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("type", sa.String(length=120), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("subtypes", sa.Text(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("reviews", sa.Integer(), nullable=True),
        sa.Column("business_status", sa.String(length=40), nullable=True),
        sa.Column("working_hours", sa.JSON(), nullable=True),
        sa.Column("google_id", sa.String(length=120), nullable=True),
        sa.Column("place_id", sa.String(length=120), nullable=True, unique=True),
        sa.Column("reviews_link", sa.Text(), nullable=True),
        sa.Column("photo", sa.Text(), nullable=True),
        sa.Column("query", sa.String(length=200), nullable=True),
        sa.Column("scraped_zip", sa.String(length=12), nullable=True),
        sa.Column("source", sa.String(length=80), nullable=True),
        sa.Column("claimed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_restaurant_name", "restaurant", ["name"])
    op.create_index("ix_restaurant_city", "restaurant", ["city"])
    op.create_index("ix_restaurant_postal_code", "restaurant", ["postal_code"])
    op.create_index("ix_restaurant_city_name", "restaurant", ["city", "name"])
    op.create_index("ix_restaurant_coordinates", "restaurant", ["latitude", "longitude"])
    op.create_table(
        "subscriber",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=160), nullable=False, unique=True),
        sa.Column("city", sa.String(length=80), nullable=True),
        sa.Column("favorite_tags", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "special",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.String(length=40), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table("special")
    op.drop_table("subscriber")
    op.drop_table("restaurant")
