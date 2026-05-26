from __future__ import annotations

from pathlib import Path

import pytest

from hhack.domain.job import Job
from hhack.matching.matcher import Matcher
from hhack.matching.prompts import MATCH_TOOL_SCHEMA
from hhack.matching.resume import Resume
from tests.integrations.fakes import FakeAnthropicClient, fake_tool_call


def _resume() -> Resume:
    return Resume(id="a", path=Path("/tmp/resume.md"), content="stack: python")


def _job() -> Job:
    return Job(
        id=42,
        hh_id=12345,
        url="https://hh.ru/vacancy/12345",
        title="Python Dev",
        company=None,
        salary=None,
        location=None,
        employment_type=None,
        full_text="Backend role, postgres, asyncio.",
        snippet=None,
    )


async def test_matcher_round_trip_populates_match_result():
    canned = fake_tool_call(
        {
            "score": 0.82,
            "rationale": "Совпадение по стеку.",
            "breakdown": {"skills": {"score": 0.9, "note": "ok"}},
            "red_flags": [],
        }
    )
    client = FakeAnthropicClient([canned])
    matcher = Matcher(client=client, model="claude-sonnet-4-6")

    result = await matcher.match(_job(), _resume())

    assert result.job_id == 42
    assert result.resume_id == "a"
    assert result.score == pytest.approx(0.82)
    assert "стеку" in result.rationale
    assert result.payload["breakdown"]["skills"]["note"] == "ok"
    assert result.prompt_hash == matcher.prompt_hash(_resume())

    # Verify the request shape.
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["mode"] == "tool_call"
    assert call["model"] == "claude-sonnet-4-6"
    assert call["temperature"] == 0.0
    assert call["tool"] is MATCH_TOOL_SCHEMA
    assert len(call["system"]) == 2
    assert "stack: python" in call["system"][1]["text"]
    assert "hh_id=12345" in call["user"]


async def test_matcher_raises_when_tool_payload_invalid():
    canned = fake_tool_call({"rationale": "missing score"})
    client = FakeAnthropicClient([canned])
    matcher = Matcher(client=client, model="claude-sonnet-4-6")
    with pytest.raises(ValueError):
        await matcher.match(_job(), _resume())
