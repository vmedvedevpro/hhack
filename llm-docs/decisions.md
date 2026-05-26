# Decisions

Lightweight ADRs. New decisions appended at the bottom. Do not edit
historical entries — if a decision is reversed, add a new entry that
references and supersedes the old one.

Format: `D-NNN` · `YYYY-MM-DD` · short title · decision · reasoning ·
alternatives considered.

---

## D-001 · 2026-05-26 · DOM automation, not computer use

**Decision:** Drive HH through Playwright with CSS selectors, not
through a vision / computer-use model.

**Reasoning:** HH has a stable, single-vendor DOM with consistent
selectors. Vision-based control would cost 10–100× more per action,
be slower, and would not improve reliability for this site.
Anti-bot defenses on HH are about browser fingerprint and behavioral
patterns, not which abstraction is driving clicks — using vision does
not buy us evasion.

**Alternatives considered:** Anthropic Computer Use, Browser Use,
Stagehand. Rejected as over-engineering for a single, stable site.
Re-evaluate only if HH starts actively randomizing DOM to defeat
selectors (not currently the case).

---

## D-002 · 2026-05-26 · Hybrid — Playwright for navigation, Claude API for judgement

**Decision:** Code (Playwright) handles all deterministic work:
navigation, scrolling, parsing, clicking apply, sending chat messages.
LLM (Claude API) is called only for three jobs: (1) job ↔ resume
match scoring, (2) cover letter generation, (3) chat reply drafting.

**Reasoning:** Keeps the LLM call count predictable and the navigation
deterministic. LLM-driven navigation would be non-reproducible and
expensive, and provides no value when selectors work.

---

## D-003 · 2026-05-26 · Not Claude Skills

**Decision:** Do not implement the bot as Claude Skills inside a
Claude Code session.

**Reasoning:** Skills are prompt extensions for interactive Claude
Code sessions; they have no runtime independent of a session. This
bot must run continuously, poll chat asynchronously, and react to
state changes without an operator present. That requires a real
service, not a skill.

---

## D-004 · 2026-05-26 · Local execution only

**Decision:** The bot only runs on the operator's own machine, from
their normal network. No VPS, no cloud, no shared runner.

**Reasoning:** HH correlates IP, geolocation, ASN, and timezone with
account history. A residential IP that has been the operator's
HH-using IP for months looks normal; a sudden datacenter IP from a
new region is the fastest path to a ban. Local-only execution also
sidesteps any "is the bot hosted" liability questions when the
project is open-sourced.

**Consequence:** Setup docs target a developer laptop, not a server.
No systemd unit files in the open-source distribution; operators
start the workers manually or via their OS's user-session
mechanism.

---

## D-005 · 2026-05-26 · Persistent Chrome profile, real browser, stealth patches

**Decision:** Use `chromium.launch_persistent_context` against a
user-data directory the operator initializes by hand (manual login,
including any captcha / SMS). Run non-headless. Apply
`playwright-stealth` or equivalent CDP-fingerprint patches.

**Reasoning:** Headless Chrome and ephemeral contexts are detectable.
Automating the login flow itself is fragile (captcha, SMS) and
unnecessary — the operator only needs to log in once. Persisting the
profile gives us the same cookies, localStorage, and
device-fingerprint stability a real user has.

---

## D-006 · 2026-05-26 · PostgreSQL via docker-compose

**Decision:** Postgres 16, provisioned by a `docker-compose.yml`
shipped in the repo. Schema managed by Alembic.

**Reasoning:** Owner requested Postgres. docker-compose keeps onboarding
for new open-source users to one command instead of a local install
walkthrough. Alembic over hand-rolled migrations because schema will
churn during phases 2–6.

---

## D-007 · 2026-05-26 · Open-source from day one

**Decision:** Project is built with public release as a hard
requirement from the start: no operator-specific paths, accounts,
resume content, or HH credentials in the repo. All such data lives in
gitignored files referenced by config.

**Reasoning:** Owner intends to publish. Retrofitting "make it
generic" after secrets and personal data are already in commits is
painful and error-prone. Easier to enforce the boundary from commit
one.

---

## D-008 · 2026-05-26 · Main-page personalized feed as the job source

**Decision:** The `feed` worker reads jobs from the HH main-page
personalized feed (the recommendations HH shows a logged-in user
based on their resume), not from a search URL with operator-defined
filters.

**Reasoning:** Owner pointed out that HH already builds a relevance
feed for the logged-in user from their resume(s), and that feed is
the natural surface to scroll. Three concrete benefits:

1. No configuration: every operator running the open-source build
   gets their own personalized feed automatically; we do not ship or
   tune a default search query.
2. The relevance signal comes from HH's own model, which has more
   signal (account history, click patterns, prior applications) than
   anything we could replicate in a search filter.
3. Behavior on the main page matches a normal logged-in user — a
   scripted, filter-heavy search URL pattern would be a more obvious
   bot signature.

**Alternative considered:** Configurable search URL(s) per operator.
Rejected: requires per-user setup, ships worse defaults than HH's
own recommender, and produces traffic patterns less like a normal
user.

---

## D-009 · 2026-05-26 · One shared feed, LLM routes each job to a resume

**Decision:** The bot reads from a single personalized feed (per D-008)
and the matcher decides per-job which of the operator's resumes the
job is best evaluated against. No switching of "primary" resume in HH
settings, no two separate feeds.

**Reasoning:** Owner confirmed empirically: with two active resumes
(currently "LLM engineer" and "senior fullstack C#/React"), the HH
main-page feed already mixes jobs relevant to both. Branching the
architecture for per-resume feeds would add complexity that the actual
HH behavior makes unnecessary.

