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

---

## D-015 · 2026-05-26 · `jobs` table is one flat row per vacancy, lifecycle via `status` string

**Decision:** A single `jobs` table holds everything we know about a
vacancy across its lifetime — card-level fields, detail-page fields,
and lifecycle state in a `status` string column (`discovered`,
`detailed`, later `matched` / `skipped` / `applied` / `failed`). The
idempotency anchor is `hh_id` (BigInteger, `UNIQUE`). `first_seen_at`
is set on insert; `detail_fetched_at` is set when status flips to
`detailed`.

**Reasoning:** All fields are 1:1 with a vacancy, so splitting them
across tables would only add joins. Phase 5+ adds `applications` and
`match_results` as separate tables (one-to-many on `jobs`), but the
job itself stays as a single row. Status as a free-form string (not
an enum constraint) lets later phases add lifecycle values without a
migration just to widen the enum — values are validated at the
application layer.

**Alternative considered:** Separate `feed_cards` / `jobs_detailed`
tables. Rejected: no useful aggregation on either; the join would be
1:1 and 100 % populated for any non-trivial workflow.

---

## D-016 · 2026-05-26 · Feed parser anchors on `/vacancy/<id>` URLs, not on cards' `data-qa`

**Decision:** The personalized-feed parser
(`integrations/hh/feed.py`) finds vacancies by
`a[href*="/vacancy/"]` first, extracts `hh_id` from the URL, then
walks up to the nearest card container and reads `title` / `company`
/ `snippet` / `feed_resume_hint` via best-effort `data-qa` selectors
with fallbacks.

**Reasoning:** HH does rename `data-qa` attributes between deploys,
but they cannot change the `/vacancy/<id>` URL pattern without
breaking their own product. Anchoring on the URL gives us a hard
guarantee that we will always know *what* the vacancy is, even if
every per-field selector breaks at once — at worst we lose the
card-level fields and recover them from the detail page. Missing
per-field selectors degrade to `NULL` in the DB rather than throwing.

**Alternative considered:** Pick a specific `data-qa` attribute as
the card root and fail loudly if it changes. Rejected: a single
brittle anchor maximizes downtime when HH ships a refactor; the
URL-first strategy degrades gracefully.

---

## D-017 · 2026-05-26 · First-run diagnostics: feed.py dumps HTML + JSON to `./artifacts/`

**Decision:** `discover_new_cards` accepts an optional
`dump_dir: Path` and, when set, writes the full page HTML plus the
parsed cards as JSON to `./artifacts/feed-<timestamp>.{html,json}`.
The `hhack-feed scan` CLI passes `./artifacts/` by default; the
operator can pass `--no-dump` once selectors are validated.

**Reasoning:** Phase 2's main risk is that our `data-qa` selectors
do not match the live HH DOM. Without a side-by-side dump there is no
way to debug "the parser found 0 cards" remotely. The artifact files
are gitignored (already covered by the `artifacts/` line from
Phase 1) and identify the operator (their feed, their resume), so
they must stay local.

**Consequence:** First Phase 2 runs are diagnostic-friendly by
default. Once the parser is stable the operator runs with
`--no-dump` to avoid filling the disk.

---

## D-018 · 2026-05-26 · Pagination: scroll until known `hh_id` is seen, with hard ceiling

**Decision:** The feed worker scrolls the personalized feed and
re-parses on each cycle. It stops on whichever happens first:
(a) any newly-parsed card has an `hh_id` already in the `jobs`
table — incremental crawl; (b) `max_scrolls` cycles complete — hard
ceiling (default 10). The ceiling exists because a brand-new install
has zero rows in `jobs` and would otherwise scroll forever.

**Reasoning:** The owner's hypothesis going into Phase 2 was that
"scroll until we hit a known hh_id" is the right strategy. It uses
the DB as the natural pagination cursor: each subsequent run only
opens vacancy pages the bot has not already seen. The hard ceiling
covers the cold-start case and any catastrophic state where every
single card is new (e.g. HH wipes our session, the database, or the
feed is entirely fresh after a long quiet period).

