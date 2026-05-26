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
from pathlib import Path
from typing import Any

from loguru import logger

from hhack.bootstrap import (
    build_anthropic_client,
    build_job_repository,
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
from hhack.matching.matcher import Matcher
from hhack.matching.resume import Resume, resumes_cache_dir
from hhack.persistence import JobRepositoryProtocol, MatchRepositoryProtocol

ARTIFACTS_DIR = Path("artifacts")


async def _process_job(
    job: Job,
    *,
    page: Any,
    job_repo: JobRepositoryProtocol,
    match_repo: MatchRepositoryProtocol | None,
    matcher: Matcher | None,
    resumes: list[Resume],
    threshold: float,
) -> None:
    bound = logger.bind(worker="feed", hh_id=job.hh_id, job_id=job.id)

    if job.status == "discovered":
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
    else:
        await job_repo.mark_skipped(job.id)
        bound.info("best score {b:.3f} < threshold {t:.2f} → skipped", b=best, t=threshold)


async def _scan(*, max_pages: int, max_details: int, dump: bool, no_match: bool) -> None:
    bound = logger.bind(worker="feed")
    job_repo = build_job_repository(settings)
    dump_dir = ARTIFACTS_DIR if dump else None

    matcher: Matcher | None = None
    match_repo: MatchRepositoryProtocol | None = None
    resumes: list[Resume] = []
    if not no_match:
        client = build_anthropic_client(settings)
        matcher = build_matcher(settings, client)
        match_repo = build_match_repository(settings)
        resumes = build_resumes(settings)
        bound.info("matcher ready: model={m} resumes={r}", m=matcher.model, r=[r.id for r in resumes])

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

        failed: list[int] = []
        for i, job in enumerate(pending):
            if i > 0:
                pause = random.uniform(
                    settings.min_seconds_between_actions * 0.7,
                    settings.min_seconds_between_actions * 1.3,
                )
                bound.info("pause {p:.1f}s before next job", p=pause)
                await asyncio.sleep(pause)
            try:
                await _process_job(
                    job,
                    page=page,
                    job_repo=job_repo,
                    match_repo=match_repo,
                    matcher=matcher,
                    resumes=resumes,
                    threshold=settings.match_threshold,
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
    sub.add_parser(
        "sync-resumes",
        help="pull every applicant-zone resume from HH and write it to the cache dir",
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
            )
        )
        return
    if args.command == "sync-resumes":
        asyncio.run(_sync_resumes())
        return
    logger.bind(worker="feed").info("no command given — try `hhack-feed --help`")


if __name__ == "__main__":
    main()
