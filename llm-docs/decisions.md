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

---

## D-021 · 2026-05-26 · Phase 2.1 drops the teaser; SERP is the only source

**Decision:** `discover_new_cards` no longer parses cards off the main
page itself. The main page is opened only to harvest every
`a[data-qa="applicant-index-search-all-results-button"]` (one per
resume HH is recommending against). For each such URL we then walk
`/search/vacancy?resume=<id>&...&page=N` from `page=0` upward,
re-using the same card-harvest JS the teaser used (anchored on
`a[href*="/vacancy/"]` with the card root resolved by
`getElementById(hh_id)` first — D-020 still applies). The SERP at
`&page=0` already contains the same cards as the teaser, so parsing
the main page twice would only produce duplicates.

Pagination is driven by direct URL navigation (`page.goto(url +
"&page=N")`), not by clicking a pagination control: deterministic,
robust against pagination-DOM refactors, and keeps the rest of HH's
query params (`resume`, `hhtmFromLabel=rec_vacancy_show_all`,
`hhtmFrom=main`) byte-identical to the URL HH built itself.

Stop conditions match D-018 — pagination ends on the first known
`hh_id` or after `max_pages` (default 10). The CLI flag was renamed
`--max-scrolls` → `--max-pages` to match the new unit.

**Reasoning:** D-019 already documented that the main page is a
teaser. Phase 2.1 turns that into code. Keeping the teaser parser as
a fallback was considered and rejected: SERP `&page=0` covers it, and
two parsing paths on the same page would either deduplicate
correctly (waste of code) or differ subtly and confuse debugging.

**Consequence on `feed_resume_hint`:** now populated unconditionally
from the source URL's `resume=<id>` for every card the SERP walk
produces. No card-DOM probing for a per-resume label (D-019 already
established the hint lives in the URL, not the card).

