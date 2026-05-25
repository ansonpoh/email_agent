"""Remove user_rules table

Revision ID: 0006_remove_user_rules
Revises: 0005_digest_schedule_count
Create Date: 2026-05-26 00:30:00
"""

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_remove_user_rules"
down_revision = "0005_digest_schedule_count"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def _q(table: str) -> str:
    return f'"{SCHEMA}"."{table}"'


def upgrade() -> None:
    op.execute(sa.text(f'ALTER TABLE {_q("user_rules")} DROP CONSTRAINT IF EXISTS user_rules_user_id_fkey'))
    op.drop_index("ix_user_rules_user_id", table_name="user_rules", schema=SCHEMA)
    op.drop_index("ix_user_rules_id", table_name="user_rules", schema=SCHEMA)
    op.drop_table("user_rules", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "user_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name="user_rules_user_id_fkey",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_user_rules_id", "user_rules", ["id"], schema=SCHEMA)
    op.create_index("ix_user_rules_user_id", "user_rules", ["user_id"], schema=SCHEMA)
