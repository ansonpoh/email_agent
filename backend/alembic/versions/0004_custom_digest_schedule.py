"""Add custom digest schedule toggle and times

Revision ID: 0004_custom_digest_schedule
Revises: 0003_telegram_first
Create Date: 2026-05-25 21:10:00
"""

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0004_custom_digest_schedule"
down_revision = "0003_telegram_first"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("scheduled_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )
    op.add_column(
        "users",
        sa.Column(
            "digest_schedule_times",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema=SCHEMA,
    )

    op.alter_column("users", "scheduled_digest_enabled", server_default=None, schema=SCHEMA)
    op.alter_column("users", "digest_schedule_times", server_default=None, schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("users", "digest_schedule_times", schema=SCHEMA)
    op.drop_column("users", "scheduled_digest_enabled", schema=SCHEMA)
