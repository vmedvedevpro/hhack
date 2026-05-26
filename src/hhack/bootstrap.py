"""Dependency-injection assembly for hhack workers.

Phase 2 wires Postgres + the job repository. The Anthropic client,
resume loader, etc. land in later phases.
"""

from __future__ import annotations

from hhack.config import Settings
from hhack.persistence import (
    JobRepositoryProtocol,
    SQLAlchemyJobRepository,
    create_session_factory,
)


def build_job_repository(settings: Settings) -> JobRepositoryProtocol:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Phase 2+ requires Postgres — run "
            "`docker compose up -d` and fill DATABASE_URL in .env."
        )
    session_factory = create_session_factory(settings.database_url)
    return SQLAlchemyJobRepository(session_factory)