**Consequence:** Match call returns a score per resume; if any resume
clears the threshold, that resume + job pair is the one that gets a
cover letter and an application. The cover letter is generated from
the matched resume, not a blend.

**Alternative considered:** Toggle "primary" resume in HH settings
between scans to alternate feeds. Rejected: makes traffic patterns
unusual and adds a stateful HH-side step.

---

## D-010 · 2026-05-26 · Adopt the `tech-pulse` stack and layout

**Decision:** hhack reuses the conventions of the owner's other
Python project [`tech-pulse`](https://github.com/vmedvedevpro/tech-pulse):
`uv` for packaging, `pydantic-settings` reading `.env`, SQLAlchemy
2.0 async + asyncpg, Alembic with async `env.py` and manual
migration filenames, `loguru` for logging with contextual `.bind()`,
`anthropic.AsyncAnthropic` for the LLM, Protocol-based repository
interfaces wired in `bootstrap.py`, `src/<pkg>/` layout, pytest +
pytest-asyncio with in-memory fakes (no test DB).

**Reasoning:** The owner will be the primary maintainer; matching
their existing house style means less cognitive overhead and a
codebase that feels native. The stack also already covers everything
hhack needs (async I/O, Postgres, Anthropic SDK with prompt caching
and overload retry).

**Deltas from `tech-pulse`:** no pgvector, no embeddings, no
Telegram bot, no yt-dlp / PyGithub. Adds Playwright + stealth
patches (the whole point of the project).

---

## D-011 · 2026-05-26 · Improvements over `tech-pulse` baseline

**Decision:** hhack inherits `tech-pulse`'s stack but tightens
tooling: `ruff format` + `ruff check`, `mypy --strict` on `src/`, a
`pre-commit` chain that runs all three plus a secrets scanner
(`gitleaks` or equivalent).

**Reasoning:** `tech-pulse` has no linter/type-checker config — a
visible gap given the project otherwise leans into type hints and
async rigor. For an open-source repo with public contributors this
is non-negotiable; better to start with the bar high than retrofit
it. The secrets scanner is doubly important here because the repo
will be public and the configured paths (browser profile, resume
files) are sensitive.

**Consequence:** Phase 0 includes `.pre-commit-config.yaml` and the
ruff/mypy config in `pyproject.toml`. Contributing guide will
mention `pre-commit install` as a required step.

---

## D-012 · 2026-05-26 · Single `.env` for config, no `config.toml`

**Decision:** All configuration — secrets and non-secret tunables
alike — lives in `.env`, loaded by a single `pydantic-settings`
`Settings` class. No `config.toml` / `config.example.toml` split.

**Reasoning:** `tech-pulse` ships only `.env` and it keeps the setup
documented in one place. Two config sources doubles the chance a
user misses a value during setup. If we later need values that
genuinely don't belong in `.env` (e.g. structured prompt templates),
they go in dedicated files under `src/hhack/...`, not in a
top-level config TOML.

**Reverses:** the implicit assumption in earlier drafts of
`conventions.md` and `architecture.md` that there would be a
`config.toml`.

---

## D-013 · 2026-05-26 · Browser profile lives at `./profile/` inside the repo (gitignored)

**Decision:** The persistent Chromium user-data directory is at
`./profile/` at the repo root. The path is in `.gitignore`. Default
value of `BROWSER_PROFILE_DIR` in `.env.example` is `./profile/`.

**Reasoning:** Owner explicitly chose in-repo over external. Trade-offs
considered: in-repo is simpler for new open-source users (one less
path to configure, profile lives next to its repo) and matches the
"clone + uv sync + go" onboarding pattern; external (e.g.
`~/.config/hhack/profile/`) survives `git clean -xdf`. The
simplicity wins; the `.gitignore` entry makes the in-repo location
safe.

**Consequence:** `.gitignore` must include `profile/` from the very
first commit. Any operator running multiple checkouts gets multiple
profiles by default — they can point all checkouts at one shared
external path by overriding `BROWSER_PROFILE_DIR` in their `.env`.

---

## D-014 · 2026-05-26 · `tf-playwright-stealth` for CDP fingerprint masking

**Decision:** Apply stealth patches via the `tf-playwright-stealth`
package (the actively-maintained fork of the original
`playwright-stealth`). Patches are applied per page via
`stealth_async(page)` in two places:

- For every page already present when the persistent context opens.
- For every new page via `context.on("page", ...)`.

**Reasoning:** Native Python port, ships via `uv add`, covers the
main CDP markers (`navigator.webdriver`, `chrome.runtime`, vendor
strings, WebGL fingerprint, plugins, languages). Sufficient for HH,
which is not behind aggressive bot management like Cloudflare Turnstile.

**Alternative considered:** `rebrowser-patches`. Patches the Playwright
runtime itself and masks deeper CDP leaks (`Runtime.enable`), but it
is an npm package — no native Python distribution. Out of proportion
for HH; revisit only if HH starts probing for the leaks tf-stealth
doesn't cover.

**Consequence:** `pyproject.toml` pins
`tf-playwright-stealth>=1.2.0`. The mypy override for
`playwright_stealth.*` already exists from Phase 0. If HH detects
the bot in spite of this, the first move is to set
`BROWSER_USER_AGENT` / `BROWSER_LOCALE` / `BROWSER_TIMEZONE` to match
the operator's real browser exactly — most fingerprint detections
hit the UA/locale mismatch before any deep CDP probe.
