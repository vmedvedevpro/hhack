# ruff: noqa: RUF001
"""Applicant-zone resume page → matcher-ready markdown.

HH ships the entire resume payload as a JSON blob inside
``<template id="HH-Lux-InitialState">``. The DOM also renders it, but
the template is the canonical SEO/SSR contract HH owns, so we read from
the template and ignore the rendered HTML.

``extract_resume_markdown`` is a pure function over the page HTML so we
can unit-test the formatter on a synthetic state fixture without a
browser. ``fetch_resume_markdown`` is the thin async wrapper for the
sync worker.

PII fields (firstName, lastName, gender, email, phone, photo,
personalSite, metro, residenceDistrict, contacts, certificates, ...)
are intentionally omitted — the matcher does not need them and we do
not want them in cached files that could later be shared for debugging.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, cast

from loguru import logger
from playwright.async_api import Page

_TEMPLATE_RE = re.compile(
    r'<template[^>]*id="HH-Lux-InitialState"[^>]*>(.*?)</template>',
    re.DOTALL,
)

# Short enum tables. Keep them tight — anything not in the map renders
# as the raw HH code so an LLM can still reason about it.
_EMPLOYMENT_LABELS: dict[str, str] = {
    "full": "Полная",
    "part": "Частичная",
    "project": "Проектная",
    "volunteer": "Волонтёрство",
    "probation": "Стажировка",
}
_WORK_SCHEDULE_LABELS: dict[str, str] = {
    "fullDay": "Полный день",
    "full_day": "Полный день",
    "shift": "Сменный график",
    "flexible": "Гибкий график",
    "remote": "Удалённо",
    "flyInFlyOut": "Вахта",
}
_WORK_FORMAT_LABELS: dict[str, str] = {
    "REMOTE": "Удалённо",
    "HYBRID": "Гибрид",
    "ON_SITE": "Офис",
    "FIELD_WORK": "Разъездной",
}
_RELOCATION_LABELS: dict[str, str] = {
    "no_relocation": "Не готов",
    "relocation_possible": "Готов",
    "relocation_desirable": "Желает",
    "change_relocation": "Готов сменить",
}
_BUSINESS_TRIP_LABELS: dict[str, str] = {
    "never": "Не готов",
    "sometimes": "Готов иногда",
    "ready": "Готов",
}
# Top-10 cities cover the vast majority of operator locations. Anything
# not in the map renders as ``area=<id>`` so the LLM can still see that
# the field was set.
_AREA_LABELS: dict[int, str] = {
    1: "Москва",
    2: "Санкт-Петербург",
    3: "Екатеринбург",
    4: "Новосибирск",
    16: "Казань",
    66: "Нижний Новгород",
    76: "Ростов-на-Дону",
    88: "Краснодар",
    113: "Россия (страна)",
    1438: "Кемерово",
}

_MONTH_NAMES = (
    "январе",
    "феврале",
    "марте",
    "апреле",
    "мае",
    "июне",
    "июле",
    "августе",
    "сентябре",
    "октябре",
    "ноябре",
    "декабре",
)
_MONTHS_NOM = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)


class ResumeParseError(RuntimeError):
    """Raised when the page does not contain a parsable initial state."""


def _extract_initial_state(html: str) -> dict[str, Any]:
    match = _TEMPLATE_RE.search(html)
    if not match:
        raise ResumeParseError("HH-Lux-InitialState template not found in page HTML")
    try:
        return cast(dict[str, Any], json.loads(match.group(1)))
    except json.JSONDecodeError as exc:
        raise ResumeParseError(f"HH-Lux-InitialState is not valid JSON: {exc.msg}") from exc


def _first(items: Any) -> Any:
    if isinstance(items, list) and items:
        return items[0]
    return None


def _string_of(items: Any) -> Any:
    """HH wraps almost every applicantResume field as ``[{"string": value}]``."""
    head = _first(items)
    if isinstance(head, dict):
        return head.get("string")
    return None


def _resolve_education_levels(state: dict[str, Any]) -> dict[str, str]:
    raw = state.get("educationLevels")
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                value = entry.get("value")
                text = entry.get("text")
                if isinstance(value, str) and isinstance(text, str):
                    out[value] = text
    return out


def _format_salary(ar: dict[str, Any]) -> str | None:
    head = _first(ar.get("salary"))
    if not isinstance(head, dict):
        return None
    amount = head.get("amount")
    currency = head.get("currency")
    if not isinstance(amount, int | float):
        return None
    if isinstance(currency, str) and currency:
        return f"{int(amount)} {currency}"
    return f"{int(amount)}"


def _format_area(ar: dict[str, Any]) -> str | None:
    area_id = _string_of(ar.get("area"))
    if not isinstance(area_id, int):
        return None
    return _AREA_LABELS.get(area_id, f"area={area_id}")


def _format_total_experience(months: Any) -> str | None:
    if not isinstance(months, int) or months <= 0:
        return None
    years, rem = divmod(months, 12)
    parts: list[str] = []
    if years:
        parts.append(f"{years} {_plural_years(years)}")
    if rem:
        parts.append(f"{rem} мес")
    return " ".join(parts) if parts else None


def _plural_years(n: int) -> str:
    n_mod_100 = n % 100
    n_mod_10 = n % 10
    if 11 <= n_mod_100 <= 14:
        return "лет"
    if n_mod_10 == 1:
        return "год"
    if 2 <= n_mod_10 <= 4:
        return "года"
    return "лет"


def _format_date(value: str | None) -> str | None:
    """Render ``YYYY-MM-DD`` as ``месяц YYYY``. Returns None for missing dates."""
    if not isinstance(value, str) or len(value) < 7:
        return None
    try:
        year = int(value[0:4])
        month = int(value[5:7])
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    return f"{_MONTHS_NOM[month - 1]} {year}"


def _format_enum_list(items: Any, labels: dict[str, str]) -> list[str]:
    if not isinstance(items, list):
        return []
    out: list[str] = []
    for entry in items:
        code = entry.get("string") if isinstance(entry, dict) else None
        if not isinstance(code, str):
            continue
        out.append(labels.get(code, code))
    return out


def _format_header(ar: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    title = _string_of(ar.get("title"))
    if isinstance(title, str) and title.strip():
        lines.append(f"# {title.strip()}")
        lines.append("")

    facts: list[tuple[str, str | None]] = []
    salary = _format_salary(ar)
    if salary:
        facts.append(("Желаемая зарплата", salary))
    area = _format_area(ar)
    if area:
        facts.append(("Локация", area))
    total_exp = _format_total_experience(_string_of(ar.get("totalExperience")))
    if total_exp:
        facts.append(("Общий опыт", total_exp))
    role = _first(ar.get("professionalRole"))
    if isinstance(role, dict) and isinstance(role.get("text"), str):
        facts.append(("Профессиональная роль", role["text"]))
    employment = _format_enum_list(ar.get("employment"), _EMPLOYMENT_LABELS)
    if employment:
        facts.append(("Тип занятости", ", ".join(employment)))
    schedule = _format_enum_list(ar.get("workSchedule"), _WORK_SCHEDULE_LABELS)
    if schedule:
        facts.append(("График", ", ".join(schedule)))
    formats = _format_enum_list(ar.get("workFormats"), _WORK_FORMAT_LABELS)
    if formats:
        facts.append(("Формат", ", ".join(formats)))
    relocation_code = _string_of(ar.get("relocation"))
    if isinstance(relocation_code, str):
        facts.append(("Переезд", _RELOCATION_LABELS.get(relocation_code, relocation_code)))
    trip_code = _string_of(ar.get("businessTripReadiness"))
    if isinstance(trip_code, str):
        facts.append(("Командировки", _BUSINESS_TRIP_LABELS.get(trip_code, trip_code)))

    for label, value in facts:
        if value:
            lines.append(f"**{label}:** {value}  ")
    if facts:
        lines.append("")
    return lines


def _clean_text(value: str) -> str:
    """Strip + unescape HTML entities. HH stores user-typed prose with ``&amp;`` etc."""
    return html_lib.unescape(value).strip()


def _format_about(ar: dict[str, Any]) -> list[str]:
    head = _first(ar.get("skills"))
    text = head.get("string") if isinstance(head, dict) else None
    if not isinstance(text, str) or not text.strip():
        return []
    return ["## О себе", "", _clean_text(text), ""]


def _format_experience(ar: dict[str, Any]) -> list[str]:
    experiences = ar.get("experience")
    if not isinstance(experiences, list) or not experiences:
        return []
    lines: list[str] = ["## Опыт работы", ""]
    for entry in experiences:
        if not isinstance(entry, dict):
            continue
        company = entry.get("companyName") or ""
        position = entry.get("position") or ""
        start = _format_date(entry.get("startDate"))
        end = _format_date(entry.get("endDate")) or "по настоящее время"
        title_parts: list[str] = []
        if position:
            title_parts.append(str(position))
        if company:
            title_parts.append(str(company))
        title = " · ".join(title_parts) if title_parts else "(без названия)"
        lines.append(f"### {title}")
        if start or end:
            lines.append(f"*{start or '?'} — {end}*")
        description = entry.get("description")
        if isinstance(description, str) and description.strip():
            lines.append("")
            lines.append(_clean_text(description))
        lines.append("")
    return lines


def _format_skills(ar: dict[str, Any]) -> list[str]:
    skills = _collect_skills(ar)
    if not skills:
        return []
    return ["## Ключевые навыки", "", ", ".join(skills), ""]


def _collect_skills(ar: dict[str, Any]) -> list[str]:
    """Prefer resumeApplicantSkills (resolved names), fall back to keySkills/advancedKeySkills."""
    seen: set[str] = set()
    out: list[str] = []
    ras = ar.get("resumeApplicantSkills")
    if isinstance(ras, list):
        for entry in ras:
            if not isinstance(entry, dict) or entry.get("category") != "SKILL":
                continue
            name = entry.get("name")
            if isinstance(name, str) and name.strip() and name not in seen:
                seen.add(name)
                out.append(name.strip())
    if out:
        return out
    aks = ar.get("advancedKeySkills")
    if isinstance(aks, list):
        for entry in aks:
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name.strip() and name not in seen:
                seen.add(name)
                out.append(name.strip())
    if out:
        return out
    ks = ar.get("keySkills")
    if isinstance(ks, list):
        for entry in ks:
            name = entry.get("string") if isinstance(entry, dict) else None
            if isinstance(name, str) and name.strip() and name not in seen:
                seen.add(name)
                out.append(name.strip())
    return out


def _format_languages(ar: dict[str, Any]) -> list[str]:
    ras = ar.get("resumeApplicantSkills")
    if not isinstance(ras, list):
        return []
    rows: list[str] = []
    for entry in ras:
        if not isinstance(entry, dict) or entry.get("category") != "LANG":
            continue
        name = entry.get("name")
        level = entry.get("level")
        level_name = level.get("name") if isinstance(level, dict) else None
        if isinstance(name, str) and name.strip():
            if isinstance(level_name, str) and level_name.strip():
                rows.append(f"- {name.strip()} — {level_name.strip()}")
            else:
                rows.append(f"- {name.strip()}")
    if not rows:
        return []
    return ["## Языки", "", *rows, ""]


def _format_education(ar: dict[str, Any], levels: dict[str, str]) -> list[str]:
    blocks: list[str] = []
    level_code = _string_of(ar.get("educationLevel"))
    level_text = levels.get(level_code, level_code) if isinstance(level_code, str) else None
    if isinstance(level_text, str):
        blocks.append(f"**Уровень:** {level_text}")
        blocks.append("")

    primary = ar.get("primaryEducation")
    if isinstance(primary, list):
        for entry in primary:
            if not isinstance(entry, dict):
                continue
            parts: list[str] = []
            name = entry.get("name")
            year = entry.get("year")
            organization = entry.get("organization")
            result = entry.get("result")
            if isinstance(name, str) and name.strip():
                if isinstance(year, int):
                    parts.append(f"**{name.strip()}** ({year})")
                else:
                    parts.append(f"**{name.strip()}**")
            extras = " — ".join(s for s in (organization, result) if isinstance(s, str) and s.strip())
            if extras:
                parts.append(f"*{extras}*")
            if parts:
                blocks.extend(parts)
                blocks.append("")

    additional = ar.get("additionalEducation")
    if isinstance(additional, list) and additional:
        blocks.append("### Курсы и дополнительное образование")
        blocks.append("")
        for entry in additional:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("result")
            organization = entry.get("organization")
            year = entry.get("year")
            label_parts: list[str] = []
            if isinstance(name, str) and name.strip():
                label_parts.append(name.strip())
            if isinstance(organization, str) and organization.strip():
                label_parts.append(organization.strip())
            if isinstance(year, int):
                label_parts.append(str(year))
            if label_parts:
                blocks.append(f"- {' — '.join(label_parts)}")
        blocks.append("")

    if not blocks:
        return []
    return ["## Образование", "", *blocks]


def extract_resume_markdown(html: str) -> str:
    """Parse one applicant-zone resume page HTML into matcher-ready markdown."""
    state = _extract_initial_state(html)
    ar = state.get("applicantResume")
    if not isinstance(ar, dict):
        raise ResumeParseError("applicantResume missing from initial state")

    levels = _resolve_education_levels(state)

    sections: list[list[str]] = [
        _format_header(ar),
        _format_about(ar),
        _format_experience(ar),
        _format_skills(ar),
        _format_education(ar, levels),
        _format_languages(ar),
    ]
    lines: list[str] = []
    for block in sections:
        lines.extend(block)
    # Collapse trailing blank lines.
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


async def fetch_resume_markdown(page: Page, resume_id: str) -> str:
    """Navigate to /resume/<id> and return the parsed markdown."""
    bound = logger.bind(component="resume_page", resume_id=resume_id)
    url = f"https://hh.ru/resume/{resume_id}"
    bound.info("opening {url}", url=url)
    await page.goto(url, wait_until="domcontentloaded")
    html = await page.content()
    markdown = extract_resume_markdown(html)
    bound.info("parsed resume into {n} chars of markdown", n=len(markdown))
    return markdown


APPLICANT_RESUMES_URL = "https://hh.ru/applicant/resumes"
_RESUME_HREF_RE = re.compile(r"/resume/([0-9a-fA-F]{16,})")


async def collect_resume_ids(page: Page) -> list[str]:
    """Open ``/applicant/resumes`` and return de-duplicated HH resume ids."""
    bound = logger.bind(component="resume_page", action="list")
    bound.info("opening {url}", url=APPLICANT_RESUMES_URL)
    await page.goto(APPLICANT_RESUMES_URL, wait_until="domcontentloaded")
    hrefs: list[str] = await page.eval_on_selector_all(
        'a[href*="/resume/"]',
        "els => els.map(e => e.getAttribute('href') || '')",
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for href in hrefs:
        match = _RESUME_HREF_RE.search(href)
        if not match:
            continue
        resume_id = match.group(1)
        if resume_id in seen:
            continue
        seen.add(resume_id)
        ordered.append(resume_id)
    bound.info("found {n} resume id(s)", n=len(ordered))
    return ordered


__all__ = [
    "APPLICANT_RESUMES_URL",
    "ResumeParseError",
    "collect_resume_ids",
    "extract_resume_markdown",
    "fetch_resume_markdown",
]
