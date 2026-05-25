"""Add digest schedule count

Revision ID: 0005_digest_schedule_count
Revises: 0004_custom_digest_schedule
Create Date: 2026-05-25 23:10:00
"""

import os

from alembic import op
import sqlalchemy as sa


revision = "0005_digest_schedule_count"
down_revision = "0004_custom_digest_schedule"
branch_labels = None
depends_on = None
SCHEMA = os.getenv("DATABASE_SCHEMA", "email_agent")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("digest_schedule_count", sa.Integer(), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_users_digest_schedule_count_1_3",
        "users",
        "digest_schedule_count IS NULL OR (digest_schedule_count >= 1 AND digest_schedule_count <= 3)",
        schema=SCHEMA,
    )
    op.execute(
        sa.text(
            f"""
            UPDATE "{SCHEMA}"."users"
            SET digest_schedule_count = jsonb_array_length(digest_schedule_times)
            WHERE jsonb_typeof(digest_schedule_times) = 'array'
              AND jsonb_array_length(digest_schedule_times) BETWEEN 1 AND 3
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_digest_schedule_count_1_3", "users", type_="check", schema=SCHEMA)
    op.drop_column("users", "digest_schedule_count", schema=SCHEMA)
