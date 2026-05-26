# Open questions

Things that need a decision before the relevant phase starts. Resolve
during a working session, then move the resolution into `decisions.md`
and delete the question from here.

## Blocking before Phase 2

- **Feed pagination strategy.** The main feed is scroll-based. Per
  cycle: scroll N pages and stop, or scroll until we hit jobs already
  in `jobs` (known `hh_id`)? Probably the latter, confirm against the
  live site.

## Blocking before Phase 3

- **Resume format.** Markdown? Structured YAML / JSON (sections,
  skills, experience entries)? Markdown is easier for the operator to
  maintain; structured is easier for the matcher to reason over. A
  middle ground: markdown with a YAML frontmatter for facts the
  matcher cares about (years_experience, primary_skills, locations,
  remote_ok).
- **Match threshold semantics.** Single 0–100 score, or
  per-dimension (skills, seniority, comp, location) with rule-based
  AND? Start with single score, revisit if precision is poor.

## Blocking before Phase 5

- **Cover letter language detection.** HH job postings can be Russian
  or English. The cover letter must match the posting's language. Add
  a language-detect step before generation, or pass the full posting
  and let the LLM mirror its language?
- **What counts as "applied successfully"?** HH application flow has
  multiple states (sent, viewed, in chat, rejected, archived). Which
  of those does `applications.status=sent` represent, and how do we
  detect each transition?

## Blocking before Phase 6

- **Browser contention.** One Chromium context shared by feed + chat
  workers with a mutex, or two separate persistent contexts? Two
  contexts mean two sessions and possibly two device fingerprints on
  the same account, which HH might flag as suspicious. One context
  with a mutex is safer but couples the workers' uptime.
- **Bot vs human classification.** Heuristic on message content
  (templated phrases, structured questionnaires, response time
  patterns), or LLM classifier per message? Heuristic is cheaper and
  reviewable; LLM is more flexible. Start with heuristic, fall back
  to LLM on ambiguous cases.
- **Sensitive answer policy.** Recruiter bots sometimes ask for
  salary expectations, citizenship, willingness to relocate.
  Hard-code answers in config, or let the LLM answer from resume +
  config preferences? Either way: never invent facts not present in
  config / resume.
