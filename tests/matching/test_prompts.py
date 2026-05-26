from __future__ import annotations

from pathlib import Path

import pytest

from hhack.domain.job import Job
from hhack.matching.prompts import (
    MATCH_RULES,
    MATCH_TOOL_SCHEMA,
    build_match_system,
    build_match_user,
    compute_prompt_hash,
    validate_match_payload,
)
from hhack.matching.resume import Resume


def _resume(content: str = "stack: python, async") -> Resume:
    return Resume(id="a", path=Path("/tmp/resume.md"), content=content)


def _job(**overrides: object) -> Job:
    defaults: dict[str, object] = {
        "id": 1,
        "hh_id": 100,
        "url": "https://hh.ru/vacancy/100",
        "title": "Python Engineer",
        "company": "Acme",
        "salary": "200000-300000 RUR",
        "location": "Москва",
        "employment_type": "Полная занятость",
        "full_text": "Python, asyncio, postgres",
        "snippet": "short snippet",
    }
    defaults.update(overrides)
    return Job(**defaults)  # type: ignore[arg-type]


def test_build_match_system_caches_both_blocks():
    system = build_match_system(_resume())
    assert len(system) == 2
    for block in system:
        assert block["type"] == "text"
        assert block["cache_control"] == {"type": "ephemeral"}
    assert MATCH_RULES in system[0]["text"]
    assert "stack: python" in system[1]["text"]


def test_build_match_user_includes_vacancy_id_and_body():
    text = build_match_user(_job())
    assert "hh_id=100" in text
    assert "Python Engineer" in text
    assert "Полная занятость" in text
    assert "Python, asyncio, postgres" in text
    assert "score_match" in text


def test_build_match_user_falls_back_to_snippet_when_full_text_missing():
    text = build_match_user(_job(full_text=None))
    assert "short snippet" in text


def test_match_tool_schema_requires_core_fields():
    schema = MATCH_TOOL_SCHEMA["input_schema"]
    required = set(schema["required"])
    assert required >= {"score", "rationale", "breakdown", "red_flags"}
    breakdown = schema["properties"]["breakdown"]
    assert set(breakdown["required"]) >= {"skills", "seniority", "location_comp"}


def test_compute_prompt_hash_is_stable():
    h1 = compute_prompt_hash(model="claude-sonnet-4-6", resume=_resume())
    h2 = compute_prompt_hash(model="claude-sonnet-4-6", resume=_resume())
    assert h1 == h2
    assert len(h1) == 64


def test_compute_prompt_hash_changes_on_resume_edit():
    base = compute_prompt_hash(model="claude-sonnet-4-6", resume=_resume("v1"))
    edit = compute_prompt_hash(model="claude-sonnet-4-6", resume=_resume("v2"))
    assert base != edit


def test_compute_prompt_hash_changes_on_model_change():
    a = compute_prompt_hash(model="claude-sonnet-4-6", resume=_resume())
    b = compute_prompt_hash(model="claude-haiku-4-5-20251001", resume=_resume())
    assert a != b


def test_validate_payload_happy_path():
    payload = {
        "score": 0.7,
        "rationale": "Совпадает по стеку.",
        "breakdown": {},
        "red_flags": [],
    }
    out = validate_match_payload(payload)
    assert out.score == 0.7
    assert "стеку" in out.rationale
    assert out.payload is payload


def test_validate_payload_clamps_score():
    high = validate_match_payload({"score": 1.7, "rationale": "ок"})
    low = validate_match_payload({"score": -0.5, "rationale": "плохо"})
    assert high.score == 1.0
    assert low.score == 0.0


def test_validate_payload_rejects_missing_fields():
    with pytest.raises(ValueError, match="numeric 'score'"):
        validate_match_payload({"rationale": "no score"})
    with pytest.raises(ValueError, match="rationale"):
        validate_match_payload({"score": 0.5})
    with pytest.raises(ValueError, match="rationale"):
        validate_match_payload({"score": 0.5, "rationale": "   "})
