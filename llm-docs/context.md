# Project context

## What we are building

An automation bot that responds to job listings on HeadHunter (hh.ru) on
behalf of its operator. For each new job in the feed the bot:

1. Reads the full job description.
2. Matches it against one of the operator's resumes (the operator maintains
   two distinct resumes for different role tracks).
3. If the match is good enough, applies — attaching a cover letter that is
   generated from a template but lightly personalized to the job and
   company. Personalization stays within the job posting; the bot does not
   crawl external company sites.
4. Watches the HH chat for follow-up questions from recruiter bots and
   answers them well enough that the bot considers the chat handled.

## Why it exists

Manual application has stopped being viable on the current market: getting
volume requires hours of scrolling and copy-pasting, and a meaningful
fraction of those interactions are with automated recruiter bots anyway.
The goal is volume of credible applications, not artisanal hand-crafted
ones.

## Target user

For now: a single person, the repo owner, using their own HH account on
their own laptop. The project will be open-sourced, so it must be
straightforward for any developer to clone, configure with their own
credentials and resumes, and run locally. Concretely this means:

- No hard-coded paths, accounts, or resume content in the repo.
- All operator-specific data lives in env files / config that is
  gitignored, or in the database.
- Setup steps documented in the top-level README.
- PostgreSQL provisioned via docker-compose so a new user does not need
  a local install.

## Hard constraints

- **Runs locally only.** Never on a VPS, hosted runner, or shared
  infrastructure. HH fingerprints aggressively and a non-residential IP
  from a sudden new location is the fastest way to get banned. The
  bot must execute from the same machine and network the operator
  normally uses HH from.
- **One account per deployment.** No multi-account orchestration. If a
  user wants two accounts they run two copies on two machines.
- **Human-paced.** Throughput is capped to look plausible (see
  `architecture.md` for current numbers). The point is sustained
  applications over weeks, not a burst that gets the account banned on
  day one.

## Non-goals

- Scraping company sites for personalization.
- Building a UI beyond what is needed to operate the bot (CLI / local
  web dashboard is fine; no hosted SaaS).
- Supporting other job boards. HH only.