**Consequence on diagnostics (D-017):** the dump format changes
slightly. Per scan we now write one HTML per "page we want to eyeball"
(the main page, plus `page=0` of each resume's SERP) plus one
combined JSON of every card collected across all resumes. Filenames
gain a label suffix (`feed-<ts>-main.html`,
`feed-<ts>-serp-resume-<id>.html`).

---

## D-022 · 2026-05-26 · Detail-page extraction reads JSON-LD JobPosting first, DOM second

**Decision:** `integrations/hh/job_page.py` evaluates **both** sources
on every vacancy page: the DOM `data-qa` selectors we already had, and
the SEO `<script type="application/ld+json">` block whose `@type` is
`JobPosting`. A pure `combine_extracted(raw, hh_id)` function then
merges them: DOM wins where it has a value, JSON-LD fills the blanks.

Field-by-field source policy:

- `full_text`: DOM `[data-qa="vacancy-description"]` (also tries
  `[itemprop="description"]` and `.vacancy-branded-user-content` as
  branded fallbacks). If still empty, JSON-LD `description` with a
  cheap HTML-to-text strip.
- `salary`: DOM `[data-qa="vacancy-salary"]` (kept first because the
  rendered string already carries currency formatting). Fallback —
  `baseSalary` formatted as `"<min>-<max> <currency>"`.
- `location`: DOM raw-address selectors, then `vacancy-address-with-map`,
  then JSON-LD `jobLocation.address.addressLocality`.
- `employment_type`: DOM only (`common-employment-text` and friends).
  JSON-LD has no equivalent for HH's «Полная занятость» phrasing.
- `posted_at`: DOM `time[datetime]` first, then JSON-LD `datePosted`.

**Reasoning:** First production run showed two structural gaps in the
DOM-only approach. (1) Branded vacancies (those wrapped in
`<div class="tmpl_hh_content">`, e.g. hh.ru/vacancy/133397925) strip
most `data-qa` attributes the parser depends on — `vacancy-salary`,
`vacancy-view-raw-address`, `vacancy-view-creation-time`,
`vacancy-view-employment-mode` all absent. Only `vacancy-description`
survives. (2) Even on non-branded vacancies `posted_at` was extracted
0/11 times and `location` only 4/11 — HH simply does not ship the
selectors we were targeting.

The JSON-LD `JobPosting` block is part of HH's SEO contract with
Google Jobs and is present on every vacancy template, branded or not.
It carries `datePosted` (which has never had a stable DOM selector),
the description, and `jobLocation.address`. Layering JSON-LD under DOM
gives us cheap, durable coverage without giving up the better-formatted
DOM strings where they exist.

**Alternative considered:** Add more `data-qa` fallback selectors per
field. Rejected: per-field selector lists were already growing brittle
and would not help with the genuinely-missing posted_at on non-branded
pages. JSON-LD is one selector lookup that gives us five fields at
once.

**Consequence:** `combine_extracted` is unit-tested without a browser
(`tests/integrations/hh/test_job_page.py`). The feed worker also gets
a `try/except` around each detail fetch so one broken page no longer
aborts the scan and the remaining cards still go from `discovered` to
`detailed`.

---

## D-023 · 2026-05-26 · Match logic — plain markdown resumes, single score with breakdown, matcher inline in scan

**Decision:** Three coupled choices for Phase 3:

1. **Resume format** — plain markdown, one file per slot
   (`RESUME_A_PATH`, `RESUME_B_PATH`). No YAML frontmatter, no
   structured schema. The matcher passes the raw text into the prompt
   verbatim; the model is responsible for extracting whatever
   structure it needs.
2. **Score schema** — one `score` in `[0, 1]`, one short `rationale`
   (2-3 sentences), a per-dimension `breakdown`
   (`skills` / `seniority` / `location_comp`) and a free-form
   `red_flags: string[]`. `MATCH_THRESHOLD` (default 0.65) compares
   against `score` only. The breakdown and red_flags are stored in
   `match_results.payload` (JSONB) for manual review and prompt
   tuning — they are not load-bearing for status decisions.
3. **Run mode** — matcher runs **inline** inside `hhack-feed scan`,
   per-vacancy. Order per card: `open → details → match →
   matched/skipped`, then jitter sleep, then the next card. No
   batching.

**Reasoning:**

- *Format.* Markdown is what the operator already writes; structured
  YAML adds parsing complexity for no observable matcher win — the
  model reads narrative well. We keep the option to layer a YAML
  frontmatter on top later if a hard pre-filter becomes necessary,
  without breaking the current loader.
- *Single score.* Tuning multiple thresholds in parallel is harder
  than tuning one, and we have no evidence yet that any single
  dimension dominates skipping decisions. Per-dimension scores are
  still emitted (and persisted) so we can audit a failure case
  without re-calling the LLM, but they don't gate status. AND-rules
  are postponed to "if precision turns out to be poor."
- *Inline in scan.* HH's defenses key on cadence and behavioral
  fingerprint, not on LLM use. A separate batched matcher would
  produce a recognizable "scrape, then later open detail pages to
  evaluate" pattern. One human-paced thread —
  open vacancy → read it (LLM) → decide → close → small pause →
  next — looks like a person browsing the feed, which is exactly
  what HH expects of a logged-in user. The matcher also stays
  best-effort: a failed LLM call leaves the job in `detailed`, the
  next scan picks it back up via `list_processable`. Phase 4/5 will
  hang cover-letter + apply off the same inline loop.

**Plumbing consequences:**

- New table `match_results` with `UNIQUE (job_id, resume_id,
  prompt_hash)`. `prompt_hash = sha256(PROMPT_VERSION || model ||
  resume_id || resume.content)` — excludes the vacancy on purpose,
  so the idempotency anchor is "this prompt/resume already evaluated
  this job," not "this exact vacancy text was already evaluated."
  Bumping `PROMPT_VERSION` in `matching/prompts.py` after a rules
  edit invalidates the cache naturally — old rows survive for
  comparison, new rows appear on the next scan.
- `Job.status` lifecycle gains `matched` and `skipped`. `mark_matched`
  / `mark_skipped` are called only after every resume slot has
  either a fresh decision or a pre-existing one; partial runs stay
  in `detailed`.
- Prompt caching is on by default — system block 0 is
  `MATCH_RULES`, block 1 is the resume content, both with
  `cache_control={"type":"ephemeral"}`. The vacancy block goes in
  the user message uncached.

**Alternative considered:**

- *Structured YAML resumes.* Rejected as premature: we have no
  pre-filter to drive off the structured fields, and the matcher
  already handles markdown well. Easy to add later as optional
  frontmatter without changing the loader contract.
- *Per-dimension AND-rule on threshold.* Rejected for Phase 3
  because we cannot calibrate multiple thresholds without first
  having a working single-score baseline.
- *Separate `hhack-feed match` command.* Rejected because it splits
  the human-cadence pattern into a "scrape now, evaluate later"
  shape that's more distinguishable from real user behavior.
  `--no-match` on `scan` covers the "I want to crawl without
  burning API tokens" case without breaking the production flow.

---

## D-024 · 2026-05-26 · Resumes come from HH applicant zone, not hand-managed markdown

**Decision:** The matcher's resumes are populated by syncing from HH's
applicant zone instead of being maintained by the operator as local
markdown files. Mechanics:

- `hhack-feed sync-resumes` opens `https://hh.ru/applicant/resumes` in
  the persistent profile, collects every `a[href*="/resume/<id>"]`,
  navigates to each `/resume/<id>` and parses HH's
  `<template id="HH-Lux-InitialState">` JSON state — specifically
  `applicantResume.*` — into matcher-ready markdown. Output is written
  to `resumes/cache/<hh_resume_id>.md` (configurable via
  `RESUMES_CACHE_DIR`).
- `load_resumes` reads every `*.md` from that cache directory. The
  slot id stored in `match_results.resume_id` is the HH `resume_id`
  (the filename), which is byte-identical to what `feed.py` writes to
  `jobs.feed_resume_hint`.
- `match_results.resume_id` widens from `String(8)` to `String(64)`
  (migration `2_widen_resume_id.py`) to fit the 38-char hex.
- Only matcher-relevant fields survive into the markdown: title,
  desired salary, area, availability/relocation/business-trip flags,
  professional role, full experience (with company, position, dates,
  description), skills, education (level + universities + courses),
  languages with CEFR level. PII (firstName, lastName, contacts,
  photo, personal site, metro, residence district) is stripped.

**Reasoning:**

- *Single source of truth.* HH already builds the operator's
  personalized feed from these same resumes; matching against any
  other text would let the matcher drift from what HH itself is
  recommending. Auto-sync removes "did you update both your HH and
  your local markdown?" as a class of bug.
- *Natural routing key.* The HH `resume_id` already appears on every
  vacancy card in `feed_resume_hint`. Using it as the slot id in
  `match_results` makes "which resume HH used to surface this job"
  trivially joinable with "what score did the matcher give that
  resume" — useful for Phase 4 cover-letter selection.
- *No PII in cache by default.* Stripping name/contacts at sync time
  means the operator can copy a cache file into a bug report or
  diff against a coworker's resume without leaking personal data.
- *Stable extraction surface.* HH ships the entire applicant-zone
  resume payload inside `<template id="HH-Lux-InitialState">` as a
  single JSON blob (this is HH's own SSR contract). DOM `data-qa`
  attributes are scarce in the applicant-zone resume template — the
  HTML carries fewer than ten of them. The template route is both
  simpler and more durable than DOM scraping.

**Alternative considered:**

- *Hand-maintained markdown (the original Phase 3 design).* Rejected
  for the drift reason above, and because the operator already had
  to keep HH resumes up-to-date anyway — having a second copy adds
  work without adding value.
- *Top-level YAML frontmatter on top of synced markdown.* Postponed
  until a hard pre-filter (e.g. "skip vacancies that require
  on-site Moscow when relocation=no") actually proves necessary.
  The sync layer would add it cheaply if needed.
- *HH public API (`/resumes/mine`).* Rejected because it requires
  OAuth tokens that don't live in the operator's normal browser
  cookies, and would create a second auth path to maintain. The
  same persistent browser context already has the session.

**Consequence on Phase 3 spec:** `RESUME_A_PATH`/`RESUME_B_PATH` are
removed from `config.py` and `.env.example`. Replaced by
`RESUMES_CACHE_DIR` (defaulting to `./resumes/cache`). `resumes/`
gitignore exception narrows from `!resumes/example_*.md` to
`!resumes/README.md`; the example files are deleted.

---

## D-025 · 2026-05-26 · Matcher output via Anthropic tool use, not free-form JSON

**Decision:** The matcher asks the model to return its decision by
invoking a forced tool call (`score_match`) with a typed input schema,
instead of asking for a JSON string in plain text. ``AnthropicClient``
gains a `create_tool_call` method that returns the SDK-parsed
``input`` dict directly. ``PROMPT_VERSION`` bumps `match-v1` →
`match-v2` so any previously persisted decisions stay in
`match_results` for comparison while every new pair gets re-evaluated
against the new prompt.

**Reasoning:** First live `hhack-feed scan` against Sonnet 4.6 produced
exactly the failure mode the free-form path is famous for —
``json.decoder.JSONDecodeError: Expecting ',' delimiter`` on a
``rationale`` that contained an unescaped character. The job ended up
in `failed` state and Phase 3 lost a usable score for it. Tool use
shifts JSON validity from "model has to remember to escape" to "SDK
guarantees a parsed dict or raises before we ever see the body."
The schema also serves as a second mile of documentation for the
model — fields, types, ranges, and required-ness all live in one
place that's read by both the API and our validator.

**Alternatives considered:**

- *JSON repair library (e.g. `json-repair`).* Rejected — would fix
  the symptom (parse error) but not the cause (model produces
  malformed text), and would add a third-party dependency for one
  call site.
- *Switch to XML output.* Rejected as strictly worse than tool use:
  same brittleness around special characters, plus the SDK doesn't
  validate it.
- *Tighten the prompt with "return JSON only" reminders.* Rejected
  as superstition — Anthropic explicitly recommends tool use for
  structured output, and there's no rules edit that turns "almost
  always valid JSON" into "always valid JSON" the way the schema
  contract does.

**Plumbing consequences:**

- `MATCH_TOOL_SCHEMA` lives next to `MATCH_RULES` in
  `matching/prompts.py`. Rules text no longer describes the JSON
  shape — only the rubric and the instruction "verify result via tool
  score_match".
- `parse_match_response` is replaced by `validate_match_payload`
  (which only re-checks `score`/`rationale` and clamps to `[0, 1]`).
- `FakeAnthropicClient` gets `create_tool_call` + `fake_tool_call`
  helper. Both `create_message` and `create_tool_call` share the same
  canned-response stream so existing tests don't need to choose paths.

---

## D-026 · 2026-05-26 · Cover letter generation — prompts-as-code, tool use, inline-в-scan, best-score-resume

**Decision:** Phase 4 lays down the cover-letter pipeline with the
following shape:

1. **Source of truth for the prompt** — `LETTER_RULES`,
   `LETTER_TOOL_SCHEMA` and `BANNED_PHRASES` live as constants in
   `matching/letter_prompts.py` (mirroring `prompts.py` for the
   matcher). No template file on disk; no DB-managed prompt.
2. **Output via tool use** — same reason as D-025. `LetterWriter`
   forces a `submit_cover_letter` tool call returning
   `{body: string, language: "ru"|"en"}`. Body length, banned-phrase
   list, structure are all in the rules text; the tool schema only
   guarantees we get parsable input.
3. **Inline in `hhack-feed scan`** — after `mark_matched(job.id)` the
   worker generates a letter for the best-scoring resume and persists
   to `applications` (status `draft`). Same single-thread human cadence
   D-023 already established for matching. `--no-letter` opt-out.
4. **Best-scoring resume wins** — `MatchRepository.best_match(job_id)`
   returns the row with the highest `score`. The resume from the local
   cache with the matching `resume_id` is fed into the letter prompt.
   Single letter per `(job, prompt_hash)` — no per-resume drafts.
5. **Language detection is the model's job** — the prompt instructs
   "пиши на том же языке, что и вакансия", and Sonnet/Haiku handle
   this reliably. No separate detection step. Closes the Phase 5
   blocker question.

**Reasoning:**

- *Prompts-as-code* gives versioning, code review, and a clean bump
  path via `LETTER_VERSION` for idempotency. A separate file would
  spread the prompt across two storage layers without a real win.
- *Tool use* is now the default for any structured Anthropic call in
  this codebase. We learned that the hard way in D-025 — no reason to
  re-learn for letters where the body is multi-line prose (worst case
  for free-form JSON).
- *Inline-в-scan* keeps the visible HH cadence intact (open → details
  → match → letter → next). Letter generation does not touch HH, so
  the HH-pacer from `_make_hh_pacer` does **not** apply to it; LLM
  calls run back-to-back. A separate `draft-letters` command would
  add a second LLM-only pass that doesn't fit the "one human session"
  story we've kept consistent through Phases 2-3.
- *Best-scoring resume* is the simplest answer that uses information
  the matcher already produces. If we end up wanting multiple drafts
  per vacancy (e.g. operator review of both .NET and LLM letters for
  borderline scores), we'd add a second draft per resume by widening
  the uniqueness key — easy follow-up if needed.

**Plumbing consequences:**

- New table `applications` (`migration 3_applications.py`) with
  `UNIQUE (job_id, prompt_hash)`. Status defaults to `draft`; Phase 5
  will move rows to `pending` / `sent` / `failed` and stamp `sent_at`
  / `hh_response_id`.
- `match_results.best_match(job_id)` added to the repository protocol
  so the worker can fetch the winning row + rationale for the letter
  prompt without re-doing the score arithmetic.
- `bootstrap.py` gains `build_letter_writer` and
  `build_application_repository`. The Anthropic client is reused
  between matcher and letter writer (same `AsyncAnthropicClient`
  instance, different model — Sonnet for matcher, Haiku for letter as
  per `architecture.md`).
- Worker `_process_job` accepts optional `letter_writer` /
  `application_repo`. If either is `None` the letter step is skipped
  (the `--no-letter` CLI flag flips both off together). This keeps
  existing matcher tests untouched.
- `hhack-feed export-letters` writes a markdown review file under
  `artifacts/letter-review-<ts>.md` so the operator can read 50+
  drafts end-to-end before Phase 5 toggles `DRY_RUN=false`.

**Alternatives considered:**

- *Separate `hhack-feed draft-letters` command.* Rejected for the
  same reason matcher stays inline: two-pass flow is a recognizable
  bot pattern, single-pass mirrors a human reviewing the feed.
- *Per-resume drafts.* Rejected for Phase 4 — adds review burden
  before we have any operator feedback that two-letter-per-vacancy
  even matters. Trivial to enable later by widening the unique
  constraint to `(job_id, resume_id, prompt_hash)`.
- *Templates with explicit slot placeholders.* Rejected; the model
  composes better when given a description of intent + banned
  phrases than when forced to fill `[GREETING]` / `[BODY]` literals.

**Subsequent calibration (same day, post-ramp):**

- `LETTER_RULES` iterated v1 → v5 against the operator's real matched
  vacancies. Each version targeted concrete failure modes the operator
  flagged on the previous draft batch (no greeting, em dash, generic
  opening "Интересует вакансия X", "Интересует возможность Y", numeric
  N/5 self-rating dumps, "погрузиться" as self-praise). Final v5
  includes a `Reliable working pattern` calibration anchor + complete
  example body to nudge the model into the desired shape rather than
  just banning the failure modes.
- Letter writer instructions are now in English even though the output
  language stays mirrored from the vacancy (Russian in our corpus).
  Sonnet/Haiku follow long English rule lists noticeably better than
  the same content in Russian.
- **Default letter model switched to `claude-sonnet-4-6`** (was Haiku
  4.5 per the initial plan in `architecture.md`). Side-by-side on the
  same 10 vacancies with the same letter-v5 rules: Haiku violated 4
  rule families in 10 letters (em dash 4/10, "Интересует возможность"
  2/10, numeric N/5 dump 1/10, "погрузиться" 1/10); Sonnet was 0/10.
  Sonnet is ~10x more expensive per token, but at the configured 20
  letters/day cap the cost delta is negligible compared to the review
  burden Haiku violations would create. Operator can override via
  `ANTHROPIC_LETTER_MODEL` if they want to retest.
