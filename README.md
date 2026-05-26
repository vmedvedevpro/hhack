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

| Variable                      | Description                                          | Default                                                          |
|-------------------------------|------------------------------------------------------|------------------------------------------------------------------|
| `ANTHROPIC_API_KEY`           | Anthropic API key (required)                         |                                                                  |
| `ANTHROPIC_MATCH_MODEL`       | Model used for job ↔ resume matching                 | `claude-sonnet-4-6`                                              |
| `ANTHROPIC_LETTER_MODEL`      | Model used for cover-letter generation               | `claude-haiku-4-5-20251001`                                      |
| `ANTHROPIC_CHAT_MODEL`        | Model used for chat replies                          | `claude-sonnet-4-6`                                              |
| `DATABASE_URL`                | PostgreSQL connection URL                            | `postgresql+asyncpg://hhack:hhack@localhost:5432/hhack`          |
| `BROWSER_PROFILE_DIR`         | Persistent Chrome profile directory (gitignored)     | `./profile`                                                      |
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
session cookie is captured (a helper command lands in Phase 1 — see
[`llm-docs/roadmap.md`](llm-docs/roadmap.md)). The bot does not
automate the login flow itself: HH gates it with captcha and SMS,
and one manual login is enough because the profile is reused.

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
