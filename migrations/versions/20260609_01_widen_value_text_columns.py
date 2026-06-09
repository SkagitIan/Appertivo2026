"""widen value_text and add_on_value_text from varchar(80) to varchar(200)

Revision ID: 20260609_01
Revises: 20260609_00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260609_01"
down_revision = "20260609_00"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("special_draft", "value_text",
                    existing_type=sa.String(80),
                    type_=sa.String(200),
                    existing_nullable=True)
    op.alter_column("special_draft", "add_on_value_text",
                    existing_type=sa.String(80),
                    type_=sa.String(200),
                    existing_nullable=True)
    op.alter_column("special", "value_text",
                    existing_type=sa.String(80),
                    type_=sa.String(200),
                    existing_nullable=True)
    op.alter_column("special", "add_on_value_text",
                    existing_type=sa.String(80),
                    type_=sa.String(200),
                    existing_nullable=True)


def downgrade():
    op.alter_column("special", "add_on_value_text",
                    existing_type=sa.String(200),
                    type_=sa.String(80),
                    existing_nullable=True)
    op.alter_column("special", "value_text",
                    existing_type=sa.String(200),
                    type_=sa.String(80),
                    existing_nullable=True)
    op.alter_column("special_draft", "add_on_value_text",
                    existing_type=sa.String(200),
                    type_=sa.String(80),
                    existing_nullable=True)
    op.alter_column("special_draft", "value_text",
                    existing_type=sa.String(200),
                    type_=sa.String(80),
                    existing_nullable=True)
