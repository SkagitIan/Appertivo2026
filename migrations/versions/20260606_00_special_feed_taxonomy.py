"""add special feed taxonomy fields

Revision ID: 20260606_00
Revises: 20260602_04
"""
from alembic import op
import sqlalchemy as sa


revision = "20260606_00"
down_revision = "20260602_04"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.add_column(sa.Column("cuisine_tags", sa.Text(), nullable=True, server_default=""))

    with op.batch_alter_table("special_draft") as batch_op:
        batch_op.add_column(sa.Column("value_text", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("tag_keys", sa.Text(), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("primary_tag", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("add_on_name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("add_on_price", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("add_on_value_text", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("featured_rank", sa.Integer(), nullable=True))
        batch_op.create_index("ix_special_draft_featured_rank", ["featured_rank"])

    with op.batch_alter_table("special") as batch_op:
        batch_op.add_column(sa.Column("value_text", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("tag_keys", sa.Text(), nullable=True, server_default=""))
        batch_op.add_column(sa.Column("primary_tag", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("add_on_name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("add_on_price", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("add_on_value_text", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("featured_rank", sa.Integer(), nullable=True))
        batch_op.create_index("ix_special_featured_rank", ["featured_rank"])

    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.alter_column("cuisine_tags", server_default=None)
    with op.batch_alter_table("special_draft") as batch_op:
        batch_op.alter_column("tag_keys", server_default=None)
    with op.batch_alter_table("special") as batch_op:
        batch_op.alter_column("tag_keys", server_default=None)


def downgrade():
    with op.batch_alter_table("special") as batch_op:
        batch_op.drop_index("ix_special_featured_rank")
        batch_op.drop_column("featured_rank")
        batch_op.drop_column("add_on_value_text")
        batch_op.drop_column("add_on_price")
        batch_op.drop_column("add_on_name")
        batch_op.drop_column("primary_tag")
        batch_op.drop_column("tag_keys")
        batch_op.drop_column("value_text")

    with op.batch_alter_table("special_draft") as batch_op:
        batch_op.drop_index("ix_special_draft_featured_rank")
        batch_op.drop_column("featured_rank")
        batch_op.drop_column("add_on_value_text")
        batch_op.drop_column("add_on_price")
        batch_op.drop_column("add_on_name")
        batch_op.drop_column("primary_tag")
        batch_op.drop_column("tag_keys")
        batch_op.drop_column("value_text")

    with op.batch_alter_table("restaurant") as batch_op:
        batch_op.drop_column("cuisine_tags")

