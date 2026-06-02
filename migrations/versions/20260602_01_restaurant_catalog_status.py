"""add restaurant catalog status

Revision ID: 20260602_01
Revises: 20260602_00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260602_01"
down_revision = "20260602_00"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.add_column(
            sa.Column("catalog_status", sa.String(length=20), nullable=False, server_default="included")
        )
        batch_op.add_column(sa.Column("catalog_reason", sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column("catalog_reviewed_at", sa.DateTime(), nullable=True))
        batch_op.create_index("ix_restaurant_catalog_status", ["catalog_status"])


def downgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.drop_index("ix_restaurant_catalog_status")
        batch_op.drop_column("catalog_reviewed_at")
        batch_op.drop_column("catalog_reason")
        batch_op.drop_column("catalog_status")
