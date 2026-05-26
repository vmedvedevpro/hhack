"""Match repository — protocol + SQLAlchemy implementation.

Writes are idempotent on ``(job_id, resume_id, prompt_hash)`` via
Postgres ``ON CONFLICT DO NOTHING`` — the matcher prompt-hash includes
the prompt version, model name and resume content, so the same call
twice on the same job is a no-op while a real prompt or resume edit
naturally produces a new row.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hhack.domain.match import MatchResult as MatchResultRow
from hhack.matching.matcher import MatchResult


class MatchRepositoryProtocol(Protocol):
    async def exists(self, *, job_id: int, resume_id: str, prompt_hash: str) -> bool:
        """True if we already have a decision for this (job, resume, prompt_hash)."""

    async def save(self, result: MatchResult) -> bool:
        """Insert one decision. Returns True if a row was added, False on conflict."""

    async def best_score(self, job_id: int) -> float | None:
        """Max ``score`` across every match row for this job, or None if none exist."""

    async def best_match(self, job_id: int) -> MatchResult | None:
        """Return the highest-scoring match row for the job, or None."""


class SQLAlchemyMatchRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def exists(self, *, job_id: int, resume_id: str, prompt_hash: str) -> bool:
        async with self._factory() as session:
            stmt = select(
                exists().where(
                    MatchResultRow.job_id == job_id,
                    MatchResultRow.resume_id == resume_id,
                    MatchResultRow.prompt_hash == prompt_hash,
                )
            )
            return bool((await session.execute(stmt)).scalar())

    async def save(self, result: MatchResult) -> bool:
        stmt = (
            pg_insert(MatchResultRow)
            .values(
                job_id=result.job_id,
                resume_id=result.resume_id,
                model=result.model,
                prompt_hash=result.prompt_hash,
                score=result.score,
                rationale=result.rationale,
                payload=result.payload,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_input_tokens=result.cache_read_input_tokens,
                cache_creation_input_tokens=result.cache_creation_input_tokens,
            )
            .on_conflict_do_nothing(constraint="uq_match_results_job_resume_prompt")
            .returning(MatchResultRow.id)
        )
        async with self._factory.begin() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row is not None

    async def best_score(self, job_id: int) -> float | None:
        async with self._factory() as session:
            result = await session.execute(
                select(func.max(MatchResultRow.score)).where(MatchResultRow.job_id == job_id)
            )
            value = result.scalar_one_or_none()
            return float(value) if value is not None else None

    async def best_match(self, job_id: int) -> MatchResult | None:
        async with self._factory() as session:
            stmt = (
                select(MatchResultRow)
                .where(MatchResultRow.job_id == job_id)
                .order_by(MatchResultRow.score.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                return None
            return MatchResult(
                job_id=row.job_id,
                resume_id=row.resume_id,
                model=row.model,
                prompt_hash=row.prompt_hash,
                score=float(row.score),
                rationale=row.rationale,
                payload=row.payload,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cache_read_input_tokens=row.cache_read_input_tokens,
                cache_creation_input_tokens=row.cache_creation_input_tokens,
            )


__all__ = ["MatchRepositoryProtocol", "SQLAlchemyMatchRepository"]
