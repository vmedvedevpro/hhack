"""widen match_results.resume_id to fit HH resume ids.

Phase 3 originally used short slot letters (``a``/``b``). Phase 3.1
replaces them with HH's own 38-character resume ids so the column on
``match_results`` lines up with ``jobs.feed_resume_hint``.

Revision ID: 2_widen_resume_id
Revises: 1_match_results
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2_widen_resume_id"
down_revision: str | Sequence[str] | None = "1_match_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "match_results",
        "resume_id",
        existing_type=sa.String(length=8),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "match_results",
        "resume_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=8),
        existing_nullable=False,
    )
