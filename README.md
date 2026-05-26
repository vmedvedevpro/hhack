# hhack

Local-only browser-automation bot for HeadHunter (hh.ru). Scrolls the
personalized job feed, matches each posting against the operator's
resumes, applies with a generated cover letter, and replies to
recruiter-bot follow-ups in the HH chat.

**Status:** pre-implementation. See [`llm-docs/roadmap.md`](llm-docs/roadmap.md)
for the phased plan.

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) for package management
- Docker (for the local PostgreSQL container)
- Anthropic API key

## Installation

```bash
uv sync
```

Install the Playwright browser (one-time):

```bash
uv run playwright install chromium
```

Install pre-commit hooks (one-time, for contributors):

```bash
uv run pre-commit install
```

## Configuration

```bash
cp .env.example .env
```

Required fields by phase:

- **Phase 1 (browser only):** none of the env keys are strictly
  required — defaults work. Optionally set `BROWSER_USER_AGENT` /
  `BROWSER_LOCALE` / `BROWSER_TIMEZONE` to match the operator's real
  browser exactly.
- **Phase 2+ (writing jobs to DB):** `DATABASE_URL`.
- **Phase 3+ (LLM matching, cover letters):** `ANTHROPIC_API_KEY`,
  `RESUME_A_PATH`, `RESUME_B_PATH`.

| Variable                      | Description                                          | Default                                                          |
|-------------------------------|------------------------------------------------------|------------------------------------------------------------------|
| `ANTHROPIC_API_KEY`           | Anthropic API key (required from Phase 3)            |                                                                  |
| `ANTHROPIC_MATCH_MODEL`       | Model used for job ↔ resume matching                 | `claude-sonnet-4-6`                                              |
| `ANTHROPIC_LETTER_MODEL`      | Model used for cover-letter generation               | `claude-haiku-4-5-20251001`                                      |
| `ANTHROPIC_CHAT_MODEL`        | Model used for chat replies                          | `claude-sonnet-4-6`                                              |
| `DATABASE_URL`                | PostgreSQL connection URL                            | `postgresql+asyncpg://hhack:hhack@localhost:5432/hhack`          |
| `BROWSER_PROFILE_DIR`         | Persistent Chrome profile directory (gitignored)     | `./profile`                                                      |
| `BROWSER_USER_AGENT`          | User-Agent override; blank = Playwright default      |                                                                  |
| `BROWSER_LOCALE`              | Locale override (e.g. `ru-RU`)                       |                                                                  |
| `BROWSER_TIMEZONE`            | IANA timezone (e.g. `Europe/Moscow`)                 |                                                                  |
| `BROWSER_VIEWPORT_WIDTH`      | Initial viewport width in pixels                     | `1440`                                                           |
| `BROWSER_VIEWPORT_HEIGHT`     | Initial viewport height in pixels                    | `900`                                                            |
| `RESUME_A_PATH`               | Path to first resume (markdown)                      | `./resumes/resume_a.md`                                          |
| `RESUME_B_PATH`               | Path to second resume (markdown)                     | `./resumes/resume_b.md`                                          |
| `MATCH_THRESHOLD`             | Score above which we apply (0–1)                     | `0.65`                                                           |
| `MAX_APPLICATIONS_PER_DAY`    | Hard cap on daily applications                       | `20`                                                             |
| `MIN_SECONDS_BETWEEN_ACTIONS` | Minimum delay between user-facing actions (seconds)  | `30`                                                             |
| `ACTIVE_HOURS_WINDOW`         | Local-time window in which the bot may act           | `09:00-23:00`                                                    |
| `DRY_RUN`                     | If `true`, log actions but never click apply         | `true`                                                           |
| `LOG_LEVEL`                   | Logging level                                        | `INFO`                                                           |

## Running

Start PostgreSQL:

```bash
docker compose up -d
```

Apply migrations:

```bash
uv run alembic upgrade head
```

Log in to HH **once by hand** inside the persistent profile so the
session cookie is captured. The bot does not automate the login flow
itself: HH gates it with captcha and SMS, and one manual login is
enough because the profile is reused.

```bash
uv run hhack-browser login
```

A real (non-headless) Chromium window opens against `BROWSER_PROFILE_DIR`.
Log in, then close the window — the session persists in the profile
directory for later worker runs.

Verify the stealth patches with a fingerprint test page:

```bash
uv run hhack-browser fingerprint
```

This opens `bot.sannysoft.com` and saves a full-page screenshot under
`./artifacts/`. The `WebDriver`, `Chrome (New)`, and CDP rows should
read as a normal browser, not as automation.

Run the workers as two separate processes:

```bash
uv run hhack-feed
uv run hhack-chat
```

## Tests

```bash
uv run pytest
```

## Project documentation

Architectural decisions, roadmap, and session notes live in
[`llm-docs/`](llm-docs/).
