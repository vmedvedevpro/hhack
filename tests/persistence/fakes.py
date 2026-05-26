"""In-memory fakes implementing the persistence Protocols. Tests only."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from hhack.domain.job import Job
from hhack.persistence.job_repository import FeedCard, JobDetails


class FakeJobRepository:
    """In-memory ``JobRepositoryProtocol`` implementation.

    Mirrors the behavior the SQLAlchemy impl has against Postgres:
    ``upsert_feed_cards`` is idempotent on ``hh_id``; ``save_details``
    updates an existing row and flips status.
    """

    def __init__(self) -> None:
        self.rows: dict[int, Job] = {}

    async def filter_known(self, hh_ids: Sequence[int]) -> set[int]:
        return {hh_id for hh_id in hh_ids if hh_id in self.rows}

    async def upsert_feed_cards(self, cards: Sequence[FeedCard]) -> list[int]:
        inserted: list[int] = []
        for card in cards:
            if card.hh_id in self.rows:
                continue
            self.rows[card.hh_id] = Job(
                hh_id=card.hh_id,
                url=card.url,
                title=card.title,
                company=card.company,
                snippet=card.snippet,
                feed_resume_hint=card.feed_resume_hint,
                feed_position=card.feed_position,
                status="discovered",
                first_seen_at=datetime.now(UTC),
            )
            inserted.append(card.hh_id)
        return inserted

    async def list_pending_details(self, limit: int) -> list[Job]:
        pending = [job for job in self.rows.values() if job.status == "discovered"]
        pending.sort(key=lambda j: j.first_seen_at)
        return pending[:limit]

    async def save_details(self, details: JobDetails) -> bool:
        job = self.rows.get(details.hh_id)
        if job is None:
            return False
        job.full_text = details.full_text
        job.salary = details.salary
        job.location = details.location
        job.employment_type = details.employment_type
        job.posted_at = details.posted_at
        job.status = "detailed"
        job.detail_fetched_at = datetime.now(UTC)
        return True
