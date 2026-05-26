---
date: 2026-05-26
participants: owner, assistant
summary: Phase 3 — matcher landed inline в scan-цикле. Plain markdown резюме, score 0..1 + breakdown, prompt caching на резюме, idempotency через prompt_hash. Live validation owed.
---

# Phase 3 — matcher inline в scan

## Контекст

После закрытия Phase 2.1 переходим к Phase 3: оценка соответствия
(job, resume) через Claude Sonnet, persistance в `match_results`,
порог `MATCH_THRESHOLD` решает `matched` vs `skipped`. До кода нужно
было закрыть два блокера из `open-questions.md` (формат резюме, схема
скоринга) и одну развилку по тому, как запускать матчер.

## Решения (см. D-023)

- **Резюме** — plain markdown, два слота (`a`, `b`) из
  `RESUME_A_PATH` / `RESUME_B_PATH`. Никакого YAML frontmatter —
  если позже понадобятся хард-фильтры, добавим на тот же файл.
- **Schema** — `score: 0..1` + `rationale` + `breakdown` (skills,
  seniority, location_comp) + `red_flags: string[]`. Threshold
  работает только по `score`; breakdown остаётся в `payload` (JSONB)
  для ручной отладки.
- **Run mode** — матчер встроен в `hhack-feed scan` per-vacancy.
  Один человеческий поток: open → details → match → решение → пауза
  → следующая. Без батчей. Этот выбор — антидетекшен: HH ловит
  cadence/behavioral fingerprint, а не сам факт LLM. Batched-matcher
  «scrape, then later evaluate» был бы отличимым паттерном.

## Что появилось в коде

- `src/hhack/matching/resume.py` — `Resume(id, path, content)` +
  `load_resumes(settings) -> [Resume(a), Resume(b)]`.
- `src/hhack/integrations/anthropic_client.py` — `AnthropicClientProtocol`
  + `AsyncAnthropicClient` (SDK + линейный backoff на 429/529,
  4 попытки с задержкой `5*attempt` секунд).
- `src/hhack/matching/prompts.py` — `MATCH_RULES`,
  `build_match_system` (две кешируемых система-блока: правила и
  резюме), `build_match_user` (вакансия), `compute_prompt_hash`
  (sha256 от `PROMPT_VERSION || model || resume_id || resume.content`,
  не включает вакансию), `parse_match_response` (толерантный JSON
  парсер: code-fence, плоский, мусор → ValueError).
- `src/hhack/matching/matcher.py` — `Matcher.match(job, resume)
  -> MatchResult`, оборачивает клиента и парс.
- `src/hhack/domain/match.py` + `migrations/versions/1_match_results.py` —
  таблица с UNIQUE `(job_id, resume_id, prompt_hash)`.
- `src/hhack/persistence/match_repository.py` — `exists / save /
  best_score`. Save идемпотентен через `ON CONFLICT DO NOTHING`.
- `JobRepositoryProtocol` расширен: `list_processable(limit)`
  (discovered ∪ detailed), `mark_matched(job_id)`, `mark_skipped(job_id)`.
- `src/hhack/bootstrap.py` — `_session_factory` кэширован per-URL,
  чтобы job + match репозитории шарили один пул. Новые
  `build_anthropic_client`, `build_matcher`, `build_match_repository`,
  `build_resumes`.
- `src/hhack/workers/feed.py` — переписан под новый lifecycle.
  `_process_job` вынесен из `_scan` и пригоден к unit-тесту с
  фейками. Новый CLI флаг `--no-match` для дешёвых dry-run без API.

## Lifecycle (новый)

```
status:
  discovered  -- card harvested from SERP, no detail fetched
  detailed    -- detail page parsed, full_text saved
  matched     -- best score >= MATCH_THRESHOLD, ready for Phase 4
  skipped     -- best score <  MATCH_THRESHOLD, ignore in Phase 4

scan loop (per vacancy):
  if status == discovered:
      fetch_job_details + save_details   -> detailed
  for resume in (a, b):
      if exists(job, resume, prompt_hash): skip
      else: matcher.match + match_repo.save
  best = match_repo.best_score(job.id)
  if best is None: leave in detailed (next scan retries)
  elif best >= threshold: mark_matched
  else:                   mark_skipped
```

## Тесты

55 passed (было 39):

- `tests/matching/test_resume.py` — load_resumes (оба, дубликат
  пути, отсутствующая переменная, отсутствующий файл, пустой файл).
- `tests/matching/test_prompts.py` — build_system/user, hash
  стабильность, парс fenced/plain/мусор/clamp.
- `tests/matching/test_matcher.py` — round-trip с FakeAnthropicClient.
- `tests/integrations/test_anthropic_client.py` — retry на 529,
  no-retry на 400, gives up after 4, usage extraction (с / без
  cache_*).
- `tests/persistence/test_fake_match_repository.py` — exists, save
  идемпотентность, best_score.
- `tests/workers/test_feed_process_job.py` — discovered→matched,
  discovered→skipped, detailed→matched без fetch, не-перевызов
  exists-матчей, no-match флаг.

## Что осталось

- **Live validation.** Нужен прогон с настоящим `ANTHROPIC_API_KEY`
  и реальными резюме оператора. Цель — 200-500 решений, ручной
  обзор, калибровка `MATCH_RULES` / `MATCH_THRESHOLD`. Если правила
  меняются — bump `PROMPT_VERSION` (сейчас `match-v2` после D-025),
  чтобы старые строки в `match_results` сохранились для сравнения,
  а новые появились автоматически.
- **Миграция.** `uv run alembic upgrade head` нужно прогнать на
  оператора-локальной БД, чтобы создать таблицу `match_results`.
- **Phase 4 (cover letter)** будет встроен в тот же inline-цикл,
  ветку после `mark_matched(job.id)`. Архитектурно это уже готовое
  место подключения.

## Postscript (2026-05-26): tool use вместо free-form JSON

Первый live-прогон `hhack-feed scan` с реальным API сломался на
`JSONDecodeError: Expecting ',' delimiter` — Sonnet 4.6 однажды
выдал `rationale` с неэкранированным символом, и `json.loads` упал.
Это типичный сбой free-form JSON-выхода.

Лекарство — Anthropic tool use. См. [D-025](../decisions.md#d-025--2026-05-26--matcher-output-via-anthropic-tool-use-not-free-form-json).
Бамп `PROMPT_VERSION` `match-v1` → `match-v2`: уже сохранённые
результаты остаются, но всё новое будет сматчено заново через
typed schema, и невалидный JSON структурно невозможен. Тесты на
matcher и `_process_job` адаптированы; `FakeAnthropicClient`
получил `create_tool_call`.
