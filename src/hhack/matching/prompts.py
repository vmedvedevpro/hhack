# ruff: noqa: RUF001
"""Prompt assembly + tool-call validation for the matcher.

We use Anthropic's *tool use* path instead of asking the model for a
JSON string in plain text. The reason is empirical: with free-form JSON
the model returns an unescaped quote or newline inside ``rationale``
once every ~dozen calls, and we have to either ignore the result or
write a tolerant repair pass. With tool use the SDK parses ``input``
for us and rejects malformed payloads on its end.

The prompt is structured into two cacheable system blocks:

* ``MATCH_RULES`` — rubric + instruction to call the ``score_match``
  tool. Cached.
* The resume content. Cached.

``MATCH_TOOL_SCHEMA`` carries the output schema. Bumping the rules,
schema, or ``PROMPT_VERSION`` invalidates the prompt hash so old rows
in ``match_results`` survive and new evaluations naturally appear on
the next scan.

``ruff: noqa`` suppresses ambiguous-character lints — the prompt mixes
Cyrillic descriptions with ASCII identifiers (``score``, ``skills``)
on purpose so the model sees both.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from hhack.domain.job import Job
from hhack.matching.resume import Resume

PROMPT_VERSION = "match-v2"

MATCH_RULES = """\
Ты оцениваешь, насколько хорошо вакансия подходит соискателю по его \
резюме. Цель — найти настоящие совпадения, а не подбадривать. Если \
вакансия требует навыков, которых нет в резюме, или уровня сильно \
выше/ниже — это низкий score, без оправданий.

Свой ответ ты обязан вернуть вызовом инструмента score_match — \
никакого свободного текста, объяснений или markdown снаружи tool call.

Правила оценки:
- skills: совпадение стека и доменных навыков. 0.9+ только когда \
ключевые требования прямо названы в резюме.
- seniority: соответствие уровня. Резюме сильно выше или сильно ниже \
требуемого — обоюдная штрафная зона.
- location_comp: локация и зарплата. Релокейт без удалёнки при явно \
не релоцируемом соискателе — низкий score. Если данных в вакансии нет, \
ставь 0.5 и так и напиши в note.
- red_flags: жёсткие стоп-факторы (обязательный релокейт, требование \
гражданства, явный мисматч по технологии). Пустой список — норма.
- Итоговый score не среднее: одно сильное red flag может уронить score \
сильнее, чем хорошее совпадение по skills его поднимает.
- Все note и rationale — на русском, не более одной короткой строки на note.
"""


_DIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "note": {"type": "string"},
    },
    "required": ["score", "note"],
}

MATCH_TOOL_SCHEMA: dict[str, Any] = {
    "name": "score_match",
    "description": (
        "Сохрани оценку соответствия одной вакансии и одного резюме. " "Вызывается ровно один раз на каждую пару."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Итоговый score соответствия в диапазоне 0..1.",
            },
            "rationale": {
                "type": "string",
                "description": "2-3 коротких предложения на русском, почему такой score.",
            },
            "breakdown": {
                "type": "object",
                "properties": {
                    "skills": _DIM_SCHEMA,
                    "seniority": _DIM_SCHEMA,
                    "location_comp": _DIM_SCHEMA,
                },
                "required": ["skills", "seniority", "location_comp"],
                "additionalProperties": False,
            },
            "red_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Список жёстких стоп-факторов; пустой массив — норма.",
            },
        },
        "required": ["score", "rationale", "breakdown", "red_flags"],
        "additionalProperties": False,
    },
}


def _resume_block(resume: Resume) -> str:
    return f"=== РЕЗЮМЕ (id={resume.id}) ===\n{resume.content}\n=== КОНЕЦ РЕЗЮМЕ ==="


def _job_block(job: Job) -> str:
    fields: list[tuple[str, str | None]] = [
        ("Должность", job.title),
        ("Компания", job.company),
        ("Зарплата", job.salary),
        ("Локация", job.location),
        ("Формат", job.employment_type),
    ]
    header = "\n".join(f"{label}: {value}" for label, value in fields if value)
    body = job.full_text or job.snippet or "(текст не извлечён)"
    return f"=== ВАКАНСИЯ (hh_id={job.hh_id}) ===\n{header}\n\n{body}\n=== КОНЕЦ ВАКАНСИИ ==="


def build_match_system(resume: Resume) -> list[dict[str, Any]]:
    """Two cacheable system blocks: the rules and the resume content."""
    return [
        {"type": "text", "text": MATCH_RULES, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": _resume_block(resume), "cache_control": {"type": "ephemeral"}},
    ]


def build_match_user(job: Job) -> str:
    return f"{_job_block(job)}\n\nОцени соответствие и верни результат через tool score_match."


def compute_prompt_hash(*, model: str, resume: Resume) -> str:
    """Stable identifier for ``(prompt_version, model, resume_content)``.

    Excludes the vacancy on purpose — we want one row per (job, resume,
    prompt_version), not per unique vacancy text.
    """
    digest = hashlib.sha256()
    digest.update(PROMPT_VERSION.encode())
    digest.update(b"\0")
    digest.update(model.encode())
    digest.update(b"\0")
    digest.update(resume.id.encode())
    digest.update(b"\0")
    digest.update(resume.content.encode())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class MatchPayload:
    score: float
    rationale: str
    payload: dict[str, Any]


def validate_match_payload(payload: dict[str, Any]) -> MatchPayload:
    """Validate a parsed tool_use input. SDK already enforces JSON validity.

    We re-check ``score`` and ``rationale`` here because Anthropic's tool
    schema is advisory (the model may still omit a required field), and
    we want clamping + clean error messages either way.
    """
    raw_score = payload.get("score")
    if not isinstance(raw_score, int | float):
        raise ValueError("tool input missing numeric 'score'")
    score = max(0.0, min(1.0, float(raw_score)))
    rationale = payload.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("tool input missing 'rationale'")
    return MatchPayload(score=score, rationale=rationale.strip(), payload=payload)


__all__ = [
    "MATCH_RULES",
    "MATCH_TOOL_SCHEMA",
    "PROMPT_VERSION",
    "MatchPayload",
    "build_match_system",
    "build_match_user",
    "compute_prompt_hash",
    "validate_match_payload",
]
