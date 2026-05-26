"""Job repository — protocol + SQLAlchemy implementation.

Feed-card writes are idempotent on ``hh_id`` (Postgres
``ON CONFLICT DO NOTHING``) so re-running the scan does not clobber
edits from later phases. Detail writes are unconditional updates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hhack.domain.job import Job


@dataclass(frozen=True, slots=True)
class FeedCard:
    """Card-level fields extracted from the main-page personalized feed."""

    hh_id: int
    url: str
    title: str
    company: str | None
    snippet: str | None
    feed_resume_hint: str | None
    feed_position: int | None


@dataclass(frozen=True, slots=True)
class JobDetails:
    """Detail-page fields. Filled in after opening the vacancy URL."""

    hh_id: int
    full_text: str | None
    salary: str | None
    location: str | None
    employment_type: str | None
    posted_at: datetime | None


class JobRepositoryProtocol(Protocol):
    async def filter_known(self, hh_ids: Sequence[int]) -> set[int]:
        """Return the subset of hh_ids that already have a row."""

    async def upsert_feed_cards(self, cards: Sequence[FeedCard]) -> list[int]:
        """Insert cards we have not seen before. Returns the inserted hh_ids."""

    async def list_pending_details(self, limit: int) -> list[Job]:
        """Return up to `limit` jobs with status == 'discovered'."""

    async def list_processable(self, limit: int) -> list[Job]:
        """Jobs the feed worker still owes work on: ``discovered`` or ``detailed``.

        Ordered by ``first_seen_at`` so older vacancies drain first. Detailed
        rows show up here when an earlier scan saved details but crashed
        before persisting match results.
        """

    async def save_details(self, details: JobDetails) -> bool:
        """Update detail-page fields and flip status to 'detailed'. Returns True if a row was updated."""

    async def mark_matched(self, job_id: int) -> bool:
        """Flip status detailed → matched. Returns True if a row was updated."""

    async def mark_skipped(self, job_id: int) -> bool:
        """Flip status detailed → skipped (every match scored below threshold)."""


class SQLAlchemyJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def filter_known(self, hh_ids: Sequence[int]) -> set[int]:
        if not hh_ids:
            return set()
        async with self._factory() as session:
            result = await session.execute(select(Job.hh_id).where(Job.hh_id.in_(hh_ids)))
            return set(result.scalars().all())

    async def upsert_feed_cards(self, cards: Sequence[FeedCard]) -> list[int]:
        if not cards:
            return []
        payload = [
            {
                "hh_id": c.hh_id,
                "url": c.url,
                "title": c.title,
                "company": c.company,
                "snippet": c.snippet,
                "feed_resume_hint": c.feed_resume_hint,
                "feed_position": c.feed_position,
                "status": "discovered",
            }
            for c in cards
        ]
        stmt = pg_insert(Job).values(payload).on_conflict_do_nothing(index_elements=[Job.hh_id]).returning(Job.hh_id)
        async with self._factory.begin() as session:
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_pending_details(self, limit: int) -> list[Job]:
        async with self._factory() as session:
            result = await session.execute(
                select(Job).where(Job.status == "discovered").order_by(Job.first_seen_at.asc()).limit(limit)
            )
            return list(result.scalars().all())

    async def list_processable(self, limit: int) -> list[Job]:
        async with self._factory() as session:
            result = await session.execute(
                select(Job)
                .where(Job.status.in_(("discovered", "detailed")))
                .order_by(Job.first_seen_at.asc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def save_details(self, details: JobDetails) -> bool:
        stmt = (
            update(Job)
            .where(Job.hh_id == details.hh_id)
            .values(
                full_text=details.full_text,
                salary=details.salary,
                location=details.location,
                employment_type=details.employment_type,
                posted_at=details.posted_at,
                status="detailed",
                detail_fetched_at=datetime.now(UTC),
            )
            .returning(Job.hh_id)
        )
        async with self._factory.begin() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def mark_matched(self, job_id: int) -> bool:
        return await self._set_status(job_id, "matched")

    async def mark_skipped(self, job_id: int) -> bool:
        return await self._set_status(job_id, "skipped")

    async def _set_status(self, job_id: int, status: str) -> bool:
        stmt = update(Job).where(Job.id == job_id).values(status=status).returning(Job.id)
        async with self._factory.begin() as session:
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None
