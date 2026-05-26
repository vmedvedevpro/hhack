"""Manual browser helpers for Phase 1.

Two subcommands:

- ``login`` — open hh.ru in the persistent profile and wait until the
  operator closes the window. Lets the operator log in by hand (incl.
  captcha / SMS) so the session cookie persists for later worker runs.
- ``fingerprint`` — open a stealth-detection test page in the same
  profile so the operator can eyeball the result, and save a screenshot
  under ``./artifacts/`` for the record.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import BrowserContext

from hhack.config import settings
from hhack.integrations.browser.session import open_persistent_context
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hhack-browser", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("login", help="open hh.ru and wait for manual login")
    subparsers.add_parser("fingerprint", help="open bot.sannysoft.com and screenshot the result")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    setup_logging(settings.log_level)

    if args.command == "login":
        asyncio.run(_login())
    elif args.command == "fingerprint":
        asyncio.run(_fingerprint())
    else:  # argparse guarantees one of the above
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
