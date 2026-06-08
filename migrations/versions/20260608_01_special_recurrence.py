"""add special recurrence metadata

Revision ID: 20260608_01
Revises: 20260608_00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260608_01"
down_revision = "20260608_00"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("special_draft") as batch_op:
        batch_op.add_column(sa.Column("recurrence_rule", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("recurrence_label", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("recurrence_confidence", sa.String(length=20), nullable=True))

    with op.batch_alter_table("special") as batch_op:
        batch_op.add_column(sa.Column("recurrence_rule", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("recurrence_label", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("recurrence_confidence", sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table("special") as batch_op:
        batch_op.drop_column("recurrence_confidence")
        batch_op.drop_column("recurrence_label")
        batch_op.drop_column("recurrence_rule")

    with op.batch_alter_table("special_draft") as batch_op:
        batch_op.drop_column("recurrence_confidence")
        batch_op.drop_column("recurrence_label")
        batch_op.drop_column("recurrence_rule")
