"""add outreach campaigns

Revision ID: 20260602_03
Revises: 20260602_02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_03"
down_revision = "20260602_02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outreach_campaign",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("recipient_email", sa.String(length=160), nullable=False),
        sa.Column("contact_name", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(), nullable=True),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("personalized_observation", sa.Text(), nullable=True),
        sa.Column("example_special", sa.Text(), nullable=True),
        sa.Column("personalized_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("restaurant_id", "recipient_email", name="uq_outreach_campaign_restaurant_email"),
    )
    op.create_index("ix_outreach_campaign_restaurant_id", "outreach_campaign", ["restaurant_id"])
    op.create_index("ix_outreach_campaign_recipient_email", "outreach_campaign", ["recipient_email"])
    op.create_index("ix_outreach_campaign_status", "outreach_campaign", ["status"])
    op.create_index("ix_outreach_campaign_current_step", "outreach_campaign", ["current_step"])
    op.create_index("ix_outreach_campaign_next_follow_up_at", "outreach_campaign", ["next_follow_up_at"])
    op.create_index("ix_outreach_campaign_paused", "outreach_campaign", ["paused"])
    op.create_index("ix_outreach_campaign_archived", "outreach_campaign", ["archived"])

    op.create_table(
        "outreach_suppression",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_outreach_suppression_email", "outreach_suppression", ["email"], unique=True)

    with op.batch_alter_table("outreach_message") as batch_op:
        batch_op.add_column(sa.Column("campaign_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("sequence_step", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("template_key", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key("fk_outreach_message_campaign_id", "outreach_campaign", ["campaign_id"], ["id"])
        batch_op.create_index("ix_outreach_message_campaign_id", ["campaign_id"])
        batch_op.create_index("ix_outreach_message_sequence_step", ["sequence_step"])
        batch_op.create_index("ix_outreach_message_template_key", ["template_key"])
        batch_op.create_index("ix_outreach_message_reviewed", ["reviewed"])
        batch_op.create_index("ix_outreach_message_due_at", ["due_at"])

    with op.batch_alter_table("outreach_message") as batch_op:
        batch_op.alter_column("reviewed", server_default=None)


def downgrade():
    with op.batch_alter_table("outreach_message") as batch_op:
        batch_op.drop_index("ix_outreach_message_due_at")
        batch_op.drop_index("ix_outreach_message_reviewed")
        batch_op.drop_index("ix_outreach_message_template_key")
        batch_op.drop_index("ix_outreach_message_sequence_step")
        batch_op.drop_index("ix_outreach_message_campaign_id")
        batch_op.drop_constraint("fk_outreach_message_campaign_id", type_="foreignkey")
        batch_op.drop_column("due_at")
        batch_op.drop_column("reviewed")
        batch_op.drop_column("template_key")
        batch_op.drop_column("sequence_step")
        batch_op.drop_column("campaign_id")

    op.drop_table("outreach_suppression")
    op.drop_table("outreach_campaign")
