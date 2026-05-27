"""Add direct email watcher event tracking

Revision ID: 0007_direct_email_watch_events
Revises: 0006_remove_user_rules
Create Date: 2026-05-27 15:20:00
"""

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_direct_email_watch_events"
down_revision = "0006_remove_user_rules"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def upgrade() -> None:
    op.create_table(
        "direct_email_watch_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("classification_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("urgency", sa.String(length=16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("suggested_action", sa.Text(), nullable=True),
        sa.Column("reply_intent", sa.Text(), nullable=True),
        sa.Column("draft_preview", sa.Text(), nullable=True),
        sa.Column("gmail_draft_id", sa.String(length=255), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("telegram_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["email_id"], [f"{SCHEMA}.emails.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email_id", name="uq_direct_email_watch_events_email_id"),
        schema=SCHEMA,
    )
    op.create_index("ix_direct_email_watch_events_id", "direct_email_watch_events", ["id"], schema=SCHEMA)
    op.create_index("ix_direct_email_watch_events_email_id", "direct_email_watch_events", ["email_id"], schema=SCHEMA)
    op.create_index("ix_direct_email_watch_events_user_id", "direct_email_watch_events", ["user_id"], schema=SCHEMA)
    op.create_index("ix_direct_email_watch_events_status", "direct_email_watch_events", ["status"], schema=SCHEMA)

    op.alter_column("direct_email_watch_events", "classification_json", server_default=None, schema=SCHEMA)
    op.alter_column("direct_email_watch_events", "telegram_notified", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_direct_email_watch_events_status", table_name="direct_email_watch_events", schema=SCHEMA)
    op.drop_index("ix_direct_email_watch_events_user_id", table_name="direct_email_watch_events", schema=SCHEMA)
    op.drop_index("ix_direct_email_watch_events_email_id", table_name="direct_email_watch_events", schema=SCHEMA)
    op.drop_index("ix_direct_email_watch_events_id", table_name="direct_email_watch_events", schema=SCHEMA)
    op.drop_table("direct_email_watch_events", schema=SCHEMA)
