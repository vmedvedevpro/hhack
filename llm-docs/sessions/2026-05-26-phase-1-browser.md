---
date: 2026-05-26
participants: owner, assistant
summary: Phase 1 — собрали persistent Chromium context со stealth и завели hhack-browser CLI; ручной login + fingerprint test остаются за оператором.
---

# Phase 1 — persistent browser session

## Что обсудили

Phase 0 закрыт в прошлой сессии, владелец дал команду переходить к
Phase 1. Открытый из kickoff'а пункт — какую stealth-библиотеку взять
(`playwright-stealth` vs `rebrowser-patches`). Я разложил:

- `tf-playwright-stealth` — модернизированный форк
  `playwright-stealth`, нативный Python, ставится через uv,
  применяется per-page через `stealth_async(page)`. Закрывает
  основные CDP-маркеры. Для HH достаточно.
- `rebrowser-patches` — патчит сам Playwright runtime, маскирует
  `Runtime.enable` leak. Но это npm-пакет, для Python нативного нет.
  Овеr-engineering для HH.

Владелец выбрал `tf-playwright-stealth` + отдельный CLI
`hhack-browser` с подкомандами `login` / `fingerprint`.

## Что решили

- Зафиксировано как [D-014](decisions.md#d-014--2026-05-26--tf-playwright-stealth-for-cdp-fingerprint-masking).
- `pyproject.toml`: добавлена зависимость
  `tf-playwright-stealth>=1.2.0`, новый console-script
  `hhack-browser = "hhack.tools.browser:main"`.
- `src/hhack/integrations/browser/session.py` — `open_persistent_context`
  как `@asynccontextmanager`, открывает Chromium против
  `BROWSER_PROFILE_DIR`, применяет stealth ко всем существующим и
  новым страницам через `context.on("page", ...)`.
- `src/hhack/tools/browser.py` — CLI с подкомандами `login` (открыть
  hh.ru и ждать закрытия окна) и `fingerprint` (открыть
  bot.sannysoft.com, снять full-page скриншот в `./artifacts/`).
- `Settings` расширен: `BROWSER_USER_AGENT`, `BROWSER_LOCALE`,
  `BROWSER_TIMEZONE`, `BROWSER_VIEWPORT_WIDTH/HEIGHT`. Опциональные —
  если пусто, Playwright дефолты. Нужны чтобы автоматизированный
  контекст совпадал с реальным браузером оператора.
- `.env.example` + `README.md` обновлены под новые ключи и новый CLI.
- `.gitignore`: добавлен `artifacts/` (там лежат скриншоты с
  фингерпринт-данными).

## Техдолг Phase 0, прибранный попутно

- Включил `plugins = ["pydantic.mypy"]` в `[tool.mypy]` —
  без этого pre-commit падал на `Settings()` (`Missing named
  argument` для всех required полей). На main pre-commit с Phase 0
  не проходил, я обнаружил это запуском хуков на новых файлах.
- В `Settings.model_config` добавил `extra="ignore"` — без этого
  pydantic-settings ронял запуск, если в `os.environ` лежали лишние
  ключи (у меня в системе был ANTHROPIC_MODEL). Это блокирующая
  проблема для любого оператора с засорённым shell-окружением.
- Сделал `anthropic_api_key`, `database_url`, `resume_a_path`,
  `resume_b_path` опциональными (`str | None = None`). Phase 1
  поднимает только браузер — ни Anthropic, ни Postgres, ни резюме ему
  ещё не нужны. До этого фикса первый же запуск `hhack-browser` падал
  на required-полях, которых у оператора физически ещё нет. Воркеры
  Phase 2+ должны явно проверять наличие соответствующих полей в
  момент использования.

Все три фикса вошли как побочный эффект Phase 1 — они мешали
проверить работоспособность нового кода.

## Smoke-тесты

- `uv run pre-commit run --files <новые файлы>` — все четыре хука
  (ruff, ruff-format, mypy, gitleaks) зелёные.
- `uv run hhack-browser --help` — CLI поднимается, оба subparser'а
  видны.
- Реальный запуск браузера (`login`, `fingerprint`) делает
  оператор — мне не нужно открывать HH под его аккаунтом из этой
  сессии.

## Что осталось / следующие шаги

Открытый чек-лист Phase 1 в [roadmap](roadmap.md#phase-1--persistent-browser-session--in-progress):

- Оператор запускает `hhack-browser login`, логинится руками в HH
  (включая капчу / SMS), закрывает окно. Повторный
  `hhack-browser login` не должен спрашивать креды → сессия выжила.
- Оператор запускает `hhack-browser fingerprint`, смотрит на
  bot.sannysoft.com глазами. Все ряды (WebDriver, Chrome,
  Permissions, WebGL, Plugins) должны быть зелёными. Скриншот
  останется в `artifacts/` для записи.
- Если что-то красное — заводим решение перед Phase 2 (см. новую
  запись в [open-questions.md](open-questions.md), блок Phase 2).

После этого можно стартовать Phase 2 (read-only main-feed discovery).
