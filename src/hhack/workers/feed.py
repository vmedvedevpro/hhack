"""Feed worker — discovery + detail-fetch + match (Phase 3).

``hhack-feed scan`` opens the persistent browser, walks each personalized
SERP for new vacancy cards, then for every card that still needs work it
opens the vacancy page (if not yet detailed), runs the matcher against
every resume slot, and lands the job in ``matched`` or ``skipped`` based
on ``MATCH_THRESHOLD``. Applies and chat are still later phases.

The whole loop is one human-paced thread on purpose (see ``D-023``):
discover → details → match runs sequentially per vacancy, with a jitter
sleep between vacancies, so HH sees a normal browsing cadence rather
than a batched script. The matcher is best-effort — a failed LLM call
leaves the job in ``detailed`` and the next scan picks it back up.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from hhack.bootstrap import (
    build_anthropic_client,
    build_application_repository,
    build_job_repository,
    build_letter_writer,
    build_match_repository,
    build_matcher,
    build_resumes,
)
from hhack.config import settings
from hhack.domain.job import Job
from hhack.integrations.browser.session import open_persistent_context
from hhack.integrations.hh.feed import discover_new_cards
from hhack.integrations.hh.job_page import fetch_job_details
from hhack.integrations.hh.resume_page import (
    collect_resume_ids,
    fetch_resume_markdown,
)
from hhack.logging import setup_logging
from hhack.matching.letter_writer import LetterWriter
from hhack.matching.matcher import Matcher
from hhack.matching.resume import Resume, resumes_cache_dir
from hhack.persistence import (
    ApplicationRepositoryProtocol,
    JobRepositoryProtocol,
    MatchRepositoryProtocol,
)
from hhack.tools.letter_export import export_letters_to_markdown
from hhack.tools.match_export import export_matches_to_markdown

ARTIFACTS_DIR = Path("artifacts")


def _make_hh_pacer(bound: Any) -> Callable[[], Awaitable[None]]:
    """Build a pacer that sleeps before every HH browser action after the first.

    Jitters around ``settings.min_seconds_between_actions``. Anthropic / DB
    calls bypass it on purpose — only browser-side actions are visible to HH.
    """
    state = {"has_acted": False}

    async def _wait() -> None:
        if state["has_acted"]:
            pause = random.uniform(
                settings.min_seconds_between_actions * 0.7,
                settings.min_seconds_between_actions * 1.3,
            )
            bound.info("pause {p:.1f}s before next HH action", p=pause)
            await asyncio.sleep(pause)
        state["has_acted"] = True

    return _wait


async def _process_job(
    job: Job,
    *,
    page: Any,
    job_repo: JobRepositoryProtocol,
    match_repo: MatchRepositoryProtocol | None,
    matcher: Matcher | None,
    resumes: list[Resume],
    threshold: float,
    application_repo: ApplicationRepositoryProtocol | None = None,
    letter_writer: LetterWriter | None = None,
    before_hh_action: Callable[[], Awaitable[None]] | None = None,
) -> None:
    bound = logger.bind(worker="feed", hh_id=job.hh_id, job_id=job.id)

    if job.status == "discovered":
        if before_hh_action is not None:
            await before_hh_action()
        details = await fetch_job_details(page, job.hh_id)
        saved = await job_repo.save_details(details)
        if not saved:
            bound.warning("save_details affected 0 rows; skipping match")
            return
        # Mirror the update locally so the matcher sees the just-saved text.
        job.full_text = details.full_text
        job.salary = details.salary
        job.location = details.location
        job.employment_type = details.employment_type
        job.posted_at = details.posted_at
        job.status = "detailed"

    if matcher is None or match_repo is None:
        bound.info("matcher disabled (--no-match); leaving job in 'detailed'")
        return

    for resume in resumes:
        prompt_hash = matcher.prompt_hash(resume)
        if await match_repo.exists(job_id=job.id, resume_id=resume.id, prompt_hash=prompt_hash):
            bound.info("match already exists for resume={r}; skipping LLM call", r=resume.id)
            continue
        result = await matcher.match(job, resume)
        inserted = await match_repo.save(result)
        if not inserted:
            bound.warning("match_repo.save returned False for resume={r}", r=resume.id)

    best = await match_repo.best_score(job.id)
    if best is None:
        bound.warning("no match rows after processing; leaving job in 'detailed'")
        return

    if best >= threshold:
        await job_repo.mark_matched(job.id)
        bound.info("best score {b:.3f} >= threshold {t:.2f} → matched", b=best, t=threshold)
        if letter_writer is not None and application_repo is not None:
            await _draft_letter(
                job,
                match_repo=match_repo,
                application_repo=application_repo,
                letter_writer=letter_writer,
                resumes=resumes,
            )
    else:
        await job_repo.mark_skipped(job.id)
        bound.info("best score {b:.3f} < threshold {t:.2f} → skipped", b=best, t=threshold)


async def _draft_letter(
    job: Job,
    *,
    match_repo: MatchRepositoryProtocol,
    application_repo: ApplicationRepositoryProtocol,
    letter_writer: LetterWriter,
    resumes: list[Resume],
) -> None:
    bound = logger.bind(component="letter", hh_id=job.hh_id, job_id=job.id)
    best_match = await match_repo.best_match(job.id)
    if best_match is None:
        bound.warning("no match rows for job — cannot draft letter")
        return
    resume = next((r for r in resumes if r.id == best_match.resume_id), None)
    if resume is None:
        bound.warning(
            "best match resume_id={r} not in local cache — run sync-resumes",
            r=best_match.resume_id,
        )
        return
    prompt_hash = letter_writer.prompt_hash(resume)
    if await application_repo.exists(job_id=job.id, prompt_hash=prompt_hash):
        bound.info("letter draft already exists for this prompt; skipping")
        return
    draft = await letter_writer.write(job, resume, best_match)
    inserted = await application_repo.save(draft)
    if not inserted:
        bound.warning("application_repo.save returned False after write")
    else:
        bound.info("letter draft saved ({n} chars, lang={lang})", n=len(draft.cover_letter), lang=draft.language)


async def _scan(
    *,
    max_pages: int,
    max_details: int,
    dump: bool,
    no_match: bool,
    no_letter: bool,
) -> None:
    bound = logger.bind(worker="feed")
    job_repo = build_job_repository(settings)
    dump_dir = ARTIFACTS_DIR if dump else None

    matcher: Matcher | None = None
    match_repo: MatchRepositoryProtocol | None = None
    letter_writer: LetterWriter | None = None
    application_repo: ApplicationRepositoryProtocol | None = None
    resumes: list[Resume] = []
    if not no_match:
        client = build_anthropic_client(settings)
        matcher = build_matcher(settings, client)
        match_repo = build_match_repository(settings)
        resumes = build_resumes(settings)
        bound.info("matcher ready: model={m} resumes={r}", m=matcher.model, r=[r.id for r in resumes])
        if not no_letter:
            letter_writer = build_letter_writer(settings, client)
            application_repo = build_application_repository(settings)
            bound.info("letter writer ready: model={m}", m=letter_writer.model)

    async with open_persistent_context(settings) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        new_cards = await discover_new_cards(
            page,
            job_repo,
            max_pages=max_pages,
            dump_dir=dump_dir,
        )
        inserted = await job_repo.upsert_feed_cards(new_cards)
        bound.info("persisted {n} new feed cards", n=len(inserted))

        pending = await job_repo.list_processable(limit=max_details)
        bound.info("processing {n} jobs (cap={cap})", n=len(pending), cap=max_details)

        pacer = _make_hh_pacer(bound)
        failed: list[int] = []
        for job in pending:
            try:
                await _process_job(
                    job,
                    page=page,
                    job_repo=job_repo,
                    match_repo=match_repo,
                    matcher=matcher,
                    resumes=resumes,
                    threshold=settings.match_threshold,
                    application_repo=application_repo,
                    letter_writer=letter_writer,
                    before_hh_action=pacer,
                )
            except Exception:
                failed.append(job.hh_id)
                bound.opt(exception=True).error(
                    "process_job crashed for hh_id={id} — continuing",
                    id=job.hh_id,
                )
        if failed:
            bound.warning("{n} job(s) failed this scan: {ids}", n=len(failed), ids=failed)


async def _sync_resumes() -> None:
    bound = logger.bind(worker="feed", action="sync-resumes")
    cache_dir = resumes_cache_dir(settings)
    cache_dir.mkdir(parents=True, exist_ok=True)

    async with open_persistent_context(settings) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        resume_ids = await collect_resume_ids(page)
        if not resume_ids:
            bound.warning("no resumes found in applicant zone — nothing to sync")
            return

        added: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []
        for i, resume_id in enumerate(resume_ids):
            if i > 0:
                pause = random.uniform(
                    settings.min_seconds_between_actions * 0.7,
                    settings.min_seconds_between_actions * 1.3,
                )
                bound.info("pause {p:.1f}s before next resume", p=pause)
                await asyncio.sleep(pause)

            markdown = await fetch_resume_markdown(page, resume_id)
            target = cache_dir / f"{resume_id}.md"
            if not target.exists():
                target.write_text(markdown, encoding="utf-8")
                added.append(resume_id)
                bound.info("added {id}", id=resume_id)
            elif target.read_text(encoding="utf-8") != markdown:
                target.write_text(markdown, encoding="utf-8")
                updated.append(resume_id)
                bound.info("updated {id}", id=resume_id)
            else:
                unchanged.append(resume_id)
                bound.info("unchanged {id}", id=resume_id)

        bound.info(
            "sync complete: {a} added, {u} updated, {n} unchanged, cache={path}",
            a=len(added),
            u=len(updated),
            n=len(unchanged),
            path=str(cache_dir),
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hhack-feed", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan", help="single discovery + detail + match pass over the personalized feed")
    scan.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="maximum number of SERP pages per resume before giving up on finding a known job",
    )
    scan.add_argument(
        "--max-details",
        type=int,
        default=30,
        help="maximum number of vacancies to process (open + match) in this scan",
    )
    scan.add_argument(
        "--no-dump",
        action="store_true",
        help="skip writing feed HTML+JSON diagnostics to ./artifacts/",
    )
    scan.add_argument(
        "--no-match",
        action="store_true",
        help="discover and detail-fetch only; leave matching for a later run (no LLM calls)",
    )
    scan.add_argument(
        "--no-letter",
        action="store_true",
        help="skip cover-letter generation even when a job is matched (default: draft a letter)",
    )
    sub.add_parser(
        "sync-resumes",
        help="pull every applicant-zone resume from HH and write it to the cache dir",
    )
    export = sub.add_parser(
        "export-matches",
        help="dump match_results joined with jobs into a markdown review file",
    )
    export.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output path (default: ./artifacts/match-review-<ts>.md)",
    )
    export.add_argument(
        "--status",
        action="append",
        choices=("matched", "skipped", "detailed", "discovered"),
        help="filter by job status; repeat to include several. Default: matched + skipped.",
    )
    export.add_argument(
        "--all-jobs",
        action="store_true",
        help="include jobs without any match_results (default: skip them)",
    )
    letters = sub.add_parser(
        "export-letters",
        help="dump cover-letter drafts joined with jobs + match rationale into markdown",
    )
    letters.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output path (default: ./artifacts/letter-review-<ts>.md)",
    )
    letters.add_argument(
        "--status",
        action="append",
        choices=("draft", "pending", "sent", "failed"),
        help="filter by application status; repeat to include several. Default: all.",
    )
    return parser


def main() -> None:
    setup_logging(settings.log_level)
    args = _build_parser().parse_args()
    if args.command == "scan":
        asyncio.run(
            _scan(
                max_pages=args.max_pages,
                max_details=args.max_details,
                dump=not args.no_dump,
                no_match=args.no_match,
                no_letter=args.no_letter,
            )
        )
        return
    if args.command == "sync-resumes":
        asyncio.run(_sync_resumes())
        return
    if args.command == "export-matches":
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = args.output or ARTIFACTS_DIR / f"match-review-{stamp}.md"
        statuses = args.status if args.status else ["matched", "skipped"]
        asyncio.run(
            export_matches_to_markdown(
                settings,
                output_path=output,
                statuses=statuses,
                only_with_matches=not args.all_jobs,
            )
        )
        return
    if args.command == "export-letters":
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        output = args.output or ARTIFACTS_DIR / f"letter-review-{stamp}.md"
        asyncio.run(
            export_letters_to_markdown(
                settings,
                output_path=output,
                statuses=args.status,
            )
        )
        return
    logger.bind(worker="feed").info("no command given — try `hhack-feed --help`")


if __name__ == "__main__":
    main()
