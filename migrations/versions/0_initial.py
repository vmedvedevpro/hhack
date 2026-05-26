"""initial schema: jobs table.

Revision ID: 0_initial
Revises:
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hh_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("feed_resume_hint", sa.Text(), nullable=True),
        sa.Column("feed_position", sa.Integer(), nullable=True),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("salary", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="discovered"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("detail_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("hh_id", name="uq_jobs_hh_id"),
    )
    op.create_index("ix_jobs_status", "jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
