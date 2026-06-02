"""add unified special intake pipeline

Revision ID: 20260602_02
Revises: 20260602_01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_02"
down_revision = "20260602_01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "raw_special_submission",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=True),
        sa.Column("source_channel", sa.String(length=20), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("raw_image_url", sa.Text(), nullable=True),
        sa.Column("raw_image_path", sa.String(length=500), nullable=True),
        sa.Column("sender_email", sa.String(length=160), nullable=True),
        sa.Column("sender_phone", sa.String(length=40), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_raw_special_submission_restaurant_id", "raw_special_submission", ["restaurant_id"])
    op.create_index("ix_raw_special_submission_source_channel", "raw_special_submission", ["source_channel"])
    op.create_index("ix_raw_special_submission_status", "raw_special_submission", ["status"])
    op.create_table(
        "special_draft",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_submission_id", sa.Integer(), sa.ForeignKey("raw_special_submission.id"), nullable=False, unique=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price_text", sa.String(length=40), nullable=True),
        sa.Column("availability_text", sa.String(length=120), nullable=True),
        sa.Column("cta_text", sa.String(length=120), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("ai_generated_image", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("image_disclaimer", sa.String(length=300), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approval_token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_special_draft_restaurant_id", "special_draft", ["restaurant_id"])
    op.create_index("ix_special_draft_status", "special_draft", ["status"])
    op.create_index("ix_special_draft_approval_token", "special_draft", ["approval_token"], unique=True)
    with op.batch_alter_table("special") as batch_op:
        batch_op.add_column(sa.Column("draft_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("availability_text", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("cta_text", sa.String(length=120), nullable=True))
        batch_op.create_foreign_key("fk_special_draft_id", "special_draft", ["draft_id"], ["id"])
        batch_op.create_unique_constraint("uq_special_draft_id", ["draft_id"])


def downgrade():
    with op.batch_alter_table("special") as batch_op:
        batch_op.drop_constraint("uq_special_draft_id", type_="unique")
        batch_op.drop_constraint("fk_special_draft_id", type_="foreignkey")
        batch_op.drop_column("cta_text")
        batch_op.drop_column("availability_text")
        batch_op.drop_column("draft_id")
    op.drop_table("special_draft")
    op.drop_table("raw_special_submission")
