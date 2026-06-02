"""add outreach inbox

Revision ID: 20260601_06
Revises: 20260601_05
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_06"
down_revision = "20260601_05"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.add_column(sa.Column("contact_email", sa.String(length=160), nullable=True))
        batch_op.create_index("ix_restaurant_contact_email", ["contact_email"])

    op.create_table(
        "outreach_message",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sender_email", sa.String(length=160), nullable=False),
        sa.Column("recipient_email", sa.String(length=160), nullable=False),
        sa.Column("subject", sa.String(length=240), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("tags", sa.String(length=300), nullable=False),
        sa.Column("follow_up", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("provider_message_id", sa.String(length=160), nullable=True),
        sa.Column("external_email_id", sa.String(length=160), nullable=True),
        sa.Column("in_reply_to", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_outreach_message_restaurant_id", "outreach_message", ["restaurant_id"])
    op.create_index("ix_outreach_message_direction", "outreach_message", ["direction"])
    op.create_index("ix_outreach_message_status", "outreach_message", ["status"])
    op.create_index("ix_outreach_message_recipient_email", "outreach_message", ["recipient_email"])
    op.create_index("ix_outreach_message_follow_up", "outreach_message", ["follow_up"])
    op.create_index("ix_outreach_message_archived", "outreach_message", ["archived"])
    op.create_index("ix_outreach_message_provider_message_id", "outreach_message", ["provider_message_id"])
    op.create_index("ix_outreach_message_external_email_id", "outreach_message", ["external_email_id"], unique=True)


def downgrade():
    op.drop_table("outreach_message")
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.drop_index("ix_restaurant_contact_email")
        batch_op.drop_column("contact_email")
