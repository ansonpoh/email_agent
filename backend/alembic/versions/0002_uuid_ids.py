"""Migrate integer primary/foreign keys to UUID

Revision ID: 0002_uuid_ids
Revises: 0001_initial
Create Date: 2026-05-24 23:20:00
"""

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_uuid_ids"
down_revision = "0001_initial"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def _q(table: str) -> str:
    return f'"{SCHEMA}"."{table}"'


def upgrade() -> None:
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))

    id_tables = [
        "users",
        "emails",
        "email_analysis",
        "agent_actions",
        "draft_replies",
        "digests",
        "user_rules",
    ]
    fk_columns = [
        ("emails", "user_id", "users"),
        ("email_analysis", "email_id", "emails"),
        ("agent_actions", "email_id", "emails"),
        ("draft_replies", "email_id", "emails"),
        ("digests", "user_id", "users"),
        ("user_rules", "user_id", "users"),
    ]

    for table in id_tables:
        op.add_column(
            table,
            sa.Column(
                "id_uuid",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            schema=SCHEMA,
        )

    for table, column, _ in fk_columns:
        op.add_column(table, sa.Column(f"{column}_uuid", postgresql.UUID(as_uuid=True), nullable=True), schema=SCHEMA)

    for table in id_tables:
        op.execute(sa.text(f"UPDATE {_q(table)} SET id_uuid = gen_random_uuid() WHERE id_uuid IS NULL"))

    for table, column, parent_table in fk_columns:
        op.execute(
            sa.text(
                f"""
                UPDATE {_q(table)} child
                SET {column}_uuid = parent.id_uuid
                FROM {_q(parent_table)} parent
                WHERE child.{column} = parent.id
                """
            )
        )

    for table in id_tables:
        op.alter_column(table, "id_uuid", nullable=False, schema=SCHEMA)
    for table, column, _ in fk_columns:
        op.alter_column(table, f"{column}_uuid", nullable=False, schema=SCHEMA)

    op.execute(sa.text(f'ALTER TABLE {_q("emails")} DROP CONSTRAINT IF EXISTS emails_user_id_fkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("email_analysis")} DROP CONSTRAINT IF EXISTS email_analysis_email_id_fkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("agent_actions")} DROP CONSTRAINT IF EXISTS agent_actions_email_id_fkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("draft_replies")} DROP CONSTRAINT IF EXISTS draft_replies_email_id_fkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("digests")} DROP CONSTRAINT IF EXISTS digests_user_id_fkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("user_rules")} DROP CONSTRAINT IF EXISTS user_rules_user_id_fkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("email_analysis")} DROP CONSTRAINT IF EXISTS uq_email_analysis_email_id'))

    op.drop_index("ix_users_id", table_name="users", schema=SCHEMA)
    op.drop_index("ix_emails_id", table_name="emails", schema=SCHEMA)
    op.drop_index("ix_emails_user_id", table_name="emails", schema=SCHEMA)
    op.drop_index("ix_email_analysis_id", table_name="email_analysis", schema=SCHEMA)
    op.drop_index("ix_agent_actions_id", table_name="agent_actions", schema=SCHEMA)
    op.drop_index("ix_agent_actions_email_id", table_name="agent_actions", schema=SCHEMA)
    op.drop_index("ix_draft_replies_id", table_name="draft_replies", schema=SCHEMA)
    op.drop_index("ix_draft_replies_email_id", table_name="draft_replies", schema=SCHEMA)
    op.drop_index("ix_digests_id", table_name="digests", schema=SCHEMA)
    op.drop_index("ix_digests_user_id", table_name="digests", schema=SCHEMA)
    op.drop_index("ix_user_rules_id", table_name="user_rules", schema=SCHEMA)
    op.drop_index("ix_user_rules_user_id", table_name="user_rules", schema=SCHEMA)

    op.execute(sa.text(f'ALTER TABLE {_q("user_rules")} DROP CONSTRAINT IF EXISTS user_rules_pkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("digests")} DROP CONSTRAINT IF EXISTS digests_pkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("draft_replies")} DROP CONSTRAINT IF EXISTS draft_replies_pkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("agent_actions")} DROP CONSTRAINT IF EXISTS agent_actions_pkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("email_analysis")} DROP CONSTRAINT IF EXISTS email_analysis_pkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("emails")} DROP CONSTRAINT IF EXISTS emails_pkey'))
    op.execute(sa.text(f'ALTER TABLE {_q("users")} DROP CONSTRAINT IF EXISTS users_pkey'))

    op.alter_column("users", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("users", "id_uuid", new_column_name="id", schema=SCHEMA)

    op.alter_column("emails", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("emails", "id_uuid", new_column_name="id", schema=SCHEMA)
    op.alter_column("emails", "user_id", new_column_name="user_id_int", schema=SCHEMA)
    op.alter_column("emails", "user_id_uuid", new_column_name="user_id", schema=SCHEMA)

    op.alter_column("email_analysis", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("email_analysis", "id_uuid", new_column_name="id", schema=SCHEMA)
    op.alter_column("email_analysis", "email_id", new_column_name="email_id_int", schema=SCHEMA)
    op.alter_column("email_analysis", "email_id_uuid", new_column_name="email_id", schema=SCHEMA)

    op.alter_column("agent_actions", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("agent_actions", "id_uuid", new_column_name="id", schema=SCHEMA)
    op.alter_column("agent_actions", "email_id", new_column_name="email_id_int", schema=SCHEMA)
    op.alter_column("agent_actions", "email_id_uuid", new_column_name="email_id", schema=SCHEMA)

    op.alter_column("draft_replies", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("draft_replies", "id_uuid", new_column_name="id", schema=SCHEMA)
    op.alter_column("draft_replies", "email_id", new_column_name="email_id_int", schema=SCHEMA)
    op.alter_column("draft_replies", "email_id_uuid", new_column_name="email_id", schema=SCHEMA)

    op.alter_column("digests", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("digests", "id_uuid", new_column_name="id", schema=SCHEMA)
    op.alter_column("digests", "user_id", new_column_name="user_id_int", schema=SCHEMA)
    op.alter_column("digests", "user_id_uuid", new_column_name="user_id", schema=SCHEMA)

    op.alter_column("user_rules", "id", new_column_name="id_int", schema=SCHEMA)
    op.alter_column("user_rules", "id_uuid", new_column_name="id", schema=SCHEMA)
    op.alter_column("user_rules", "user_id", new_column_name="user_id_int", schema=SCHEMA)
    op.alter_column("user_rules", "user_id_uuid", new_column_name="user_id", schema=SCHEMA)

    op.drop_column("emails", "user_id_int", schema=SCHEMA)
    op.drop_column("email_analysis", "email_id_int", schema=SCHEMA)
    op.drop_column("agent_actions", "email_id_int", schema=SCHEMA)
    op.drop_column("draft_replies", "email_id_int", schema=SCHEMA)
    op.drop_column("digests", "user_id_int", schema=SCHEMA)
    op.drop_column("user_rules", "user_id_int", schema=SCHEMA)

    op.drop_column("users", "id_int", schema=SCHEMA)
    op.drop_column("emails", "id_int", schema=SCHEMA)
    op.drop_column("email_analysis", "id_int", schema=SCHEMA)
    op.drop_column("agent_actions", "id_int", schema=SCHEMA)
    op.drop_column("draft_replies", "id_int", schema=SCHEMA)
    op.drop_column("digests", "id_int", schema=SCHEMA)
    op.drop_column("user_rules", "id_int", schema=SCHEMA)

    for table in id_tables:
        op.alter_column(table, "id", server_default=sa.text("gen_random_uuid()"), schema=SCHEMA)

    op.create_primary_key("users_pkey", "users", ["id"], schema=SCHEMA)
    op.create_primary_key("emails_pkey", "emails", ["id"], schema=SCHEMA)
    op.create_primary_key("email_analysis_pkey", "email_analysis", ["id"], schema=SCHEMA)
    op.create_primary_key("agent_actions_pkey", "agent_actions", ["id"], schema=SCHEMA)
    op.create_primary_key("draft_replies_pkey", "draft_replies", ["id"], schema=SCHEMA)
    op.create_primary_key("digests_pkey", "digests", ["id"], schema=SCHEMA)
    op.create_primary_key("user_rules_pkey", "user_rules", ["id"], schema=SCHEMA)

    op.create_foreign_key(
        "emails_user_id_fkey",
        "emails",
        "users",
        ["user_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "email_analysis_email_id_fkey",
        "email_analysis",
        "emails",
        ["email_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "agent_actions_email_id_fkey",
        "agent_actions",
        "emails",
        ["email_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "draft_replies_email_id_fkey",
        "draft_replies",
        "emails",
        ["email_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "digests_user_id_fkey",
        "digests",
        "users",
        ["user_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "user_rules_user_id_fkey",
        "user_rules",
        "users",
        ["user_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )

    op.create_unique_constraint("uq_email_analysis_email_id", "email_analysis", ["email_id"], schema=SCHEMA)

    op.create_index("ix_users_id", "users", ["id"], schema=SCHEMA)
    op.create_index("ix_emails_id", "emails", ["id"], schema=SCHEMA)
    op.create_index("ix_emails_user_id", "emails", ["user_id"], schema=SCHEMA)
    op.create_index("ix_email_analysis_id", "email_analysis", ["id"], schema=SCHEMA)
    op.create_index("ix_agent_actions_id", "agent_actions", ["id"], schema=SCHEMA)
    op.create_index("ix_agent_actions_email_id", "agent_actions", ["email_id"], schema=SCHEMA)
    op.create_index("ix_draft_replies_id", "draft_replies", ["id"], schema=SCHEMA)
    op.create_index("ix_draft_replies_email_id", "draft_replies", ["email_id"], schema=SCHEMA)
    op.create_index("ix_digests_id", "digests", ["id"], schema=SCHEMA)
    op.create_index("ix_digests_user_id", "digests", ["user_id"], schema=SCHEMA)
    op.create_index("ix_user_rules_id", "user_rules", ["id"], schema=SCHEMA)
    op.create_index("ix_user_rules_user_id", "user_rules", ["user_id"], schema=SCHEMA)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for UUID ID migration.")
