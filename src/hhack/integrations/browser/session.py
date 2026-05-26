"""Persistent Chromium browser session with stealth patches.

Anti-detection rationale: see `llm-docs/decisions.md` D-005.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright_stealth import stealth_async

from hhack.config import Settings


def _resolve_profile_dir(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


async def _apply_stealth(page: Page) -> None:
    try:
        await stealth_async(page)
    except Exception as exc:
        logger.warning("stealth patch failed on page {url}: {exc}", url=page.url, exc=exc)


def _on_new_page(page: Page) -> None:
    asyncio.get_event_loop().create_task(_apply_stealth(page))


@asynccontextmanager
async def open_persistent_context(settings: Settings) -> AsyncIterator[BrowserContext]:
    """Launch Chromium against the operator's persistent profile and yield the context.

    Stealth patches are applied to every page (existing and future) so the
    operator can navigate freely without the caller worrying about it.
    """
    profile_dir = _resolve_profile_dir(settings.browser_profile_dir)
    bound = logger.bind(component="browser", profile=str(profile_dir))
    bound.info("launching persistent context")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={
                "width": settings.browser_viewport_width,
                "height": settings.browser_viewport_height,
            },
            user_agent=settings.browser_user_agent,
            locale=settings.browser_locale,
            timezone_id=settings.browser_timezone,
        )
        context.on("page", _on_new_page)

        for page in context.pages:
            await _apply_stealth(page)

        try:
            yield context
        finally:
            bound.info("closing persistent context")
            await context.close()
