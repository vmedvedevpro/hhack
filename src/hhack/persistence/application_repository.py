"""Application repository — protocol + SQLAlchemy implementation.

Writes are idempotent on ``(job_id, prompt_hash)`` via Postgres
``ON CONFLICT DO NOTHING`` — the letter prompt hash includes the
template version, model and resume content, so the same call twice on
the same job is a no-op while a real prompt or resume edit naturally
produces a new draft row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hhack.domain.application import Application as ApplicationRow

if TYPE_CHECKING:
    from hhack.matching.letter_writer import LetterDraft


class ApplicationRepositoryProtocol(Protocol):
    async def exists(self, *, job_id: int, prompt_hash: str) -> bool:
        """True if we already drafted a letter for this (job, prompt_hash)."""

    async def save(self, draft: LetterDraft) -> bool:
        """Insert one draft. Returns True if a row was added, False on conflict."""


class SQLAlchemyApplicationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def exists(self, *, job_id: int, prompt_hash: str) -> bool:
        async with self._factory() as session:
            stmt = select(
                exists().where(
                    ApplicationRow.job_id == job_id,
                    ApplicationRow.prompt_hash == prompt_hash,
                )
            )
            return bool((await session.execute(stmt)).scalar())

    async def save(self, draft: LetterDraft) -> bool:
        stmt = (
            pg_insert(ApplicationRow)
            .values(
                job_id=draft.job_id,
                resume_id=draft.resume_id,
                cover_letter=draft.cover_letter,
                language=draft.language,
                status="draft",
                prompt_hash=draft.prompt_hash,
                model=draft.model,
                input_tokens=draft.input_tokens,
                output_tokens=draft.output_tokens,
                cache_read_input_tokens=draft.cache_read_input_tokens,
                cache_creation_input_tokens=draft.cache_creation_input_tokens,
            )
            .on_conflict_do_nothing(constraint="uq_applications_job_prompt")
            .returning(ApplicationRow.id)
        )
        async with self._factory.begin() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row is not None


__all__ = ["ApplicationRepositoryProtocol", "SQLAlchemyApplicationRepository"]
