# ruff: noqa: RUF001
"""Prompt assembly + validation for cover-letter generation.

Same shape as ``prompts.py`` but for the second LLM call in the chain.
Two cacheable system blocks (rules + resume), one uncached user block
(job text + match rationale). Output is forced through a tool call so
the model can't break the JSON.

``LETTER_VERSION`` is bumped any time we touch ``LETTER_RULES``, the
banned-phrase list, or the tool schema. The bump invalidates the
per-(job, prompt_hash) idempotency check so the next scan generates a
fresh draft against the new prompt while the old draft stays in
``applications`` for comparison.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from hhack.domain.job import Job
from hhack.matching.matcher import MatchResult
from hhack.matching.resume import Resume

LETTER_VERSION = "letter-v5"

LETTER_RULES = """\
You are drafting a short cover letter on behalf of a job applicant for \
one specific HH.ru vacancy. The recipient is a recruiter who reads \
fifty letters today. Your job is to look like a real human writing one \
thoughtful reply, not a polished marketing pitch.

LANGUAGE OF THE OUTPUT — read carefully:
- These instructions are written in English, but that is for clarity only.
- The body of the letter MUST be written in the language of the vacancy text.
- Russian vacancy text → Russian letter. English vacancy text → English letter.
- Never mix languages inside the body. Pick one and stay in it.

Hard constraints:
- 4-6 sentences total. Hard cap 600 characters in the body. If your \
draft is longer than 600, rewrite it shorter until it fits. Do not \
emit a draft above 700 characters under any circumstance.
- Begin with a single short greeting on its own line: \
"Здравствуйте," for Russian, "Hello," for English. No "Dear Hiring \
Manager", no "Добрый день", no name placeholder, no extra punctuation.
- No signature at the end. HH adds the candidate's name automatically. \
Never write "С уважением", "Best regards", "Спасибо за внимание", \
"Looking forward to your response".
- No emoji, no exclamation marks.
- Use only facts that are explicitly present in the resume. Do not \
invent companies, years of experience, technologies, or numbers.

Opening line — what it must NOT do:
- Restate the job title. The recruiter already knows the role.
  bad: "Интересует вакансия Senior .NET-разработчика"
  bad: "I am applying for the Senior X position"
- Restate the company name as the hook. Also obvious from context.
  bad: "Интересна работа в Clearway"
  bad: "I'm excited about Company X"
- Praise the standard tech stack as something "attractive". For a \
candidate at this level the stack is normal, not a draw.
  bad: "Привлекает работа с микросервисами на .NET"
  bad: "I love working with React"
- Use the empty-connector pattern X-is-exactly-what-Y. This applies to \
ALL paraphrases, including variants that route through "это/то место" \
or "именно эта/эта позиция". Forbidden patterns include:
  bad: "это именно то, что..."
  bad: "это то, что я искал"
  bad: "это то, чем я делал"
  bad: "это то, с чем я работал"
  bad: "это близко к тому, что вы описываете"
  bad: "это именно то место, где"
  bad: "this is exactly what I do"
  bad: "this is what I was looking for"
  The pattern reads as machine-generated regardless of the noun that \
follows it. If you want to claim a match, name the concrete project, \
company, or technology from the resume instead of inserting a \
demonstrative.
- Use the "Интересует возможность X" closing pattern (and its English \
twins). It is the same empty filler, just at the end of the letter \
instead of the start. Forbidden patterns include:
  bad: "Интересует возможность поработать над X"
  bad: "Интересует возможность обсудить, как мой опыт..."
  bad: "Интересует возможность вернуться к X"
  bad: "Интересует именно эта позиция"
  bad: "Looking forward to the opportunity to..."
  bad: "Excited about the chance to..."
  Replace with a concrete question or hand-off: "Хотел бы понять, как \
устроена X в команде" / "Готов обсудить детали Y" / "Could we talk \
about how your Z team is organized".

A good opening references one concrete detail of THIS vacancy that the \
candidate can actually speak to from the resume — a product, a domain, \
a non-trivial technical challenge in the description, a scale/load \
number, a specific migration target. Something you could not say about \
any other vacancy that shares the same stack. If no such detail is in \
the vacancy text (description is too generic), skip the hook entirely \
and go straight from the greeting to the resume match.

