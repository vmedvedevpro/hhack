---
date: 2026-05-26
participants: owner, assistant
summary: Phase 3.1 — резюме больше не маркдаун-файлы, а кэш, наполняемый из HH applicant zone. Парсер тащит JSON state из `<template id="HH-Lux-InitialState">`, slot id = HH resume_id.
---

# Phase 3.1 — HH applicant-zone resume sync

## Контекст

Сразу после Phase 3 оператор предложил: вместо `RESUME_A_PATH` /
`RESUME_B_PATH` грузить резюме автоматически из HH applicant zone.
Логично: HH строит фид по этим же резюме, значит и матчер должен
смотреть на тот же текст, чтобы не было drift'а.

См. [D-024](../decisions.md#d-024--2026-05-26--resumes-come-from-hh-applicant-zone-not-hand-managed-markdown).

## Что сделал по коду

### Разведка

- `hhack-browser dump-resumes` (новая generic-команда в
  `tools/browser.py`) — открывает `/applicant/resumes`, собирает
  ссылки `/resume/<id>`, дампит HTML+скрин каждого в
  `artifacts/resumes-<ts>/`. После запуска у оператора нашлось
  2 резюме.
- На дампах: applicant-zone template'а имеет крайне мало
  `data-qa` (< 10), но HH встраивает весь payload как JSON внутри
  `<template id="HH-Lux-InitialState">`. Все нужные поля лежат в
  `state.applicantResume.*`: `title`, `salary`, `area`, `experience[]`,
  `keySkills`/`advancedKeySkills`/`resumeApplicantSkills`,
  `primaryEducation[]`, `additionalEducation[]`, `educationLevel`,
  `language[]`, `workSchedule`, `workFormats`, `relocation`,
  `businessTripReadiness`, `professionalRole`, `totalExperience`.
- Бонус: `resumeApplicantSkills` уже резолвлен с человеко-читаемыми
  именами (для языков ещё и с CEFR level: `L1 - Родной`, `B1 — Средний`).
  `educationLevels` лежит на верхнем уровне state — словарь
  `bachelor → Бакалавр`.

### Парсер

`src/hhack/integrations/hh/resume_page.py`:

- `extract_resume_markdown(html) -> str` — чистая, вытаскивает
  template-state, форматирует в markdown секциями: header (факты),
  «О себе», «Опыт работы», «Ключевые навыки», «Образование» (+ курсы),
  «Языки». Поддерживает: HTML-unescape свободного текста,
  плюрализацию русских лет (`1 год / 2 года / 5 лет`), форматирование
  ISO-дат в `месяц YYYY`, fallback'и для unknown enum-кодов (рендерим
  как есть, чтобы LLM хотя бы видела факт).
- Hardcoded mini-словари для `employment`, `workSchedule`,
  `workFormats`, `relocation`, `businessTripReadiness`, плюс топ-10
  `area_id`. Educational levels — берутся прямо из state.
- `fetch_resume_markdown(page, resume_id)` — async обёртка.
- `collect_resume_ids(page)` — открывает `/applicant/resumes`,
  возвращает дедуплицированный список HH resume_ids (используется
  и в `tools/browser.py dump-resumes`, и в новом `sync-resumes`).
- **Что НЕ попадает в markdown:** firstName/lastName/email/phone/
  photo/personalSite/metro/residenceDistrict, рекомендации, портфолио,
  сертификаты, водительские права. Резюме в кэше можно показать
  третьему лицу без утечки PII.

### Sync-команда

`hhack-feed sync-resumes`:

1. open persistent context, `collect_resume_ids(page)`
2. для каждого id (с jitter-паузой `min_seconds_between_actions`):
   - `fetch_resume_markdown(page, id)` → markdown
   - сравнить с существующим `resumes/cache/<id>.md`
   - записать, если отличается (или впервые)
3. лог: `N added, N updated, N unchanged, cache=<path>`

Идемпотентно: если на HH ничего не менялось — sync пишет 0 файлов.

### Loader + конфиг

- `matching/resume.py` теперь читает все `*.md` из кэш-директории.
  Slot id = filename без `.md` (т.е. HH resume_id). Сортировка по
  имени для стабильности.
- `config.py`: убраны `resume_a_path` / `resume_b_path`, добавлен
  `resumes_cache_dir` (default `./resumes/cache`).
- `.env.example` обновлён.
- `match_results.resume_id` расширен `String(8)` → `String(64)`
  миграцией `2_widen_resume_id.py` (HH id — 38 hex).
- `domain/match.py`: то же изменение в SQLAlchemy модели.

### Cleanup

- Удалены `resumes/example_a.md` / `resumes/example_b.md` —
  больше не источник данных.
- Создан `resumes/README.md` (объясняет, что кэш наполняется
  `sync-resumes`), gitignore exception сузился с `!resumes/example_*.md`
  до `!resumes/README.md`.

### Тесты

64 passed (было 55, +9 для парсера резюме). Покрытие:

- `tests/integrations/hh/test_resume_page.py` — 9 тестов на чистый
  парсер: полное резюме, отсутствующие optional-поля, неизвестные
  enum-коды, неизвестный area_id, плюрализация лет, fallback chain
  для skills, отсутствующий template, невалидный JSON, отсутствующий
  `applicantResume`. Все на synthetic state — без реальных дампов
  в репо.
- `tests/matching/test_resume.py` переписан на чтение из кэш-директории.

## Smoke

- `uv run ruff check src tests` — all checks passed.
- `uv run mypy src` — no issues, 30 source files.
- `uv run pytest` — 64 passed.
- Прогон парсера на дампах оператора (2 резюме): markdown выглядит
  адекватно, поля разложены по секциям, опыт по местам с описаниями,
  навыки, образование, языки. Сохранён в `artifacts/parser-output.md`
  для глаза (не коммитится — `artifacts/` gitignored).

## Что осталось

- **Live-прогон `hhack-feed sync-resumes`** оператором на реальной
  сессии — убедиться, что 2 резюме корректно лягут в `resumes/cache/`.
- **Миграция:** `uv run alembic upgrade head` (применит и
  `1_match_results`, и `2_widen_resume_id`).
- После этого — Phase 3 live-validation, ту же что и до 3.1:
  `hhack-feed scan --max-details 5` и обзор 5 решений.
