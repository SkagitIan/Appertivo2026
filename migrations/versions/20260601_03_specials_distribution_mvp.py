"""add specials distribution mvp

Revision ID: 20260601_03
Revises: 20260601_02
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_03"
down_revision = "20260601_02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.add_column(sa.Column("submission_token_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("direct_publish_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_unique_constraint("uq_restaurant_submission_token_hash", ["submission_token_hash"])

    with op.batch_alter_table("special") as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("photo_object_key", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("photo_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("submitted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("published_at", sa.DateTime(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id FROM special WHERE public_id IS NULL")).fetchall()
    from uuid import uuid4

    for row in rows:
        connection.execute(
            sa.text("UPDATE special SET public_id = :public_id WHERE id = :id"),
            {"public_id": str(uuid4()), "id": row[0]},
        )

    with op.batch_alter_table("special") as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_index("ix_special_public_id", ["public_id"], unique=True)

    op.create_table(
        "distribution_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("special_id", sa.Integer(), sa.ForeignKey("special.id"), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_distribution_log_special_id", "distribution_log", ["special_id"])
    op.create_table(
        "special_metric",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("special_id", sa.Integer(), sa.ForeignKey("special.id"), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_special_metric_special_id", "special_metric", ["special_id"])
    op.create_index("ix_special_metric_event_type", "special_metric", ["event_type"])


def downgrade():
    op.drop_table("special_metric")
    op.drop_table("distribution_log")
    with op.batch_alter_table("special") as batch_op:
        batch_op.drop_index("ix_special_public_id")
        batch_op.drop_column("published_at")
        batch_op.drop_column("submitted_at")
        batch_op.drop_column("photo_url")
        batch_op.drop_column("photo_object_key")
        batch_op.drop_column("public_id")
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.drop_constraint("uq_restaurant_submission_token_hash", type_="unique")
        batch_op.drop_column("direct_publish_enabled")
        batch_op.drop_column("submission_token_hash")
