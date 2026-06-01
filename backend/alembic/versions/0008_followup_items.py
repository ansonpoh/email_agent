"""Add followup item tracking

Revision ID: 0008_followup_items
Revises: 0007_direct_email_watch_events
Create Date: 2026-06-01 12:10:00
"""

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_followup_items"
down_revision = "0007_direct_email_watch_events"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def upgrade() -> None:
    op.create_table(
        "followup_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_text", sa.Text(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_label", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'open'")),
        sa.Column("needs_reply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority_score", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], [f"{SCHEMA}.emails.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index("ix_followup_items_id", "followup_items", ["id"], schema=SCHEMA)
    op.create_index("ix_followup_items_user_id", "followup_items", ["user_id"], schema=SCHEMA)
    op.create_index("ix_followup_items_email_id", "followup_items", ["email_id"], schema=SCHEMA)
    op.create_index("ix_followup_items_due_at", "followup_items", ["due_at"], schema=SCHEMA)
    op.create_index("ix_followup_items_status", "followup_items", ["status"], schema=SCHEMA)

    op.alter_column("followup_items", "status", server_default=None, schema=SCHEMA)
    op.alter_column("followup_items", "needs_reply", server_default=None, schema=SCHEMA)
    op.alter_column("followup_items", "priority_score", server_default=None, schema=SCHEMA)
    op.alter_column("followup_items", "confidence_score", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_followup_items_status", table_name="followup_items", schema=SCHEMA)
    op.drop_index("ix_followup_items_due_at", table_name="followup_items", schema=SCHEMA)
    op.drop_index("ix_followup_items_email_id", table_name="followup_items", schema=SCHEMA)
    op.drop_index("ix_followup_items_user_id", table_name="followup_items", schema=SCHEMA)
    op.drop_index("ix_followup_items_id", table_name="followup_items", schema=SCHEMA)
    op.drop_table("followup_items", schema=SCHEMA)

