# Architecture

Status: **draft, pre-implementation**. Update as code lands.

## Stack

Mostly mirrors the owner's `tech-pulse` project so this codebase feels
native to the same developer (D-010). Deltas: no pgvector, no
embeddings, no Telegram. Adds Playwright and stricter tooling
(D-011).

- **Language:** Python 3.11+. Async-only.
- **Package manager:** `uv` (`pyproject.toml` + `uv.lock`).
- **Browser automation:** Playwright with `chromium.launch_persistent_context`
  against a real (non-headless) Chrome user data directory. Stealth
  patches (`playwright-stealth` or `rebrowser-patches`) applied to reduce
  CDP fingerprint exposure.
- **LLM:** `anthropic.AsyncAnthropic` with prompt caching and the
  same overload-retry pattern used in `tech-pulse` (linear backoff on
  HTTP 529). Default models:
  - Sonnet 4.6 (`claude-sonnet-4-6`) for job matching and chat responses
    (reasoning quality matters).
  - Haiku 4.5 (`claude-haiku-4-5-20251001`) for cover letter generation
    (volume task, cheaper).
  - Prompt caching on the resume content, reused on every match call.
- **Storage:** PostgreSQL 16 (plain — no pgvector), provisioned via
  `docker-compose.yml` in the repo. SQLAlchemy 2.0 async + `asyncpg`.
  Alembic with async `env.py` and manual migration filenames
  (`0_initial.py`, `1_jobs.py`, …) per project conventions.
- **Configuration:** `pydantic-settings` reading from `.env`.
  Single `Settings` class in `config.py`. No separate `config.toml`.
- **Logging:** `loguru`, configured in `logging.py`. Contextual binds
  per scope (`logger.bind(worker="feed", job_id=...)`).
- **Dependency injection:** assembled in `bootstrap.py`. Repositories
  and clients are passed in via `Protocol` interfaces so tests can
  swap fakes.
- **Process manager:** Two long-running processes (see Components),
  exposed as console scripts in `pyproject.toml`:
  `hhack-feed = "hhack.workers.feed:main"` and
  `hhack-chat = "hhack.workers.chat:main"`. No systemd /
  supervisord assumed.

## Why this stack (high level)

HH has a stable, predictable DOM. CSS-selector-driven automation is more
reliable and orders of magnitude cheaper than visual / computer-use
approaches for this site. The LLM is reserved for the parts that
genuinely need judgement: ranking job fit, drafting prose, and replying
to free-form recruiter questions. Full reasoning recorded in
`decisions.md`.

## Components

### 1. `feed` worker

Long-running. Single browser context.

Source of jobs is the **HH main page personalized feed**, not a search
URL. HH builds this feed for the logged-in user from their resume(s),
so there are no filters to configure — every operator running this bot
gets their own relevant feed automatically. This is also nicer for the
open-source story: no shared search query to tune across users. See
D-008.

```
loop:
  open hh.ru main page
  scroll the personalized feed until we hit a known hh_id
  parse new cards -> jobs table
  for each new job:
    open job page, parse full description -> jobs table
    call Claude for match (resume A, resume B) -> match_results table
    if match score >= threshold:
      generate cover letter -> applications table (status=pending)
      submit application via Playwright -> applications table (status=sent)
  sleep with jitter
```

Rate caps (initial, tighten/relax based on observation):
- Max 1 application per 30–60 s (uniform jitter).
- Max 20–30 applications per calendar day.
- Random short idle pauses every 5–10 actions.
- No activity outside the operator's typical waking hours
  (configurable window).

### 2. `chat` worker

Long-running. Separate browser context to avoid contention with `feed`,
or reuses the same one with a mutex — TBD (see `open-questions.md`).

```
loop:
  open chat inbox
  for each thread with unread messages:
    parse new messages
    classify: human / bot / unclear
    if bot:
      build context (job text, matched resume, thread history)
      call Claude for reply -> chat_drafts table
      send reply via Playwright -> chat_messages table
    if human or unclear:
      mark for operator review, do not auto-reply
  sleep with jitter
```

