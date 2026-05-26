"""High-level letter writer: vacancy + best-match resume → cover letter draft."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from hhack.domain.job import Job
from hhack.integrations.anthropic_client import AnthropicClientProtocol
from hhack.matching.letter_prompts import (
    LETTER_TOOL_SCHEMA,
    build_letter_system,
    build_letter_user,
    compute_letter_prompt_hash,
    validate_letter_payload,
)
from hhack.matching.matcher import MatchResult
from hhack.matching.resume import Resume

_MAX_OUTPUT_TOKENS = 1200


@dataclass(frozen=True, slots=True)
class LetterDraft:
    """A single generated cover letter, ready to persist as an Application row."""

    job_id: int
    resume_id: str
    model: str
    prompt_hash: str
    cover_letter: str
    language: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


class LetterWriter:
    def __init__(self, client: AnthropicClientProtocol, model: str) -> None:
        self._client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def prompt_hash(self, resume: Resume) -> str:
        return compute_letter_prompt_hash(model=self._model, resume=resume)

    async def write(self, job: Job, resume: Resume, match: MatchResult) -> LetterDraft:
        bound = logger.bind(component="letter_writer", hh_id=job.hh_id, resume_id=resume.id)
        system = build_letter_system(resume)
        user = build_letter_user(job, match)

        result = await self._client.create_tool_call(
            model=self._model,
            system=system,
            user=user,
            tool=LETTER_TOOL_SCHEMA,
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.4,
        )
        bound.info(
            "anthropic usage: in={i} out={o} cache_read={cr} cache_creation={cc}",
            i=result.input_tokens,
            o=result.output_tokens,
            cr=result.cache_read_input_tokens,
            cc=result.cache_creation_input_tokens,
        )

        parsed = validate_letter_payload(result.input)
        bound.info("letter drafted: {n} chars lang={lang}", n=len(parsed.body), lang=parsed.language)

        return LetterDraft(
            job_id=job.id,
            resume_id=resume.id,
            model=result.model,
            prompt_hash=self.prompt_hash(resume),
            cover_letter=parsed.body,
            language=parsed.language,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_input_tokens=result.cache_read_input_tokens,
            cache_creation_input_tokens=result.cache_creation_input_tokens,
        )


__all__ = ["LetterDraft", "LetterWriter"]
