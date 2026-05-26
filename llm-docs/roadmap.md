# Roadmap

Phased plan. Each phase is small enough to validate end-to-end before the
next one starts. Do not skip ahead — earlier phases de-risk the later
ones, and the cost of getting banned partway through is a multi-week
account cooldown.

Status legend: `[ ]` planned · `[~]` in progress · `[x]` done.

## Phase 0 — repo skeleton  ✓ done (2026-05-26)

Mirrors `tech-pulse`'s layout and tooling (D-010) with the
improvements from D-011 (ruff/mypy/pre-commit, secret-scan hook).

- [x] `pyproject.toml`: project metadata, dependencies, console
      scripts (`hhack-feed`, `hhack-chat`), `[tool.pytest.ini_options]`
      with `asyncio_mode = "auto"` and `pythonpath = ["src", "."]`,
      `[tool.ruff]` and `[tool.mypy]` config.
- [x] `uv sync` produces `uv.lock`.
- [x] `docker-compose.yml`: `postgres:16` (plain — no pgvector),
      persistent named volume, port 5432, healthcheck.
- [x] `alembic.ini` + `migrations/env.py` set up for async, empty
      `versions/`.
- [x] `.env.example` with every key from `architecture.md` §5,
      commented, no values.
- [x] `src/hhack/` skeleton: `__init__.py`, `config.py` (Settings
      class), `logging.py` (loguru setup), `bootstrap.py` (empty
      assembly stub), empty `domain/`, `persistence/`, `integrations/`,
      `matching/`, `workers/` packages.
- [x] Console-script entrypoints: `hhack/workers/feed.py` and
      `hhack/workers/chat.py` each define a `main()` that does
      nothing yet but logs "started". Smoke-tested with a temporary
      `.env`: both `uv run hhack-feed` and `uv run hhack-chat`
      emit the expected loguru line and exit cleanly.
- [x] `.gitignore` updated: `profile/`, `resumes/*` except
      `resumes/example_*.md`, `*.code-workspace`. `.env` was already
      covered by the existing Python template.
- [x] `.pre-commit-config.yaml`: ruff (format + check), mypy,
      `gitleaks` for secret scanning.
- [x] Top-level `README.md` rewritten with setup steps for a fresh
      clone (mirrors the `tech-pulse` README shape: Requirements,
      Installation, Configuration, Running, Tests).

## Phase 1 — persistent browser session

- [ ] Script that opens a persistent Chromium context against a
      configurable profile directory.
- [ ] Operator logs in to HH by hand once. Verify session survives
      across script restarts (cookies, localStorage).
- [ ] Apply stealth patches; verify with a fingerprint test page
      (bot.sannysoft.com or similar) that obvious CDP markers are gone.
- [ ] No HH automation yet beyond opening the homepage.

## Phase 2 — read-only main-feed discovery

Source is the personalized feed on hh.ru's main page, not a search
URL. See D-008.

- [ ] Parse main-page feed cards: extract card-level fields (hh_id,
      title, company, snippet, url).
- [ ] Handle infinite scroll: scroll until we hit an `hh_id` already
      stored (incremental crawl) or until a configured ceiling.
- [ ] Observe whether the feed reflects both resumes or only one,
      and capture which (settles an open question — record findings
      in a decision entry).
- [ ] Open each job page, extract full description and structured
      fields (salary, location, employment type).
- [ ] Persist everything to `jobs` table. Idempotent on `hh_id`.
- [ ] Run for several days at a low cadence. Goal: confirm selectors
      are stable and HH does not flag the traffic.

## Phase 3 — match logic (no applications yet)

- [ ] Define resume schema and load operator resumes from configured
      paths.
- [ ] Match prompt with resume content cached. One call per
      (job, resume) pair, returns score + short rationale.
- [ ] Persist to `match_results`. Threshold lives in config.
- [ ] Operator reviews 200–500 decisions by hand. Tune prompt and
      threshold until precision feels right. No automated apply yet.

## Phase 4 — cover letter generation

- [ ] Cover letter template with explicit slots.
- [ ] Generation prompt with hard style/length constraints and
      anti-pattern examples (banned phrases).
- [ ] Persist drafts. Operator reviews 50+ end-to-end before any of
      them get sent.

## Phase 5 — application submission (gated)

- [ ] Playwright flow to submit application + attach cover letter on
      a job page.
- [ ] `dry_run` flag on by default. First sessions: dry_run=true logs
      the action plan instead of executing.
- [ ] Flip dry_run=false with daily cap of 10. Watch for any HH
      pushback (captchas, rate-limit pages, account warnings).
- [ ] Gradually raise cap toward the configured ceiling.

## Phase 6 — chat worker

- [ ] Inbox parser: list threads, detect unread.
- [ ] Per-thread fetch: messages, author detection.
- [ ] Reply generation with thread + job + matched resume in context.
- [ ] Draft-only mode first. Operator approves before send.
- [ ] Auto-send once draft quality is consistently good and only for
      messages classified as recruiter-bot.

## Phase 7 — open-source hardening

- [ ] Walk through README setup on a clean machine (or VM).
- [ ] Add CONTRIBUTING.md.
- [ ] Sanitize git history for any accidentally committed secrets.
- [ ] License headers if needed.
- [ ] Publish.
