# ruff: noqa: RUF001
from __future__ import annotations

import json

import pytest

from hhack.integrations.hh.resume_page import (
    ResumeParseError,
    extract_resume_markdown,
)

_FULL_STATE: dict[str, object] = {
    "educationLevels": [
        {"value": "bachelor", "text": "Бакалавр"},
        {"value": "higher", "text": "Высшее"},
    ],
    "applicantResume": {
        "title": [{"string": "Backend Engineer"}],
        "salary": [{"amount": 250000, "currency": "RUR"}],
        "area": [{"string": 1}],
        "totalExperience": [{"string": 66}],
        "professionalRole": [{"id": 96, "text": "Программист, разработчик"}],
        "employment": [{"string": "full"}, {"string": "project"}],
        "workSchedule": [{"string": "remote"}],
        "workFormats": [{"string": "REMOTE"}],
        "relocation": [{"string": "no_relocation"}],
        "businessTripReadiness": [{"string": "never"}],
        "skills": [{"string": "Опытный backend-разработчик. R&amp;D в финтехе."}],
        "experience": [
            {
                "startDate": "2024-01-01",
                "endDate": "2026-04-01",
                "companyName": "Acme Bank",
                "position": "Senior Backend Engineer",
                "description": "Python, asyncio, postgres. R&amp;D на gRPC.",
            },
            {
                "startDate": "2022-03-01",
                "endDate": None,
                "companyName": "Stealth Mode",
                "position": "Tech Lead",
                "description": None,
            },
        ],
        "resumeApplicantSkills": [
            {"category": "LANG", "name": "Русский", "level": {"name": "L1 - Родной"}},
            {"category": "LANG", "name": "Английский", "level": {"name": "B2 — Средне-продвинутый"}},
            {"category": "SKILL", "name": "Python"},
            {"category": "SKILL", "name": "PostgreSQL"},
            {"category": "SKILL", "name": "gRPC"},
        ],
        "educationLevel": [{"string": "bachelor"}],
        "primaryEducation": [
            {
                "name": "МФТИ",
                "organization": "ФУПМ",
                "result": "Прикладная математика",
                "year": 2018,
            }
        ],
        "additionalEducation": [
            {"name": "Курс по DevOps", "organization": "Stepik", "year": 2023},
        ],
    },
}


def _wrap(state: dict[str, object]) -> str:
    return (
        "<html><body>"
        '<template id="HH-Lux-InitialState">' + json.dumps(state, ensure_ascii=False) + "</template></body></html>"
    )


def test_extract_full_resume_produces_expected_sections():
    md = extract_resume_markdown(_wrap(_FULL_STATE))

    assert md.startswith("# Backend Engineer")
    assert "**Желаемая зарплата:** 250000 RUR" in md
    assert "**Локация:** Москва" in md
    assert "**Общий опыт:** 5 лет 6 мес" in md
    assert "**Профессиональная роль:** Программист, разработчик" in md
    assert "**Тип занятости:** Полная, Проектная" in md
    assert "**График:** Удалённо" in md
    assert "**Формат:** Удалённо" in md
    assert "**Переезд:** Не готов" in md
    assert "**Командировки:** Не готов" in md

    assert "## О себе" in md
    # html-entity is unescaped
    assert "R&D" in md
    assert "R&amp;D" not in md

    assert "## Опыт работы" in md
    assert "### Senior Backend Engineer · Acme Bank" in md
    assert "*январь 2024 — апрель 2026*" in md
    assert "### Tech Lead · Stealth Mode" in md
    assert "по настоящее время" in md

    assert "## Ключевые навыки" in md
    assert "Python, PostgreSQL, gRPC" in md

    assert "## Образование" in md
    assert "**Уровень:** Бакалавр" in md
    assert "**МФТИ** (2018)" in md
    assert "*ФУПМ — Прикладная математика*" in md
    assert "### Курсы и дополнительное образование" in md
    assert "Курс по DevOps — Stepik — 2023" in md

    assert "## Языки" in md
    assert "- Русский — L1 - Родной" in md
    assert "- Английский — B2 — Средне-продвинутый" in md


def test_extract_handles_missing_optional_fields():
    minimal = {
        "applicantResume": {
            "title": [{"string": "Junior Dev"}],
            "salary": [],
            "experience": [],
            "skills": [],
        }
    }
    md = extract_resume_markdown(_wrap(minimal))
    assert md.startswith("# Junior Dev")
    assert "Зарплата" not in md
    assert "## Опыт работы" not in md
    assert "## Языки" not in md
    assert "## Образование" not in md


def test_unknown_enum_codes_render_as_raw():
    state = {
        "applicantResume": {
            "title": [{"string": "X"}],
            "workSchedule": [{"string": "exotic_schedule"}],
            "relocation": [{"string": "alien_planet"}],
        }
    }
    md = extract_resume_markdown(_wrap(state))
    assert "**График:** exotic_schedule" in md
    assert "**Переезд:** alien_planet" in md


def test_unknown_area_id_falls_back_to_code():
    state = {
        "applicantResume": {
            "title": [{"string": "X"}],
            "area": [{"string": 99999}],
        }
    }
    md = extract_resume_markdown(_wrap(state))
    assert "**Локация:** area=99999" in md


def test_total_experience_pluralization():
    cases = [
        (1, "1 мес"),
        (5, "5 мес"),
        (12, "1 год"),
        (13, "1 год 1 мес"),
        (24, "2 года"),
        (60, "5 лет"),
        (132, "11 лет"),
    ]
    for months, expected in cases:
        state = {"applicantResume": {"title": [{"string": "X"}], "totalExperience": [{"string": months}]}}
        md = extract_resume_markdown(_wrap(state))
        assert expected in md, f"{months} months → expected '{expected}' in markdown"


def test_skills_fallback_chain():
    # If resumeApplicantSkills is missing, fall back to advancedKeySkills, then keySkills.
    advanced_only = {
        "applicantResume": {
            "title": [{"string": "X"}],
            "advancedKeySkills": [{"id": 1, "name": "Kafka"}, {"id": 2, "name": "Redis"}],
        }
    }
    md = extract_resume_markdown(_wrap(advanced_only))
    assert "## Ключевые навыки" in md
    assert "Kafka, Redis" in md

    legacy_only = {
        "applicantResume": {
            "title": [{"string": "X"}],
            "keySkills": [{"string": "Bash"}, {"string": "Linux"}],
        }
    }
    md = extract_resume_markdown(_wrap(legacy_only))
    assert "Bash, Linux" in md


def test_missing_template_raises():
    with pytest.raises(ResumeParseError, match="not found"):
        extract_resume_markdown("<html><body>no template here</body></html>")


def test_invalid_json_raises():
    bad = '<html><template id="HH-Lux-InitialState">{not json}</template></html>'
    with pytest.raises(ResumeParseError, match="not valid JSON"):
        extract_resume_markdown(bad)


def test_missing_applicant_resume_raises():
    bad = '<html><template id="HH-Lux-InitialState">{"other": 1}</template></html>'
    with pytest.raises(ResumeParseError, match="applicantResume"):
        extract_resume_markdown(bad)
