from __future__ import annotations

from pathlib import Path

import pytest

from hhack.domain.job import Job
from hhack.matching.letter_prompts import LETTER_TOOL_SCHEMA
from hhack.matching.letter_writer import LetterWriter
from hhack.matching.matcher import MatchResult
from hhack.matching.resume import Resume
from tests.integrations.fakes import FakeAnthropicClient, fake_tool_call


def _resume() -> Resume:
    return Resume(id="abc", path=Path("/tmp/abc.md"), content="Python backend, 5 years.")


def _job() -> Job:
    return Job(
        id=1,
        hh_id=100,
        url="https://hh.ru/vacancy/100",
        title="Backend Python",
        company="Acme",
        salary=None,
        location=None,
        employment_type=None,
        full_text="Python, asyncio, postgres",
        snippet=None,
    )


def _match() -> MatchResult:
    return MatchResult(
        job_id=1,
        resume_id="abc",
        model="claude-sonnet-4-6",
        prompt_hash="match-hash",
        score=0.82,
        rationale="Совпадение по стеку.",
        payload={"score": 0.82, "rationale": "Совпадение по стеку.", "breakdown": {}, "red_flags": []},
        input_tokens=10,
        output_tokens=10,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


async def test_letter_writer_round_trip_produces_draft():
    canned = fake_tool_call({"body": "Привет, готов обсудить.", "language": "ru"})
    client = FakeAnthropicClient([canned])
    writer = LetterWriter(client=client, model="claude-haiku-4-5-20251001")

    draft = await writer.write(_job(), _resume(), _match())

    assert draft.job_id == 1
    assert draft.resume_id == "abc"
    assert draft.cover_letter == "Привет, готов обсудить."
    assert draft.language == "ru"
    assert draft.model == "claude-sonnet-4-6"  # comes from fake_tool_call default
    assert draft.prompt_hash == writer.prompt_hash(_resume())

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["mode"] == "tool_call"
    assert call["tool"] is LETTER_TOOL_SCHEMA
    # System carries the resume; user carries vacancy + match context.
    assert any("Python backend" in b["text"] for b in call["system"])
    assert "Score: 0.82" in call["user"]


async def test_letter_writer_raises_on_bad_payload():
    canned = fake_tool_call({"language": "ru"})  # body missing
    client = FakeAnthropicClient([canned])
    writer = LetterWriter(client=client, model="claude-haiku-4-5-20251001")
    with pytest.raises(ValueError):
        await writer.write(_job(), _resume(), _match())
