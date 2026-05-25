"""Add Telegram-first workflow fields and scheduled run tracking

Revision ID: 0003_telegram_first
Revises: 0002_uuid_ids
Create Date: 2026-05-25 16:30:00
"""

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_telegram_first"
down_revision = "0002_uuid_ids"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_link_token_hash", sa.String(length=128), nullable=True), schema=SCHEMA)
    op.add_column("users", sa.Column("telegram_link_token_expires_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column("users", sa.Column("digest_frequency", sa.String(length=32), nullable=False, server_default="hourly"), schema=SCHEMA)
    op.add_column("users", sa.Column("urgent_alerts_enabled", sa.Boolean(), nullable=False, server_default=sa.true()), schema=SCHEMA)
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"), schema=SCHEMA)
    op.create_index("ix_users_telegram_link_token_hash", "users", ["telegram_link_token_hash"], schema=SCHEMA)

    op.add_column("email_analysis", sa.Column("urgent_alert_sent", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)

    op.add_column("agent_actions", sa.Column("execution_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")), schema=SCHEMA)
    op.add_column("agent_actions", sa.Column("execution_error", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("agent_actions", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True), schema=SCHEMA)
    op.add_column("agent_actions", sa.Column("telegram_message_id", sa.String(length=64), nullable=True), schema=SCHEMA)
    op.add_column("agent_actions", sa.Column("telegram_callback_data", sa.String(length=64), nullable=True), schema=SCHEMA)
    op.add_column("agent_actions", sa.Column("telegram_callback_handled_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)

    op.create_table(
        "scheduled_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("run_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_type", "run_key", name="uq_scheduled_runs_job_type_run_key"),
        schema=SCHEMA,
    )
    op.create_index("ix_scheduled_runs_id", "scheduled_runs", ["id"], schema=SCHEMA)
    op.create_index("ix_scheduled_runs_user_id", "scheduled_runs", ["user_id"], schema=SCHEMA)
    op.create_index("ix_scheduled_runs_job_type", "scheduled_runs", ["job_type"], schema=SCHEMA)
    op.create_index("ix_scheduled_runs_run_key", "scheduled_runs", ["run_key"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_scheduled_runs_run_key", table_name="scheduled_runs", schema=SCHEMA)
    op.drop_index("ix_scheduled_runs_job_type", table_name="scheduled_runs", schema=SCHEMA)
    op.drop_index("ix_scheduled_runs_user_id", table_name="scheduled_runs", schema=SCHEMA)
    op.drop_index("ix_scheduled_runs_id", table_name="scheduled_runs", schema=SCHEMA)
    op.drop_table("scheduled_runs", schema=SCHEMA)

    op.drop_column("agent_actions", "telegram_callback_handled_at", schema=SCHEMA)
    op.drop_column("agent_actions", "telegram_callback_data", schema=SCHEMA)
    op.drop_column("agent_actions", "telegram_message_id", schema=SCHEMA)
    op.drop_column("agent_actions", "telegram_chat_id", schema=SCHEMA)
    op.drop_column("agent_actions", "execution_error", schema=SCHEMA)
    op.drop_column("agent_actions", "execution_payload", schema=SCHEMA)

    op.drop_column("email_analysis", "urgent_alert_sent", schema=SCHEMA)

    op.drop_index("ix_users_telegram_link_token_hash", table_name="users", schema=SCHEMA)
    op.drop_column("users", "timezone", schema=SCHEMA)
    op.drop_column("users", "urgent_alerts_enabled", schema=SCHEMA)
    op.drop_column("users", "digest_frequency", schema=SCHEMA)
    op.drop_column("users", "telegram_link_token_expires_at", schema=SCHEMA)
    op.drop_column("users", "telegram_link_token_hash", schema=SCHEMA)
