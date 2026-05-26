# Conventions

## Repository

- Project will be public. Treat every commit as if it is already
  pushed to a public mirror.
- `main` is the working branch. Feature branches as needed, no
  enforced flow yet — revisit when there are contributors.

## Languages

- All code, code comments, commit messages, and user-facing
  documentation: English.
- `llm-docs/` (this directory): English, except `sessions/` logs,
  which are written in Russian — they are the working journal of
  Russian-language conversations with the owner and quoting verbatim
  is more useful than translating.

## Code

Conventions inherited from the owner's other Python project
(`tech-pulse`, see `decisions.md` D-010) plus a few deliberate
improvements (D-011).

- **Python 3.11+**, type hints required on public functions and on
  every repository / tool method.
- **Package manager: `uv`.** `pyproject.toml` + `uv.lock` are
  authoritative. New dependencies added with `uv add <pkg>`. No
  `requirements.txt`.
- **Async-only.** Playwright async API, SQLAlchemy async engine,
  `anthropic.AsyncAnthropic`. No sync helpers except the very top of
  process bootstrap.
- **One worker per process.** No threading inside a worker. Two
  workers (`feed`, `chat`) run as separate processes.
- **Format / lint:** `ruff format` and `ruff check`. **Type check:**
  `mypy --strict` on `src/`. All three run pre-commit.
- **Pre-commit secret scan:** `gitleaks` or equivalent in the
  pre-commit chain to catch `.env`, profile dirs, or resume content
  before they land.
- **Logging:** `loguru`, configured once in `logging.py`. Bind
  contextual fields per scope: `logger.bind(worker="feed",
  job_id=...)`. Text output to stderr; no JSON unless we ship to a
  log aggregator later.

## Configuration

- Secrets and tunables both in `.env`, loaded via `pydantic-settings`
  (single `Settings` class in `config.py`). No separate `config.toml`
  — `tech-pulse` ships only `.env` and it keeps onboarding shorter.
- `.env.example` ships with every key, no values, comments explaining
  each field.
- `DATABASE_URL` accepts `postgres://` and normalizes to
  `postgresql+asyncpg://` inside `Settings`, same trick as
  `tech-pulse`.
- No path or value referring to the owner specifically may be
  committed. If a default would identify the owner, the field has no
  default and is required in `.env`.

## Database

- **SQLAlchemy 2.0 async** with `asyncpg`. Declarative models via
  `Mapped[]` + `mapped_column()`.
- **Repositories take a session factory**, open transactions with
  `async with self._factory.begin() as session:` — no manual
  rollback, no shared module-level session.
- **Repository interfaces are `Protocol`s** (e.g.
  `JobRepositoryProtocol`). Concrete classes are wired in
  `bootstrap.py`; tests pass fakes from `tests/persistence/fakes.py`.
- Migrations via Alembic, one per schema change, never edit a merged
  migration. **Manual filenames** with a numeric prefix and slug:
  `0_initial.py`, `1_jobs.py`, `2_chat.py`. No `--autogenerate`
  reliance — generated as the start point, then reviewed and renamed.
- `migrations/env.py` runs async (`asyncio.run(run_migrations_online())`).
- All timestamps `TIMESTAMPTZ` in UTC. `server_default=func.now()` for
  `created_at` columns.
- Foreign keys named `<table>_id`. Tables and columns `snake_case`.

## Testing

- `pytest` + `pytest-asyncio` with `asyncio_mode = "auto"`. Test files
  default to `async def test_*`.
- **No real DB in unit tests.** Repositories are exercised through
  fakes that implement the same `Protocol`. Real DB only in
  end-to-end smoke tests, gated behind a marker.
- `pythonpath = ["src", "."]` in `pyproject.toml` so `from hhack...`
  works without install.
- Coverage tracked via `pytest --cov=hhack`. No hard floor yet; will
  set one after Phase 5.

## What must never be committed

- `.env` (any variant other than `.example`).
- Browser profile directories (typically `profile/`).
- Resume files containing actual personal data. Only `resumes/example_*`
  templates with placeholder content.
- HH session cookies, exported in any form.
- Screenshots / HTML dumps that include the operator's name, email,
  HH ID, or any application history.
- Anthropic API keys, logs of LLM calls that include the operator's
  resume content verbatim.

## What must never be committed

- `.env` (any variant other than `.example`).
- Browser profile directories (typically `profile/`).
- Resume files containing actual personal data. Only `resumes/example_*`
  templates with placeholder content.
- HH session cookies, exported in any form.
- Screenshots / HTML dumps that include the operator's name, email,
  HH ID, or any application history.
- Anthropic API keys, logs of LLM calls that include the operator's
  resume content verbatim.

If something sensitive lands in a commit, the recovery is rewriting
history with `git filter-repo` and rotating whatever was exposed —
not "fix in next commit". The `gitleaks` pre-commit hook catches the
obvious cases; the gitignore catches the rest. Both must stay in
place.

## Session logs

- File name: `sessions/YYYY-MM-DD-<slug>.md`.
- Front matter: date, participants ("owner", "assistant"), summary in
  one sentence.
- Sections: что обсудили · что решили · что осталось.
- Quote the owner verbatim when their phrasing carries the decision —
  paraphrase loses nuance.
- Cross-link to decisions (`D-NNN`) and roadmap phases.
