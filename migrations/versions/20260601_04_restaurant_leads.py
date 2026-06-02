"""add public restaurant leads

Revision ID: 20260601_04
Revises: 20260601_03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_04"
down_revision = "20260601_03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "restaurant_lead",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_name", sa.String(length=200), nullable=False),
        sa.Column("contact_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_restaurant_lead_email", "restaurant_lead", ["email"])
    op.create_index("ix_restaurant_lead_city", "restaurant_lead", ["city"])
    op.create_index("ix_restaurant_lead_status", "restaurant_lead", ["status"])


def downgrade():
    op.drop_table("restaurant_lead")