First weeks: drafts only, operator approves manually. Once trusted,
flip a config flag to auto-send for the `bot` class.

### 3. Source layout

`src/` layout following `tech-pulse`:

```
src/hhack/
  __init__.py
  config.py              # pydantic-settings Settings class
  logging.py             # loguru setup
  bootstrap.py           # DI assembly: settings -> clients -> repos -> workers
  domain/                # SQLAlchemy models, plain dataclasses
  persistence/
    __init__.py
    session.py           # async_sessionmaker factory
    fakes.py             # (in tests/persistence/, not here)
    job_repository.py    # ProtocolBased; one repo per aggregate
    application_repository.py
    chat_repository.py
  integrations/
    anthropic_client.py  # AsyncAnthropic wrapper with retry
    browser/
      session.py         # launch_persistent_context, stealth patching
    hh/
      feed.py            # main-page feed parsing
      job_page.py        # job detail parsing
      apply.py           # application submission flow
      chat.py            # inbox + thread parsing, sending replies
  matching/
    prompts.py           # match prompt + cover-letter prompt + chat-reply prompt
    matcher.py           # call wrapper, returns scored decisions
  workers/
    feed.py              # async loop: discover -> match -> apply
    chat.py              # async loop: poll inbox -> draft/send replies

migrations/
  env.py                 # async Alembic env
  versions/
    0_initial.py
    ...

tests/
  unit/                  # per-module tests with fakes
  persistence/
    fakes.py             # FakeJobRepository, FakeApplicationRepository, ...
  e2e/                   # gated by pytest marker, hits real Postgres + browser
```

### 4. Database

Tables (sketch — finalize during phase 2):

- `jobs` — id, hh_id, url, title, company, posted_at, full_text,
  fetched_at, status (new / matched / skipped / applied).
- `match_results` — job_id, resume_id, score, rationale, model,
  prompt_hash, created_at.
- `applications` — job_id, resume_id, cover_letter, status
  (pending / sent / failed), sent_at, hh_response_id.
- `chat_threads` — id, hh_thread_id, job_id, last_seen_message_at.
- `chat_messages` — thread_id, hh_message_id, direction (in / out),
  author_kind (bot / human / us), body, created_at.
- `chat_drafts` — thread_id, body, status (pending / approved / sent /
  rejected), created_at.

### 5. Config & secrets

Single source of truth: `.env`, loaded by `pydantic-settings`. No
`config.toml`. Required keys (working list):

- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MATCH_MODEL`, `ANTHROPIC_LETTER_MODEL`,
  `ANTHROPIC_CHAT_MODEL` (defaults to the Sonnet/Haiku split above)
- `DATABASE_URL` (normalized to async driver in Settings)
- `BROWSER_PROFILE_DIR` (path to persistent Chrome profile)
- `RESUME_A_PATH`, `RESUME_B_PATH` (paths to markdown resumes)
- `MATCH_THRESHOLD` (float)
- `MAX_APPLICATIONS_PER_DAY`, `MIN_SECONDS_BETWEEN_ACTIONS`
- `ACTIVE_HOURS_WINDOW` (e.g. `"09:00-23:00"`, operator's local time)
- `DRY_RUN` (bool — start true)
- `LOG_LEVEL`

`.env.example` ships in the repo with every key documented, no
values. Browser profile dir, resume files, and `.env` itself are
gitignored. Repo ships `resumes/example_*.md` as templates.

## Anti-detection posture

See `decisions.md` (D-005) for the rationale. Summary:

- Persistent Chrome profile, not a fresh context per run.
- Stealth patches applied.
- Real screen, not headless.
- Human-paced timings (see rate caps above).
- Same machine, same network the operator normally uses.
- No retry storms: a failed action backs off long, does not retry fast.
- All HH-facing strings (User-Agent, accept-language, timezone) match
  the operator's real browser.

## What is explicitly NOT in the architecture

- No computer-use / vision-based navigation. Pure DOM. (See D-001.)
- No multi-account support. (See `context.md` constraints.)
- No hosted deployment story. Local only. (See D-004.)
- No third-party application services or proxies for HH submissions.
