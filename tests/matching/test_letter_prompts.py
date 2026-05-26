from __future__ import annotations

from pathlib import Path

import pytest

from hhack.domain.job import Job
from hhack.matching.letter_prompts import (
    LETTER_RULES,
    LETTER_TOOL_SCHEMA,
    build_letter_system,
    build_letter_user,
    compute_letter_prompt_hash,
    validate_letter_payload,
)
from hhack.matching.matcher import MatchResult
from hhack.matching.resume import Resume


def _resume(content: str = "Python backend, 5 years.") -> Resume:
    return Resume(id="abc", path=Path("/tmp/abc.md"), content=content)


def _job() -> Job:
    return Job(
        id=1,
        hh_id=100,
        url="https://hh.ru/vacancy/100",
        title="Backend Python",
        company="Acme",
        salary="200000 RUR",
        location="Москва",
        employment_type="Полная занятость",
        full_text="Python, asyncio, postgres",
        snippet=None,
    )


def _match(score: float = 0.82) -> MatchResult:
    return MatchResult(
        job_id=1,
        resume_id="abc",
        model="claude-sonnet-4-6",
        prompt_hash="hash",
        score=score,
        rationale="Хорошее совпадение по стеку.",
        payload={
            "score": score,
            "rationale": "Хорошее совпадение по стеку.",
            "breakdown": {
                "skills": {"score": 0.9, "note": "Python и postgres совпадают"},
                "seniority": {"score": 0.8, "note": "5 лет — точно по требованию"},
                "location_comp": {"score": 0.5, "note": "Зарплата не указана"},
            },
            "red_flags": ["Релокейт в США не обсуждается"],
        },
        input_tokens=100,
        output_tokens=50,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def test_build_letter_system_caches_both_blocks():
    system = build_letter_system(_resume())
    assert len(system) == 2
    for block in system:
        assert block["type"] == "text"
        assert block["cache_control"] == {"type": "ephemeral"}
    assert LETTER_RULES in system[0]["text"]
    assert "Python backend" in system[1]["text"]


def test_build_letter_user_includes_vacancy_and_match_context():
    text = build_letter_user(_job(), _match())
    assert "hh_id=100" in text
    assert "Backend Python" in text
    assert "Python, asyncio, postgres" in text
    assert "Score: 0.82" in text
    assert "rationale" in text.lower()
    # Breakdown details should be there so the model can lean on strong dims.
    assert "skills: 0.90" in text
    assert "Релокейт" in text
    assert "submit_cover_letter" in text


def test_tool_schema_requires_body_and_language():
    schema = LETTER_TOOL_SCHEMA["input_schema"]
    assert set(schema["required"]) == {"body", "language"}
    assert "ru" in schema["properties"]["language"]["enum"]


def test_compute_letter_hash_stable_and_resume_sensitive():
    h1 = compute_letter_prompt_hash(model="claude-haiku-4-5-20251001", resume=_resume("v1"))
    h2 = compute_letter_prompt_hash(model="claude-haiku-4-5-20251001", resume=_resume("v1"))
    h3 = compute_letter_prompt_hash(model="claude-haiku-4-5-20251001", resume=_resume("v2"))
    h4 = compute_letter_prompt_hash(model="claude-sonnet-4-6", resume=_resume("v1"))
    assert h1 == h2
    assert h1 != h3  # resume edit invalidates
    assert h1 != h4  # model change invalidates


def test_validate_payload_happy_path():
    out = validate_letter_payload({"body": "Привет, готов обсудить.", "language": "ru"})
    assert out.body == "Привет, готов обсудить."
    assert out.language == "ru"


def test_validate_payload_rejects_missing_or_bad_fields():
    with pytest.raises(ValueError, match="body"):
        validate_letter_payload({"language": "ru"})
    with pytest.raises(ValueError, match="body"):
        validate_letter_payload({"body": "   ", "language": "ru"})
    with pytest.raises(ValueError, match="language"):
        validate_letter_payload({"body": "ok", "language": "fr"})
    with pytest.raises(ValueError, match="language"):
        validate_letter_payload({"body": "ok"})
