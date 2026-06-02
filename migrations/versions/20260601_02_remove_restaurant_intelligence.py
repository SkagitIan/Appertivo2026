"""remove restaurant intelligence workflow

Revision ID: 20260601_02
Revises: 20260601_01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_02"
down_revision = "20260601_01"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("newsletter_signup_attempt")
    op.drop_table("restaurant_intel_source")
    op.drop_table("restaurant_intel_snapshot")
    op.drop_table("intelligence_task")
    op.drop_table("intelligence_run")
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.drop_index("ix_restaurant_intelligence_status")
        batch_op.drop_column("intelligence_updated_at")
        batch_op.drop_column("intelligence_needs_review")
        batch_op.drop_column("intelligence_status")
        batch_op.drop_column("enriched_at")


def downgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.add_column(sa.Column("enriched_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("intelligence_status", sa.String(length=30), nullable=False, server_default="never")
        )
        batch_op.add_column(
            sa.Column("intelligence_needs_review", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("intelligence_updated_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_restaurant_intelligence_status", ["intelligence_status"])

    op.create_table(
        "intelligence_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("worker_count", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_intelligence_run_status", "intelligence_run", ["status"])
    op.create_table(
        "intelligence_task",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("intelligence_run.id"), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("research_attempts", sa.Integer(), nullable=False),
        sa.Column("signup_attempts", sa.Integer(), nullable=False),
        sa.Column("trace_id", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_intelligence_task_run_id", "intelligence_task", ["run_id"])
    op.create_index("ix_intelligence_task_restaurant_id", "intelligence_task", ["restaurant_id"])
    op.create_index("ix_intelligence_task_status", "intelligence_task", ["status"])
    op.create_table(
        "restaurant_intel_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("intelligence_task.id"), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("research_output", sa.JSON(), nullable=True),
        sa.Column("browser_output", sa.JSON(), nullable=True),
        sa.Column("validation_output", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("proposed_updates", sa.JSON(), nullable=True),
        sa.Column("applied_updates", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_restaurant_intel_snapshot_task_id", "restaurant_intel_snapshot", ["task_id"])
    op.create_index("ix_restaurant_intel_snapshot_restaurant_id", "restaurant_intel_snapshot", ["restaurant_id"])
    op.create_table(
        "restaurant_intel_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("intelligence_task.id"), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("official_match", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_restaurant_intel_source_task_id", "restaurant_intel_source", ["task_id"])
    op.create_index("ix_restaurant_intel_source_restaurant_id", "restaurant_intel_source", ["restaurant_id"])
    op.create_table(
        "newsletter_signup_attempt",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("intelligence_task.id"), nullable=False),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("submitted_fields", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("success_message", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_newsletter_signup_attempt_task_id", "newsletter_signup_attempt", ["task_id"])
    op.create_index("ix_newsletter_signup_attempt_restaurant_id", "newsletter_signup_attempt", ["restaurant_id"])
