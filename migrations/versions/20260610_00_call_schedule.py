"""add call_schedule table and call_schedule_token to restaurant

Revision ID: 20260610_00
Revises: 20260609_01
"""
from alembic import op
import sqlalchemy as sa


revision = "20260610_00"
down_revision = "20260609_01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("restaurant", sa.Column("call_schedule_token", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_restaurant_call_schedule_token", "restaurant", ["call_schedule_token"])

    op.create_table(
        "call_schedule",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("restaurant_id", sa.Integer, sa.ForeignKey("restaurant.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("call_time", sa.Time, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_called_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_call_schedule_restaurant_id", "call_schedule", ["restaurant_id"])
    op.create_index("ix_call_schedule_is_active", "call_schedule", ["is_active"])


def downgrade():
    op.drop_index("ix_call_schedule_is_active", "call_schedule")
    op.drop_index("ix_call_schedule_restaurant_id", "call_schedule")
    op.drop_table("call_schedule")
    op.drop_constraint("uq_restaurant_call_schedule_token", "restaurant", type_="unique")
    op.drop_column("restaurant", "call_schedule_token")