**Alternative considered:** Fixed N scrolls per cycle regardless of
DB state. Rejected: either wastes detail fetches by re-walking the
same vacancies, or misses new jobs when the feed is long.

**Resolves:** the "Feed pagination strategy" open question from
`open-questions.md`.

**Superseded in part by [D-019](#d-019--2026-05-26--main-page-is-a-teaser-real-feed-lives-at-searchvacancyresumeid):**
the main page is a teaser, not the full feed. Scroll-until-known
still describes the policy on a list once we are on one — D-019
changes *which list* we scroll.

---

## D-019 · 2026-05-26 · Main page is a teaser; real feed lives at `/search/vacancy?resume=<id>`

**Decision:** The hh.ru main page is **not** the full personalized
feed — it shows ~5 recommendation cards followed by a "Посмотреть N
вакансий" button. That button is a normal `<a>` with
`data-qa="applicant-index-search-all-results-button"` and an `href`
pointing to `/search/vacancy?resume=<resume_id>&hhtmFromLabel=
rec_vacancy_show_all&hhtmFrom=main`. The full feed is HH's standard
search SERP with the operator's resume id as a query parameter and
ordinary `&page=N` pagination.

Phase 2 ships the teaser-only flow (the 5 cards visible on the main
page). Phase 2.1 will extend `discover_new_cards` to:

1. parse all `data-qa="applicant-index-search-all-results-button"`
   anchors on the main page to collect one URL per resume that HH
   is currently recommending against;
2. for each such URL, navigate to `&page=0`, harvest cards, advance
   to `&page=N+1` until either a known `hh_id` appears (D-018's
   stop condition) or `max_pages` is hit.

**Reasoning:** Discovered during the first live `hhack-feed scan` —
the teaser exhausts in 1–2 scrolls and yields only ~5 cards, so
`scroll-until-known` is a no-op past the first page. The "see all"
button URL exposes the resume id directly, which incidentally
closes one of our open questions on per-resume attribution.

**Consequence on D-016:** still valid — anchoring on
`a[href*="/vacancy/"]` works identically on the search SERP, since
that is where the cards live anyway. The card root selector chain
(`getElementById(hh_id)` →
`[class*="vacancy-card--"]` → `[data-qa="vacancy-serp__vacancy"]` →
`article`) was chosen specifically so the same parser works on both
the main-page teaser and the search SERP.

**Consequence on per-resume attribution:** the resume id is in the
URL we navigate to, not in the individual cards. Setting
`feed_resume_hint = "<resume_id>"` per card is straightforward once
Phase 2.1 lands. Note: at apply time HH's response form lets the
operator pick a resume regardless of which feed surfaced the
vacancy — so this hint is informational, not authoritative.

---

## D-020 · 2026-05-26 · Feed card root anchor — `getElementById(hh_id)` first

**Decision:** In `feed.py`'s harvest JS, the card root for any
given `<a href="…/vacancy/{id}">` is resolved via:

```
document.getElementById(String(id))
  || a.closest('[class*="vacancy-card--"]')
  || a.closest('[data-qa="vacancy-serp__vacancy"]')
  || a.closest('article')
  || a.parentElement
```

**Reasoning:** The first version of `feed.py` used
`a.closest('[data-qa*="serp"]')`. The title link itself carries
`data-qa="serp-item__title"`, so `closest` resolved to the `<a>`
and every subsequent `card.querySelector(...)` returned `null`.
This silently produced rows with `title` populated (via
`a.innerText` fallback) and everything else `NULL`.

HH wraps every feed card in `<div id="{hh_id}"
class="vacancy-card--<hash>">`. `getElementById` is the most
durable anchor — HH would have to change their entire feed
implementation to break it. The class-substring and `data-qa`
fallbacks cover the case where HH later moves to a wrapper without
an id (unlikely; their analytics rely on it).

**Resolves:** the bug observed in the first
`feed-20260526T162630Z.json` dump where `company` / `snippet` /
`feed_resume_hint` were all `null` despite the cards rendering
correctly in the browser.
