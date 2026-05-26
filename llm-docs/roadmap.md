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

## Phase 1 — persistent browser session  ✓ done (2026-05-26)

- [x] Script that opens a persistent Chromium context against a
      configurable profile directory. `hhack-browser login` opens
      hh.ru against `BROWSER_PROFILE_DIR`, waits for the operator to
      close the window. See `src/hhack/tools/browser.py`.
- [x] Stealth library chosen: `tf-playwright-stealth` (D-014).
      Applied via `context.on("page", ...)` plus a pass over existing
      pages in `integrations/browser/session.py`.
- [x] `hhack-browser fingerprint` subcommand opens bot.sannysoft.com
      and saves a full-page screenshot to `./artifacts/`.
- [x] Operator ran `hhack-browser login`, logged in to HH manually,
      confirmed the session survives a second `hhack-browser login`
      (no re-login prompt). 2026-05-26.
- [x] Operator ran `hhack-browser fingerprint` on 2026-05-26, all
      bot.sannysoft.com rows looked clean.

## Phase 2 — read-only main-feed discovery (teaser only)  ✓ done (2026-05-26)

Source is the personalized feed on hh.ru's main page, not a search
URL. See D-008. The "full feed" via `/search/vacancy?resume=<id>` is
deferred to Phase 2.1 (D-019).

Code-side (landed 2026-05-26):

- [x] `jobs` table + initial migration (`migrations/versions/0_initial.py`),
      idempotency anchor `hh_id`. Schema in D-015.
- [x] `JobRepositoryProtocol` + `SQLAlchemyJobRepository` with
      Postgres `ON CONFLICT DO NOTHING` upsert. `FakeJobRepository`
      for unit tests.
- [x] Main-page feed parser (`integrations/hh/feed.py`): URL-anchored
      card harvester (D-016), card-root anchor via
      `getElementById(hh_id)` chain (D-020), scroll-until-known with
      configurable ceiling (D-018), optional diagnostic dump of
      HTML+JSON to `./artifacts/` for selector validation (D-017).
- [x] Vacancy detail parser (`integrations/hh/job_page.py`):
      full_text, salary, location, employment_type, posted_at.
- [x] `hhack-feed scan` worker — single discovery pass with paced
      detail fetches (`min_seconds_between_actions` ±30% jitter).

Validation (operator, 2026-05-26):

- [x] `docker compose up -d` and `uv run alembic upgrade head`
      applied 0_initial cleanly.
- [x] First diagnostic scan caught a card-root scoping bug
      (`closest('[data-qa*="serp"]')` matched the title link
      itself) — fixed; second scan filled `company` for all rows.
      `snippet` legitimately stays `NULL` (main feed has no snippet
      block) and is filled from the detail page's `full_text`.
- [x] Discovered that the main page only shows ~5 teaser cards
      followed by a "Посмотреть N вакансий" button. Full feed is
      paginated SERP at `/search/vacancy?resume=<id>&…`. See D-019.

## Phase 2.1 — paginated SERP crawl  [ ] planned

- [ ] On main-page load, parse every
      `a[data-qa="applicant-index-search-all-results-button"]` to
      collect one feed URL per active resume; extract `resume=<id>`
      from each URL and persist it as `feed_resume_hint` on every
      card harvested from that URL.
- [ ] Drive pagination by `&page=N` on the SERP URL, not by
      scrolling. Reuse D-018's stop conditions: stop on first known
      `hh_id` or after `max_pages` (rename `--max-scrolls` →
      `--max-pages` in the CLI).
- [ ] Low-cadence run for ≥1 week. Goal: selectors stay stable,
      HH does not flag the traffic, posted_at extraction holds.

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
