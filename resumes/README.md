# Resumes

This directory holds the resume cache the matcher reads from. Contents are
operator-specific and `.gitignore`d — only this README ships in the repo.

## How it gets populated

Run `uv run hhack-feed sync-resumes`. It opens HH's applicant zone in your
persistent Chromium profile, finds every resume on your account, parses each
into matcher-ready markdown (no PII), and writes one file per resume to
`./resumes/cache/<hh_resume_id>.md`.

Re-running the command is idempotent: unchanged resumes are skipped, edits on
HH overwrite the local cache file.

The matcher loads every `*.md` under the cache directory. The filename (HH
`resume_id`) becomes the slot id stored in `match_results.resume_id`, which
also lines up with `jobs.feed_resume_hint` so later phases can route a match
to the resume HH itself recommended the vacancy for.

If you want the cache to live outside the repo, set `RESUMES_CACHE_DIR` in
`.env` to an absolute path.
