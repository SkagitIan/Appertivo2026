"""add outreach templates

Revision ID: 20260608_00
Revises: 20260606_00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260608_00"
down_revision = "20260606_00"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outreach_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject", sa.String(length=240), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_outreach_template_name", "outreach_template", ["name"], unique=True)
    op.create_index("ix_outreach_template_is_active", "outreach_template", ["is_active"])


def downgrade():
    op.drop_table("outreach_template")