Examples:
  bad: "Привлекает работа с микросервисами на .NET" (any .NET job)
  bad: "Это именно то, что я делаю сейчас"
  good: "Видел в описании про миграцию биллинга с Windows на Linux - \
этим занимался последний год на проекте X."

Red flags from the match analysis block — important:
- The user message includes a "Результат матчинга" block with a \
red_flags array. That block is context FOR YOU, not content for the \
letter.
- Never copy red flags / deal-breakers / "I might not fit because..." \
language from the analysis into the letter. Specifically forbidden:
  bad: "Понимаю, что вакансия требует офисного формата, а я ищу удалёнку"
  bad: "Если это критично, мы не подходим друг другу"
  bad: "Сейчас перехожу в другое направление, но готов рассмотреть как \
переходный проект"
  bad: "Коммерческого опыта на Python пока нет"
- You may briefly parry ONE gap, and only if the resume gives you a \
concrete bridge for it. Example: "MS SQL не использовал коммерчески, \
но T-SQL и оптимизация запросов мне знакомы по PostgreSQL." Never \
advertise more than one gap. Never offer the company a reason to \
reject.
- If red flags were severe enough to disqualify, the matcher would \
have skipped this job. By the time we reach the letter, treat the \
candidate as a viable fit.

Anti-AI tells — these must be absent from the letter body:
- Em dash "—" (U+2014) and en dash "–" (U+2013). Use a plain hyphen \
"-", a comma, or a period.
- Perfectly balanced lists like "не только X, но и Y, а также Z". A \
normal person enumerates 1-2 things.
- Connector words: "более того", "кроме того", "к тому же", \
"таким образом", "в заключение", "furthermore", "moreover", \
"additionally", "it is worth noting".
- Showy verbs: "погрузиться", "всесторонне изучить", "комплексно \
подойти", "синергия", "leverage", "delve", "harness", "utilize" when \
"use" / "применять" works.
- Strings of 3+ adjectives ("современный, масштабируемый, надёжный и \
производительный"). One or two precise words is enough.
- Numeric self-rating dumps copied from the vacancy ("EF Core - 2, \
RabbitMQ - 2, Hangfire - 2"). Never paste a self-rating list into the \
letter, EVEN IF THE VACANCY EXPLICITLY ASKS FOR A 1-5 SCALE. If the \
recruiter wants a self-rating they will ask in the interview; in the \
cover letter you describe the same fact in prose ("С EF Core работал \
коммерчески на двух проектах" instead of "EF Core - 2").

Write like a human: vary sentence length, contractions are fine \
("I'm" / "не могу"), starting a sentence with "И" or "But" \
occasionally is fine, mild word repetition is natural, and one or two \
slightly informal touches are better than uniform polish.

Structure (loose — follow only as far as the vacancy makes useful):
1. Greeting.
2. One concrete hook (or skip if no concrete detail in the vacancy).
3. One or two matches from the resume that connect to the vacancy. \
Lean on the dimensions where the matcher gave high skills/seniority \
scores.
4. One short sentence on what you would like to discuss or how you \
would plug in.
5. One short sentence on availability for a call. No formal flourishes.

Reliable working pattern for the body (use as a calibration anchor, \
not as a literal template — the X / Y / Z must come from THIS vacancy \
and THIS resume):
"Видел в описании про <конкретная деталь вакансии>. У меня был похожий \
кейс — <конкретный проект из резюме>, где я делал <что именно>. \
<Опционально: одно парирование пробела, если есть чем парировать.> \
Хотел бы понять, <конкретный вопрос про команду / стек / процессы>. \
Готов созвониться в удобное вам время."

Calibration example (a complete letter, ~615 characters, do NOT copy \
phrases out of it — only use as a length and tone reference):
"Здравствуйте,

Видел в описании про переход на event-driven архитектуру через Kafka. \
В банке Acme последние два года поднимал именно такую — развёл 9 \
микросервисов через Kafka и RabbitMQ, настроил трассировку и метрики \
через Prometheus и Grafana. EF Core, PostgreSQL и асинхронные \
паттерны в ежедневной работе.

