"""In-memory fakes implementing the persistence Protocols. Tests only."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import count

from hhack.domain.job import Job
from hhack.matching.letter_writer import LetterDraft
from hhack.matching.matcher import MatchResult
from hhack.persistence.job_repository import FeedCard, JobDetails


class FakeJobRepository:
    """In-memory ``JobRepositoryProtocol`` implementation.

    Mirrors the behavior the SQLAlchemy impl has against Postgres:
    ``upsert_feed_cards`` is idempotent on ``hh_id``; ``save_details``
    updates an existing row and flips status.
    """

    def __init__(self) -> None:
        self.rows: dict[int, Job] = {}
        self._next_pk = count(1)

    async def filter_known(self, hh_ids: Sequence[int]) -> set[int]:
        return {hh_id for hh_id in hh_ids if hh_id in self.rows}

    async def upsert_feed_cards(self, cards: Sequence[FeedCard]) -> list[int]:
        inserted: list[int] = []
        for card in cards:
            if card.hh_id in self.rows:
                continue
            self.rows[card.hh_id] = Job(
                id=next(self._next_pk),
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

    async def list_processable(self, limit: int) -> list[Job]:
        rows = [job for job in self.rows.values() if job.status in {"discovered", "detailed"}]
        rows.sort(key=lambda j: j.first_seen_at)
        return rows[:limit]

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

    async def mark_matched(self, job_id: int) -> bool:
        return self._set_status(job_id, "matched")

    async def mark_skipped(self, job_id: int) -> bool:
        return self._set_status(job_id, "skipped")

    def _set_status(self, job_id: int, status: str) -> bool:
        for job in self.rows.values():
            if job.id == job_id:
                job.status = status
                return True
        return False


class FakeMatchRepository:
    """In-memory ``MatchRepositoryProtocol`` for tests."""

    def __init__(self) -> None:
        self.rows: list[MatchResult] = []

    async def exists(self, *, job_id: int, resume_id: str, prompt_hash: str) -> bool:
        return any(r.job_id == job_id and r.resume_id == resume_id and r.prompt_hash == prompt_hash for r in self.rows)

    async def save(self, result: MatchResult) -> bool:
        if await self.exists(
            job_id=result.job_id,
            resume_id=result.resume_id,
            prompt_hash=result.prompt_hash,
        ):
            return False
        self.rows.append(result)
        return True

    async def best_score(self, job_id: int) -> float | None:
        scores = [r.score for r in self.rows if r.job_id == job_id]
        return max(scores) if scores else None

    async def best_match(self, job_id: int) -> MatchResult | None:
        rows = [r for r in self.rows if r.job_id == job_id]
        if not rows:
            return None
        return max(rows, key=lambda r: r.score)


class FakeApplicationRepository:
    """In-memory ``ApplicationRepositoryProtocol`` for tests."""

    def __init__(self) -> None:
        self.rows: list[LetterDraft] = []

    async def exists(self, *, job_id: int, prompt_hash: str) -> bool:
        return any(r.job_id == job_id and r.prompt_hash == prompt_hash for r in self.rows)

    async def save(self, draft: LetterDraft) -> bool:
        if await self.exists(job_id=draft.job_id, prompt_hash=draft.prompt_hash):
            return False
        self.rows.append(draft)
        return True
