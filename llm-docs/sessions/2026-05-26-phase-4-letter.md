---
date: 2026-05-26
participants: owner, assistant
summary: Phase 4 — cover letter inline в scan-цикле. Prompts-as-code (LETTER_RULES + banned phrases), tool use, best-scoring resume, draft-only в новой applications. Live validation owed.
---

# Phase 4 — cover letter generation

## Контекст

После закрытия Phase 3 (matcher inline + tool use фикс) переходим к
Phase 4. Цель — генерировать сопроводительное письмо для каждой
вакансии, которая получила `matched`, сразу в том же scan-цикле.
Отправка остаётся за Phase 5 (`DRY_RUN` ON по умолчанию).

Три ключевые развилки оператор закрыл сразу:

- **Хранилище шаблона** — константы в `prompts.py`-style модуле, без
  файла на диске (как `MATCH_RULES`).
- **Когда генерим** — inline в scan после `mark_matched`, не отдельной
  командой.
- **Язык письма** — модель сама подхватывает из текста вакансии (нет
  отдельного detect-шага).

Полное обоснование — [D-026](../decisions.md#d-026--2026-05-26--cover-letter-generation--prompts-as-code-tool-use-inline-в-scan-best-score-resume).

## Что появилось в коде

- `src/hhack/domain/application.py` + `migrations/versions/3_applications.py`
  — таблица с `UNIQUE (job_id, prompt_hash)`. `status='draft'` дефолт,
  `sent_at` / `hh_response_id` nullable (Phase 5).
- `src/hhack/persistence/application_repository.py` — Protocol +
  SQLAlchemy + Fake. `exists`, `save` (ON CONFLICT DO NOTHING).
- `src/hhack/matching/letter_prompts.py`:
  - `LETTER_RULES` — 4-7 предложений, ≤800 символов, без приветствий
    и подписей, на языке вакансии, без эмодзи. Структура: цеплялка
    про вакансию → 1-2 совпадения из резюме → что хотел бы обсудить
    → готов созвониться. Список banned phrases прямо в правилах
    («Меня заинтересовала ваша вакансия», «коммуникабельный», «hope
    to hear from you soon», и т.д.).
  - `LETTER_TOOL_SCHEMA` — tool `submit_cover_letter` с
    `{body: string, language: "ru"|"en"}`.
  - `compute_letter_prompt_hash` — sha256 от `LETTER_VERSION || model
    || resume.id || resume.content`. Бамп `LETTER_VERSION` = свежий
    draft при следующем scan.
- `src/hhack/matching/letter_writer.py` — `LetterWriter.write(job,
  resume, match)` → `LetterDraft` через `create_tool_call`.
  Temperature 0.4 (письмо — творческая задача, score 0.0 не подходит).
- `src/hhack/persistence/match_repository.py` расширен:
  `best_match(job_id) -> MatchResult | None`. Возвращает доменный
  dataclass с `payload` для прокидывания breakdown в letter prompt.
- `src/hhack/bootstrap.py`: `build_letter_writer`,
  `build_application_repository`. Anthropic client шарится между
  matcher и writer (Sonnet vs Haiku — разные `model` параметры).
- `src/hhack/workers/feed.py`:
  - `_process_job` принимает опциональные `application_repo` +
    `letter_writer`. После `mark_matched` вызывает `_draft_letter`,
    который вытягивает best match, находит резюме в локальном кэше,
    проверяет idempotency и пишет draft.
  - CLI флаг `--no-letter` (опциональный, по умолчанию выключен).
  - HH-pacer **не** распространяется на letter — это LLM-only вызов,
    HH ничего не видит.
- `src/hhack/tools/letter_export.py` + `hhack-feed export-letters` —
  markdown review writer: вакансия, score, match rationale, тело
  письма quote-blocked. Аналог `export-matches`.

## Lifecycle (расширенный)

```
discovered → fetch_job_details → detailed
detailed   → match (both resumes) → matched | skipped
matched    → write_letter (best resume) → application(status=draft)
             status джобы остаётся matched (Phase 5 двинет в applied/failed)
skipped    → конец, drafts не пишутся
```

## Тесты

81 passed (было 67, +14 на letter pipeline):

- `tests/matching/test_letter_prompts.py` — 6 тестов: build_system
  с cache_control, build_user с match context, tool schema required,
  hash стабильность + резюме/модель чувствительность, validate happy
  path, validate отвергает мусор.
- `tests/matching/test_letter_writer.py` — 2 теста: round-trip
  через FakeAnthropicClient.create_tool_call, ошибка при bad payload.
- `tests/persistence/test_fake_application_repository.py` — 3 теста:
  save/exists, idempotency, разный prompt_hash → новая строка.
- `tests/workers/test_feed_process_job.py` расширен (+3 теста):
  letter drafted для matched, не drafted для skipped, не дублируется
  при повторном process_job на той же джобе.

## Smoke

- `uv run ruff check src tests` — all checks passed.
- `uv run mypy src` — no issues, 36 source files.
- `uv run pytest` — 81 passed.

## Что осталось

- **Миграция:** `uv run alembic upgrade head` на оператора-локальной
  БД (применит `3_applications`).
- **Live run** оператором с реальным API: `uv run hhack-feed scan
  --max-details 5`. Для уже-matched джоб (на которые матчер
  отработал в Phase 3) повторный scan сначала ничего не сделает —
  status у них уже `matched`, и `list_processable` их не выберет.
  Чтобы перегенерить letters для тех jobs, нужно либо дождаться
  свежих матчей, либо вручную сбросить status на `detailed` (после
  чего scan переcметчит и сразу же сгенерит письма).
- **Review:** `uv run hhack-feed export-letters` после первых
  драфтов, оператор читает 50+, калибрует `LETTER_RULES` / банлист.
  Bump `LETTER_VERSION` при изменениях.
- **Phase 5 (submit)** будет реагировать на `applications WHERE
  status='draft'`, выберет апплай-flow на странице вакансии, заполнит
  resume + cover_letter и нажмёт «Откликнуться». `DRY_RUN=true` —
  пишет план, не нажимает.

## Итерации на LETTER_RULES (2026-05-26 live ramp)

Прогнали ramp на одних и тех же 10 matched вакансиях, между прогонами
дропали `applications`, возвращали джобы в `detailed` и бампили
`LETTER_VERSION`.

| Версия | Что добавили | Что подтвердил прогон |
|---|---|---|
| `letter-v1` | первоначальные правила, ≤800 chars | модель писала без приветствия и с длинными тире |
| `letter-v2` | приветствие «Здравствуйте,» в начале, бан em dash, бан подписи в конце | em dash почти ушёл, но Haiku ещё путал |
| `letter-v3` | бан «это именно то», бан опенинга «Интересует вакансия X в Y» | заходы стали гибче; вместо банов появилось «Интересует возможность X» |
| `letter-v4` | весь rules-блок перевели на английский (output language must match vacancy), 4-6 sentences, ≤600 chars target | дисциплина лучше; «Интересует возможность» всё ещё проскакивает в ~6/10 |
| `letter-v5` | extended bad examples ("это близко к тому", "это именно то место"), запрет на дамп шкалы 1-5 ЕВЕН если вакансия её просит, calibration example body с placeholder компанией, и переключили дефолт-модель Haiku → Sonnet | «Интересует возможность» исчез у Sonnet (0/10), дамп шкалы пропал у Sonnet, calibration pattern явно проглядывает |

Side-by-side Haiku 4.5 vs Sonnet 4.6 на letter-v5 (один и тот же
промпт, один и тот же набор вакансий):

| Правило | Sonnet 4.6 | Haiku 4.5 |
|---|---|---|
| em dash (`—`) | 0/10 | 4/10 |
| «Интересует возможность X» | 0/10 | 2/10 |
| Дамп шкалы N/5 | 0/10 | 1/10 (Miractal: «EF Core - 2, RabbitMQ - 2 …» в самом хвосте после «Готов созвониться») |
| «погрузиться» в self-description | 0/10 | 1/10 («готов быстро погружаться в новый стек») |
| Средняя длина / max | 724 / 877 | 787 / 967 |
| Приветствие | 10/10 | 10/10 |

Вывод: Haiku даже с расширенным letter-v5 промптом игнорирует ~30%
длинных negative-rules — подтверждение того, что было видно по D-025
на матчере. Дефолт-модель остаётся Sonnet 4.6.

## Evals — пока deferred

Сейчас корпус ~10-20 драфтов, ручной просмотр одного export-файла
занимает 5 минут, цикл «правка промпта → прогон → чтение» работает
быстрее любых evals. По мере того, как Phase 5 даст 50+ драфтов в
неделю:

1. **Rule-based detector** первым (2-4 ч работы, $0 на API): regex на
   em dash, banned-phrases, длину >600, numeric N/M дампы, отсутствие
   приветствия. Может стать pre-commit / CI gate и встроиться как
   post-write retry внутри `LetterWriter` для самых жёстких правил.
2. **LLM-judge eval по 4 dimensions** (relevance / originality / tone
   / hook quality) только если rule-based недостаточен (~$0.25 на 50
   писем, 6-8 ч работы).
3. **Side-by-side A/B harness** — позже, когда возникнет частая
   итерация на промпте и нужен автоматический tiebreaker.

В roadmap.md добавлен deferred-пункт в Phase 4.
