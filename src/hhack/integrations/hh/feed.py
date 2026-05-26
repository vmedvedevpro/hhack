"""Personalized-feed crawler — Phase 2.1 paginated SERP.

The hh.ru main page is a teaser: ~5 recommendation cards plus one
"Посмотреть N вакансий" button per resume HH is currently recommending
against. The button is a normal anchor pointing at
``/search/vacancy?resume=<id>&hhtmFromLabel=rec_vacancy_show_all&hhtmFrom=main``.
That URL is the actual personalized feed; pagination is ``&page=N``.

This module:

1. Opens the main page just to collect those buttons (one per resume).
2. For each button, walks ``&page=0, 1, 2, …`` on the SERP, harvests
   cards, and stops at the first ``hh_id`` already in the DB (D-018) or
   when the per-resume page cap is reached.
3. Tags every card with ``feed_resume_hint=<resume_id>`` from the URL
   it was scraped from.

Card-level fields are read via ``a[href*="/vacancy/"]`` anchored on the
card root resolved by ``getElementById(hh_id)`` first (D-020). Missing
``data-qa`` selectors degrade to NULL, the detail-page parser fills in
the rest.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from loguru import logger
from playwright.async_api import Page

from hhack.integrations.hh.urls import (
    HH_HOME_URL,
    extract_resume_id,
    search_url_with_page,
)
from hhack.persistence.job_repository import FeedCard, JobRepositoryProtocol

_HARVEST_JS = """
() => {
  const out = [];
  const seen = new Set();
  let position = 0;
  const anchors = document.querySelectorAll('a[href*="/vacancy/"]');
  for (const a of anchors) {
    const href = a.href || '';
    const m = href.match(/\\/vacancy\\/(\\d+)/);
    if (!m) continue;
    const id = parseInt(m[1], 10);
    if (!Number.isFinite(id) || seen.has(id)) continue;
    seen.add(id);

    // The title link itself carries data-qa="serp-item__title", so a
    // naive closest('[data-qa*="serp"]') would resolve to the <a> and
    // scope all per-field lookups to nothing. Anchor on the card root
    // instead — HH wraps every feed item in <div id="{hh_id}"
    // class="vacancy-card--…">, and the next ancestor with a stable
    // data-qa is [data-qa="vacancy-serp__vacancy"].
    const card =
      document.getElementById(String(id)) ||
      a.closest('[class*="vacancy-card--"]') ||
      a.closest('[data-qa="vacancy-serp__vacancy"]') ||
      a.closest('article') ||
      a.parentElement;

    const pickText = (selectors) => {
      if (!card) return null;
      for (const sel of selectors) {
        const el = card.querySelector(sel);
        if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
      }
      return null;
    };

    const title =
      pickText([
        '[data-qa="serp-item__title"]',
        '[data-qa="vacancy-serp__vacancy-title"]',
      ]) || (a.innerText || '').trim() || null;

    const company = pickText([
      '[data-qa="vacancy-serp__vacancy-employer"]',
      '[data-qa="vacancy-serp__vacancy-employer-text"]',
      '[data-qa="vacancy-employer-text"]',
    ]);

    const snippet = pickText([
      '[data-qa="vacancy-serp__vacancy_snippet_responsibility"]',
      '[data-qa="vacancy-serp__vacancy_snippet_requirement"]',
      '[data-qa^="vacancy-serp__vacancy_snippet"]',
    ]);

    position += 1;
    out.push({
      hh_id: id,
      url: href.split('?')[0].split('#')[0],
      title: title,
      company: company,
      snippet: snippet,
      feed_position: position,
    });
  }
  return out;
}
"""

_SEARCH_BUTTONS_JS = """
() => {
  const out = [];
  const seen = new Set();
  const anchors = document.querySelectorAll(
    'a[data-qa="applicant-index-search-all-results-button"]'
  );
  for (const a of anchors) {
    const href = a.href || '';
    if (!href || seen.has(href)) continue;
    seen.add(href);
    out.push(href);
  }
  return out;
}
"""


def _row_to_card(row: dict[str, Any], *, resume_id: str | None) -> FeedCard | None:
    hh_id = row.get("hh_id")
    title = row.get("title")
    url = row.get("url")
    if not isinstance(hh_id, int) or not isinstance(url, str) or not isinstance(title, str):
        return None
    return FeedCard(
        hh_id=hh_id,
        url=url,
        title=title,
        company=row.get("company"),
        snippet=row.get("snippet"),
        feed_resume_hint=resume_id,
        feed_position=row.get("feed_position"),
    )


async def harvest_cards(page: Page, *, resume_id: str | None = None) -> list[FeedCard]:
    """Read every vacancy card currently in the DOM.

    ``resume_id`` is written to each card's ``feed_resume_hint`` so the
    SERP loop can attribute cards to the resume HH is recommending
    against.
    """
    raw = cast(list[dict[str, Any]], await page.evaluate(_HARVEST_JS))
    cards: list[FeedCard] = []
    for row in raw:
        card = _row_to_card(row, resume_id=resume_id)
        if card is not None:
            cards.append(card)
    return cards


async def collect_search_buttons(page: Page) -> list[str]:
    """Return ``href`` of every "Посмотреть N вакансий" anchor on the main page.

    HH renders one button per resume it currently recommends against. The
    list may be empty if HH has no recommendations to show (new account,
    no active resumes, etc.) — caller should warn and bail.
    """
    raw = cast(list[str], await page.evaluate(_SEARCH_BUTTONS_JS))
    return [href for href in raw if isinstance(href, str) and href]


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


async def _dump_page_html(page: Page, directory: Path, label: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"feed-{_timestamp()}-{label}.html"
    try:
        path.write_text(await page.content(), encoding="utf-8")
        logger.bind(component="feed").info("dumped HTML: {p}", p=str(path))
    except Exception as exc:
        logger.bind(component="feed").warning("could not dump page HTML: {exc}", exc=exc)


def _dump_cards_json(cards: Sequence[FeedCard], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"feed-{_timestamp()}.json"
    path.write_text(
        json.dumps([dataclasses.asdict(c) for c in cards], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.bind(component="feed").info("dumped JSON: {p}", p=str(path))


async def discover_new_cards(
    page: Page,
    repo: JobRepositoryProtocol,
    *,
    max_pages: int,
    page_pause_seconds: float = 1.5,
    dump_dir: Path | None = None,
) -> list[FeedCard]:
    """Walk every SERP linked from the main page until known ``hh_id`` or page cap.

    Returns only new cards (those whose ``hh_id`` was not already in the
    DB). When ``dump_dir`` is set, the main page's HTML and the first
    SERP page per resume are dumped for selector validation, plus one
    combined JSON of the harvest.
    """
    bound = logger.bind(component="feed")
    bound.info("navigating to {url}", url=HH_HOME_URL)
    await page.goto(HH_HOME_URL, wait_until="domcontentloaded")
    await asyncio.sleep(page_pause_seconds)

    if dump_dir is not None:
        await _dump_page_html(page, dump_dir, "main")

    button_urls = await collect_search_buttons(page)
    bound.info("found {n} 'Посмотреть все' button(s) on main page", n=len(button_urls))

    if not button_urls:
        bound.warning(
            "no 'applicant-index-search-all-results-button' anchors on main page — "
            "HH may not be recommending against any active resume, or the selector changed"
        )
        return []

    collected: dict[int, FeedCard] = {}
    global_position = 0

    for button_url in button_urls:
        resume_id = extract_resume_id(button_url)
        per_resume_bound = bound.bind(resume_id=resume_id or "unknown")
        per_resume_bound.info("crawling SERP for resume — base url {u}", u=button_url)

        saw_known = False
        for page_index in range(max_pages):
            target_url = search_url_with_page(button_url, page_index)
            per_resume_bound.info("page {n}: goto {u}", n=page_index, u=target_url)
            await page.goto(target_url, wait_until="domcontentloaded")
            await asyncio.sleep(page_pause_seconds)

            cards = await harvest_cards(page, resume_id=resume_id)
            per_resume_bound.info("page {n}: {count} cards in DOM", n=page_index, count=len(cards))

            if not cards:
                per_resume_bound.info("page {n} returned no cards — stopping pagination", n=page_index)
                break

            if dump_dir is not None and page_index == 0:
                label = f"serp-resume-{resume_id or 'unknown'}"
                await _dump_page_html(page, dump_dir, label)

            new_in_page: list[FeedCard] = []
            for c in cards:
                if c.hh_id in collected:
                    continue
                global_position += 1
                new_in_page.append(dataclasses.replace(c, feed_position=global_position))

            known = await repo.filter_known([c.hh_id for c in new_in_page])
            new_unknown = [c for c in new_in_page if c.hh_id not in known]
            for c in new_unknown:
                collected[c.hh_id] = c

            if known:
                per_resume_bound.info(
                    "hit {k} known hh_id(s) on page {n} — stopping pagination",
                    k=len(known),
                    n=page_index,
                )
                saw_known = True
                break

        if not saw_known:
            per_resume_bound.warning(
                "max_pages={max_pages} reached without hitting a known job",
                max_pages=max_pages,
            )

    if dump_dir is not None:
        _dump_cards_json(list(collected.values()), dump_dir)

    bound.info(
        "feed scan finished: resumes={r} new={n}",
        r=len(button_urls),
        n=len(collected),
    )
    return list(collected.values())
