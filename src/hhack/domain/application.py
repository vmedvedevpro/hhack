"""Persistence model for a generated cover letter / planned application.

One row per ``(job, prompt_hash)`` — Phase 4 only fills the drafting
fields and leaves ``status='draft'``. Phase 5 will flip the row to
``pending`` / ``sent`` / ``failed`` and stamp ``sent_at`` /
``hh_response_id`` once the apply flow lands.

``resume_id`` records which resume slot the letter was written for —
typically the one with the highest match score, but stored on the
application itself so Phase 5 can wire the right resume into HH's
apply form.

``prompt_hash`` is the idempotency anchor. Bumping ``LETTER_VERSION``
or editing ``LETTER_RULES`` produces a new hash so a re-scan generates
a fresh draft instead of being skipped — the old draft stays in the
table for comparison.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from hhack.domain.base import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    resume_id: Mapped[str] = mapped_column(String(64), nullable=False)

    cover_letter: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="draft")
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_creation_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hh_response_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", "prompt_hash", name="uq_applications_job_prompt"),
        Index("ix_applications_job_id", "job_id"),
        Index("ix_applications_status", "status"),
    )
