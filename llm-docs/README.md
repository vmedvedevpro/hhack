# llm-docs

Working memory for the AI assistant collaborating on this project. The
assistant reads this directory at the start of each session to restore context
and writes back to it as decisions are made and work progresses.

The owner of the repository can edit any of these files by hand at any time —
this is shared scratch space, not assistant-only.

## Layout

- `context.md` — what we are building, for whom, and why.
- `architecture.md` — chosen stack and how components fit together. Updated
  when the design changes.
- `roadmap.md` — phased plan from "nothing" to "running bot". Tick off
  phases as they land; do not delete old ones, mark them done.
- `decisions.md` — lightweight ADRs. One entry per non-obvious choice with
  date, decision, and reasoning. New decisions appended at the bottom.
- `open-questions.md` — things still to be decided, with enough context that
  the next session can pick them up.
- `conventions.md` — repo, code, and doc conventions (naming, language,
  what must never be committed).
- `sessions/` — chronological log of working sessions. One file per session
  named `YYYY-MM-DD-<slug>.md`. Captures what was discussed, what was
  decided, and what was left for next time. Written in Russian (the
  working language of the diaglog with the owner); everything else in
  this directory is English.

## Rules for the assistant

1. At the start of a session, read `context.md`, `architecture.md`,
   `roadmap.md`, `open-questions.md`, and the most recent session log.
2. Update `decisions.md` whenever a non-trivial technical choice is made.
3. Update `roadmap.md` when a phase completes or scope changes.
4. Write a session log before ending a session that involved meaningful
   progress, decisions, or open threads.
5. Never put secrets, the owner's resume content, HH cookies, API keys,
   or any other sensitive material here. This directory is committed and
   the repo will be public. See `conventions.md` for the full list.
