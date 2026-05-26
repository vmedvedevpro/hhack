"""Manual browser helpers.

Subcommands:

- ``login`` — open hh.ru in the persistent profile and wait until the
  operator closes the window. Lets the operator log in by hand (incl.
  captcha / SMS) so the session cookie persists for later worker runs.
- ``fingerprint`` — open a stealth-detection test page in the same
  profile so the operator can eyeball the result, and save a screenshot
  under ``./artifacts/`` for the record.
- ``dump-resumes`` — open the applicant-zone resumes index, find every
  ``/resume/<id>`` link, open each one, save HTML + screenshot under
  ``./artifacts/resumes-<ts>/``. One-shot dump for the parser work in
  Phase 3.1; the real ``sync-resumes`` lives in the feed worker.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import BrowserContext, Page

from hhack.config import settings
from hhack.integrations.browser.session import open_persistent_context
from hhack.integrations.hh.resume_page import (
    APPLICANT_RESUMES_URL,
    collect_resume_ids,
)
from hhack.logging import setup_logging

HH_HOME_URL = "https://hh.ru/"
FINGERPRINT_URL = "https://bot.sannysoft.com/"
ARTIFACTS_DIR = Path("artifacts")


async def _wait_until_closed(context: BrowserContext) -> None:
    closed = asyncio.Event()
    context.on("close", lambda _ctx: closed.set())
    await closed.wait()


async def _login() -> None:
    bound = logger.bind(component="browser", action="login")
    async with open_persistent_context(settings) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        bound.info("opening hh.ru — log in by hand, then close the window")
        await page.goto(HH_HOME_URL, wait_until="domcontentloaded")
        await _wait_until_closed(context)


async def _fingerprint() -> None:
    bound = logger.bind(component="browser", action="fingerprint")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    screenshot_path = ARTIFACTS_DIR / f"fingerprint-{stamp}.png"

    async with open_persistent_context(settings) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        bound.info("opening {url}", url=FINGERPRINT_URL)
        await page.goto(FINGERPRINT_URL, wait_until="networkidle")
        await asyncio.sleep(3)
        await page.screenshot(path=str(screenshot_path), full_page=True)
        bound.info("screenshot saved to {path}", path=str(screenshot_path))
        bound.info("inspect the page, then close the window to exit")
        await _wait_until_closed(context)


async def _dump_page(page: Page, out_dir: Path, label: str) -> None:
    html_path = out_dir / f"{label}.html"
    png_path = out_dir / f"{label}.png"
    html_path.write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(png_path), full_page=True)


async def _dump_resumes() -> None:
    bound = logger.bind(component="browser", action="dump-resumes")
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ARTIFACTS_DIR / f"resumes-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    async with open_persistent_context(settings) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        resume_ids = await collect_resume_ids(page)
        # Snapshot the index after collect_resume_ids has already navigated there.
        await asyncio.sleep(3)
        await _dump_page(page, out_dir, "index")
        bound.info("dumping {n} resume page(s)", n=len(resume_ids))

        for resume_id in resume_ids:
            url = f"https://hh.ru/resume/{resume_id}"
            bound.info("opening {url}", url=url)
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            await _dump_page(page, out_dir, f"resume-{resume_id}")

        manifest = {
            "captured_at": stamp,
            "applicant_resumes_url": APPLICANT_RESUMES_URL,
            "resume_ids": resume_ids,
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        bound.info("dump complete: {path}", path=str(out_dir))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hhack-browser", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("login", help="open hh.ru and wait for manual login")
    subparsers.add_parser("fingerprint", help="open bot.sannysoft.com and screenshot the result")
    subparsers.add_parser("dump-resumes", help="dump applicant-zone resume pages into ./artifacts/resumes-<ts>/")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    setup_logging(settings.log_level)

    if args.command == "login":
        asyncio.run(_login())
    elif args.command == "fingerprint":
        asyncio.run(_fingerprint())
    elif args.command == "dump-resumes":
        asyncio.run(_dump_resumes())
    else:  # argparse guarantees one of the above
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