MS SQL коммерчески не использовал, но T-SQL и оптимизация запросов \
знакомы по PostgreSQL — переход не должен быть болезненным.

Хотел бы понять, как у вас устроена доменная декомпозиция и какие \
ожидания по объёму нового кода в первые месяцы. Готов созвониться в \
удобное время."

Output: you MUST return your result by calling the submit_cover_letter \
tool. Emit nothing outside the tool call. The "body" field of the \
tool call is the letter exactly as it should be sent to the recruiter.
"""


LETTER_TOOL_SCHEMA: dict[str, Any] = {
    "name": "submit_cover_letter",
    "description": "Сохранить черновик сопроводительного письма для одного отклика.",
    "input_schema": {
        "type": "object",
        "properties": {
            "body": {
                "type": "string",
                "description": ("Текст письма. 4-7 предложений на языке вакансии. Без приветствия и подписи."),
            },
            "language": {
                "type": "string",
                "enum": ["ru", "en"],
                "description": "Язык, на котором написано письмо.",
            },
        },
        "required": ["body", "language"],
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


def _match_block(match: MatchResult) -> str:
    lines = [
        "=== РЕЗУЛЬТАТ МАТЧИНГА ===",
        f"Score: {match.score:.2f}",
        f"Rationale: {match.rationale}",
    ]
    breakdown = match.payload.get("breakdown") if isinstance(match.payload, dict) else None
    if isinstance(breakdown, dict):
        for dim in ("skills", "seniority", "location_comp"):
            entry = breakdown.get(dim)
            if isinstance(entry, dict):
                score = entry.get("score")
                note = entry.get("note")
                if isinstance(score, int | float) and isinstance(note, str):
                    lines.append(f"- {dim}: {score:.2f} — {note}")
    red_flags = match.payload.get("red_flags") if isinstance(match.payload, dict) else None
    if isinstance(red_flags, list) and red_flags:
        lines.append("Red flags: " + "; ".join(str(rf) for rf in red_flags))
    lines.append("=== КОНЕЦ МАТЧИНГА ===")
    return "\n".join(lines)


def build_letter_system(resume: Resume) -> list[dict[str, Any]]:
    """Two cacheable system blocks: rules + resume content."""
    return [
        {"type": "text", "text": LETTER_RULES, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": _resume_block(resume), "cache_control": {"type": "ephemeral"}},
    ]


def build_letter_user(job: Job, match: MatchResult) -> str:
    return (
        f"{_job_block(job)}\n\n{_match_block(match)}\n\n"
        "Write the cover letter for the vacancy above and return it via "
        "the submit_cover_letter tool. Output language must match the "
        "vacancy language (Russian here unless the vacancy text is in English)."
    )


def compute_letter_prompt_hash(*, model: str, resume: Resume) -> str:
    """Stable identifier for ``(letter_version, model, resume_content)``.

    Excludes the vacancy on purpose — one row per (job, letter_version),
    not per unique vacancy text. The job_id is the table-level anchor.
    """
    digest = hashlib.sha256()
    digest.update(LETTER_VERSION.encode())
    digest.update(b"\0")
    digest.update(model.encode())
    digest.update(b"\0")
    digest.update(resume.id.encode())
    digest.update(b"\0")
    digest.update(resume.content.encode())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class LetterPayload:
    body: str
    language: str
    payload: dict[str, Any]


def validate_letter_payload(payload: dict[str, Any]) -> LetterPayload:
    """Validate parsed tool_use input. Re-check body / language presence."""
    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("letter tool input missing 'body'")
    language = payload.get("language")
    if not isinstance(language, str) or language not in ("ru", "en"):
        raise ValueError("letter tool input missing valid 'language' (ru/en)")
    return LetterPayload(body=body.strip(), language=language, payload=payload)


__all__ = [
    "LETTER_RULES",
    "LETTER_TOOL_SCHEMA",
    "LETTER_VERSION",
    "LetterPayload",
    "build_letter_system",
    "build_letter_user",
    "compute_letter_prompt_hash",
    "validate_letter_payload",
]
