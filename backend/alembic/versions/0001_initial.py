"""Initial schema for Gmail assistant MVP

Revision ID: 0001_initial
Revises: 
Create Date: 2026-05-24 22:30:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("google_user_id", sa.String(length=255), nullable=False),
        sa.Column("encrypted_access_token", sa.String(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.String(), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_google_user_id", "users", ["google_user_id"], unique=True)

    op.create_table(
        "emails",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=False),
        sa.Column("sender_email", sa.String(length=320), nullable=False),
        sa.Column("sender_name", sa.String(length=255), nullable=True),
        sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subject", sa.String(length=998), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_emails_id", "emails", ["id"])
    op.create_index("ix_emails_user_id", "emails", ["user_id"])
    op.create_index("ix_emails_gmail_message_id", "emails", ["gmail_message_id"])
    op.create_index("ix_emails_gmail_thread_id", "emails", ["gmail_thread_id"])

    op.create_table(
        "email_analysis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extracted_tasks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extracted_deadlines", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("suggested_action", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email_id", name="uq_email_analysis_email_id"),
    )
    op.create_index("ix_email_analysis_id", "email_analysis", ["id"])

    op.create_table(
        "agent_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("suggested_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approved_by_user", sa.Boolean(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_actions_id", "agent_actions", ["id"])
    op.create_index("ix_agent_actions_email_id", "agent_actions", ["email_id"])

    op.create_table(
        "draft_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email_id", sa.Integer(), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False),
        sa.Column("draft_body", sa.Text(), nullable=False),
        sa.Column("tone", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("gmail_draft_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_draft_replies_id", "draft_replies", ["id"])
    op.create_index("ix_draft_replies_email_id", "draft_replies", ["email_id"])

    op.create_table(
        "digests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("digest_text", sa.Text(), nullable=False),
        sa.Column("sent_to_telegram", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_digests_id", "digests", ["id"])
    op.create_index("ix_digests_user_id", "digests", ["user_id"])

    op.create_table(
        "user_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_rules_id", "user_rules", ["id"])
    op.create_index("ix_user_rules_user_id", "user_rules", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_rules_user_id", table_name="user_rules")
    op.drop_index("ix_user_rules_id", table_name="user_rules")
    op.drop_table("user_rules")

    op.drop_index("ix_digests_user_id", table_name="digests")
    op.drop_index("ix_digests_id", table_name="digests")
    op.drop_table("digests")

    op.drop_index("ix_draft_replies_email_id", table_name="draft_replies")
    op.drop_index("ix_draft_replies_id", table_name="draft_replies")
    op.drop_table("draft_replies")

    op.drop_index("ix_agent_actions_email_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_id", table_name="agent_actions")
    op.drop_table("agent_actions")

    op.drop_index("ix_email_analysis_id", table_name="email_analysis")
    op.drop_table("email_analysis")

    op.drop_index("ix_emails_gmail_thread_id", table_name="emails")
    op.drop_index("ix_emails_gmail_message_id", table_name="emails")
    op.drop_index("ix_emails_user_id", table_name="emails")
    op.drop_index("ix_emails_id", table_name="emails")
    op.drop_table("emails")

    op.drop_index("ix_users_google_user_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
