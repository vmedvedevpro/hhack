"""High-level matcher: vacancy + resume → score + rationale."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from hhack.domain.job import Job
from hhack.integrations.anthropic_client import AnthropicClientProtocol
from hhack.matching.prompts import (
    MATCH_TOOL_SCHEMA,
    build_match_system,
    build_match_user,
    compute_prompt_hash,
    validate_match_payload,
)
from hhack.matching.resume import Resume

_MAX_OUTPUT_TOKENS = 800


@dataclass(frozen=True, slots=True)
class MatchResult:
    """A single (job, resume) decision, ready to persist."""

    job_id: int
    resume_id: str
    model: str
    prompt_hash: str
    score: float
    rationale: str
    payload: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class Matcher:
    def __init__(self, client: AnthropicClientProtocol, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def prompt_hash(self, resume: Resume) -> str:
        return compute_prompt_hash(model=self._model, resume=resume)

    async def match(self, job: Job, resume: Resume) -> MatchResult:
        bound = logger.bind(component="matcher", hh_id=job.hh_id, resume_id=resume.id)
        system = build_match_system(resume)
        user = build_match_user(job)

        result = await self._client.create_tool_call(
            model=self._model,
            system=system,
            user=user,
            tool=MATCH_TOOL_SCHEMA,
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.0,
        )
        bound.info(
            "anthropic usage: in={i} out={o} cache_read={cr} cache_creation={cc}",
            i=result.input_tokens,
            o=result.output_tokens,
            cr=result.cache_read_input_tokens,
            cc=result.cache_creation_input_tokens,
        )

        parsed = validate_match_payload(result.input)
        bound.info("matched score={s:.3f}", s=parsed.score)

        return MatchResult(
            job_id=job.id,
            resume_id=resume.id,
            model=result.model,
            prompt_hash=self.prompt_hash(resume),
            score=parsed.score,
            rationale=parsed.rationale,
            payload=parsed.payload,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_input_tokens=result.cache_read_input_tokens,
            cache_creation_input_tokens=result.cache_creation_input_tokens,
        )


__all__ = ["MatchResult", "Matcher"]
