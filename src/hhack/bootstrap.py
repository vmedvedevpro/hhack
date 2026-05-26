"""Dependency-injection assembly for hhack workers.

Each ``build_*`` factory returns an interface-typed object so workers and
tests don't depend on the concrete class. A single ``async_sessionmaker``
is cached per ``DATABASE_URL`` so the job and match repositories share
one connection pool instead of opening two.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hhack.config import Settings
from hhack.integrations.anthropic_client import (
    AnthropicClientProtocol,
    AsyncAnthropicClient,
)
from hhack.matching.letter_writer import LetterWriter
from hhack.matching.matcher import Matcher
from hhack.matching.resume import Resume, load_resumes
from hhack.persistence import (
    ApplicationRepositoryProtocol,
    JobRepositoryProtocol,
    MatchRepositoryProtocol,
    SQLAlchemyApplicationRepository,
    SQLAlchemyJobRepository,
    SQLAlchemyMatchRepository,
    create_session_factory,
)

_session_factory_cache: dict[str, async_sessionmaker[AsyncSession]] = {}


def _session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Phase 2+ requires Postgres — run "
            "`docker compose up -d` and fill DATABASE_URL in .env."
        )
    cached = _session_factory_cache.get(settings.database_url)
    if cached is not None:
        return cached
    factory = create_session_factory(settings.database_url)
    _session_factory_cache[settings.database_url] = factory
    return factory


def build_job_repository(settings: Settings) -> JobRepositoryProtocol:
    return SQLAlchemyJobRepository(_session_factory(settings))


def build_match_repository(settings: Settings) -> MatchRepositoryProtocol:
    return SQLAlchemyMatchRepository(_session_factory(settings))


def build_application_repository(settings: Settings) -> ApplicationRepositoryProtocol:
    return SQLAlchemyApplicationRepository(_session_factory(settings))


def build_anthropic_client(settings: Settings) -> AnthropicClientProtocol:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Phase 3+ calls the LLM — fill "
            "it in .env or unset the matcher in your CLI flags."
        )
    return AsyncAnthropicClient(settings.anthropic_api_key)


def build_matcher(settings: Settings, client: AnthropicClientProtocol) -> Matcher:
    return Matcher(client=client, model=settings.anthropic_match_model)


def build_letter_writer(settings: Settings, client: AnthropicClientProtocol) -> LetterWriter:
    return LetterWriter(client=client, model=settings.anthropic_letter_model)


def build_resumes(settings: Settings) -> list[Resume]:
    return load_resumes(settings)
