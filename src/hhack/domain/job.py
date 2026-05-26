"""Persistence model for a discovered HH vacancy.

A `Job` row is created when we first see a vacancy card in the
personalized feed (status ``discovered``). The detail-fetch step in the
feed worker opens the vacancy page, fills in the long-form fields, and
flips the status to ``detailed``. Later phases extend the lifecycle
with ``matched`` / ``skipped`` / ``applied`` / ``failed``.

Idempotency anchor is ``hh_id`` — the integer at the end of an HH
vacancy URL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from hhack.domain.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hh_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    feed_resume_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    feed_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="discovered", server_default="discovered")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    detail_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_jobs_status", "status"),)
