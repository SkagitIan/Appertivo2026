"""add subscriber unsubscribe fields

Revision ID: 20260602_04
Revises: 20260602_03
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_04"
down_revision = "20260602_03"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.add_column(sa.Column("is_subscribed", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column("unsubscribed_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_subscriber_is_subscribed", ["is_subscribed"])
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.alter_column("is_subscribed", server_default=None)


def downgrade():
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.drop_index("ix_subscriber_is_subscribed")
        batch_op.drop_column("unsubscribed_at")
        batch_op.drop_column("is_subscribed")
