"""Feed worker — Phase 2 read-only discovery pass.

``hhack-feed scan`` opens the persistent browser, scrolls the
personalized main-page feed, persists new cards, then opens each new
vacancy page (paced) and fills in the detail fields. Apply / cover
letter / chat behavior lives in later phases.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from pathlib import Path

from loguru import logger

from hhack.bootstrap import build_job_repository
from hhack.config import settings
from hhack.integrations.browser.session import open_persistent_context
from hhack.integrations.hh.feed import discover_new_cards
from hhack.integrations.hh.job_page import fetch_job_details
from hhack.logging import setup_logging

ARTIFACTS_DIR = Path("artifacts")


async def _scan(*, max_scrolls: int, max_details: int, dump: bool) -> None:
    bound = logger.bind(worker="feed")
    repo = build_job_repository(settings)
    dump_dir = ARTIFACTS_DIR if dump else None

    async with open_persistent_context(settings) as context:
        page = context.pages[0] if context.pages else await context.new_page()

        new_cards = await discover_new_cards(
            page,
            repo,
            max_scrolls=max_scrolls,
            dump_dir=dump_dir,
        )
        inserted = await repo.upsert_feed_cards(new_cards)
        bound.info("persisted {n} new feed cards", n=len(inserted))

        pending = await repo.list_pending_details(limit=max_details)
        bound.info("opening {n} vacancy pages (max_details={cap})", n=len(pending), cap=max_details)
        for i, job in enumerate(pending):
            if i > 0:
                pause = random.uniform(
                    settings.min_seconds_between_actions * 0.7,
                    settings.min_seconds_between_actions * 1.3,
                )
                bound.info("pause {p:.1f}s before next page", p=pause)
                await asyncio.sleep(pause)
            details = await fetch_job_details(page, job.hh_id)
            saved = await repo.save_details(details)
            if not saved:
                bound.warning("save_details affected 0 rows for hh_id={id}", id=job.hh_id)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hhack-feed", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    scan = sub.add_parser("scan", help="single discovery pass over the personalized feed")
    scan.add_argument(
        "--max-scrolls",
        type=int,
        default=10,
        help="maximum number of scroll cycles before giving up on finding a known job",
    )
    scan.add_argument(
        "--max-details",
        type=int,
        default=30,
        help="maximum number of vacancy pages to open in this scan",
    )
    scan.add_argument(
        "--no-dump",
        action="store_true",
        help="skip writing feed HTML+JSON diagnostics to ./artifacts/",
    )
    return parser


def main() -> None:
    setup_logging(settings.log_level)
    args = _build_parser().parse_args()
    if args.command == "scan":
        asyncio.run(
            _scan(
                max_scrolls=args.max_scrolls,
                max_details=args.max_details,
                dump=not args.no_dump,
            )
        )
        return
    logger.bind(worker="feed").info("no command given — try `hhack-feed scan --help`")


if __name__ == "__main__":
    main()
