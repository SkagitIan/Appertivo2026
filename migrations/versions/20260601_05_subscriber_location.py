"""add subscriber location

Revision ID: 20260601_05
Revises: 20260601_04
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_05"
down_revision = "20260601_04"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.add_column(sa.Column("location", sa.String(length=160), nullable=True))


def downgrade():
    with op.batch_alter_table("subscriber") as batch_op:
        batch_op.drop_column("location")
