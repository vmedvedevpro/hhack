---
date: 2026-05-26
participants: owner, assistant
summary: Phase 2.1 — detail-page парсер переписан на DOM+JSON-LD, feed-worker теперь не падает на одной вакансии, найдены и закрыты дыры в branded-вёрстке и в posted_at/location.
---

# Phase 2.1 — JSON-LD JobPosting в detail-парсере + resilient feed worker

## Симптом

Оператор показал branded-вакансию hh.ru/vacancy/133397925 (Сбер Data
Science, обёртка `<div class="tmpl_hh_content">…<div
class="vacancy-branded-user-content" data-qa="vacancy-description">…</div>`)
и сказал, что такие вакансии «не парсятся, надо как-то по-другому
обрабатывать».

## Что проверил

- Состояние БД по hh_id=133397925:
  `status='discovered'`, `detail_fetched_at=NULL`, все детали `NULL`.
  То есть detail-парсер по ней вообще не запускался.
- Покрытие на 11 уже `detailed` вакансиях:
  `full_text` 11/11, `employment_type` 11/11, `salary` 3/11,
  `location` 4/11, `posted_at` **0/11**.
- HTML branded-страницы (`artifacts/branded-133397925.html`):
  `data-qa="vacancy-description"` на месте, но нет
  `vacancy-salary` / `vacancy-view-raw-address` /
  `vacancy-view-creation-time` / `vacancy-view-employment-mode`.
  Зато есть полноценный `<script type="application/ld+json">` с
  `JobPosting` (description, datePosted, jobLocation, hiringOrganization).

Гипотеза «branded ломает description» оказалась ложной — описание
подхватилось бы, если бы worker дошёл. Реальные проблемы две:
prev-run worker умер посередине второго скана, а `posted_at` не
работает вообще нигде.

## Что сделал по коду

- `src/hhack/integrations/hh/job_page.py` — переписан:
  - `_EXTRACT_JS` теперь возвращает `{dom, json_ld}` — DOM-поля
    как раньше, плюс распарсенный первый `JobPosting` из
    `<script type="application/ld+json">`. Парс JSON-LD в браузере
    (там, где он живёт), чтобы Python ничего не доделывал руками.
  - `combine_extracted(raw, hh_id)` — чистая функция-мерджер.
    DOM-значение выигрывает; JSON-LD-значение подтыкается, когда
    DOM пуст. Логика построчно описана в [D-022](../decisions.md#d-022--2026-05-26--detail-page-extraction-reads-json-ld-jobposting-first-dom-second).
  - Хелперы: `_strip_html` (HTML→текст, сохраняя списки), `_json_ld_location`
    (`addressLocality`/`addressRegion`/`addressCountry` с поддержкой
    `Place` как массива), `_json_ld_salary`
    (`{minValue, maxValue, value}` → `"100000-150000 RUR"`).
  - Branded-fallback в DOM-селекторах: `[itemprop="description"]` и
    `.vacancy-branded-user-content` для full_text;
    `[data-qa="vacancy-address-with-map"]` для location.
- `src/hhack/workers/feed.py` — `try/except` вокруг каждой detail-итерации.
  Один сбой больше не убивает весь скан: hh_id запоминается в `failed`,
  пишется traceback через `logger.opt(exception=True).error(...)`,
  цикл идёт дальше. В конце — суммарный warning со списком failed.
  При следующем `hhack-feed scan` те же карточки снова всплывут в
  `list_pending_details` (status остался `discovered`).
- `tests/integrations/hh/test_job_page.py` — 14 unit-тестов на
  `_strip_html`, `_json_ld_location`, `_json_ld_salary`,
  `_parse_iso_datetime` и три сценария мерджа в `combine_extracted`
  (DOM выигрывает, JSON-LD заполняет дыры, всё пусто).

## Smoke-тесты

- `uv run pytest` — 25 passed (было 11).
- `uv run ruff check src tests` — all checks passed (после правки
  `–` EN DASH → `-` в форматтере salary).
- `uv run mypy src` — Success: no issues found in 23 source files.

## Что осталось

- Оператор перезапускает `hhack-feed scan` — должен подхватить 9
  застрявших `discovered` (включая 133397925) и заполнить им детали.
  По итогу проверить, что `posted_at` теперь не NULL для всех
  свежеобработанных, и что `location` стало плотнее.
- Если на какой-то странице снова прилетит exception — будет в логе с
  traceback и hh_id, не аборт скана.
- Дальше — закрыть оставшийся пункт Phase 2.1 (низкоинтенсивный прогон
  ≥1 неделю) и переходить на Phase 3 (matcher).
