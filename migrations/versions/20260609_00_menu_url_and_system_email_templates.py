"""add menu_url to restaurant and system_email_template table

Revision ID: 20260609_00
Revises: 20260608_01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260609_00"
down_revision = "20260608_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("restaurant", sa.Column("menu_url", sa.Text(), nullable=True))
    op.create_table(
        "system_email_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("body_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_system_email_template_name", "system_email_template", ["name"], unique=True)
    op.create_index("ix_system_email_template_is_active", "system_email_template", ["is_active"])


def downgrade():
    op.drop_column("restaurant", "menu_url")
    op.drop_table("system_email_template")
