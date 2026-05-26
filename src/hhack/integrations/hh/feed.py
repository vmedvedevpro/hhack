"""Main-page personalized feed parser.

Strategy: anchor on ``a[href*="/vacancy/"]`` links and walk up to the
nearest card container. HH frequently reshuffles ``data-qa`` attributes,
but the vacancy URL is the one piece they cannot change without breaking
their own product. Per-field selectors are best-effort with fallbacks —
missing fields are stored as ``NULL`` and the detail-page parser fills
in the rest.

Pagination: scroll the feed until we see an ``hh_id`` already in the DB
(incremental crawl) or until a configurable ceiling. See
``llm-docs/decisions.md`` D-018.
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

from hhack.integrations.hh.urls import HH_HOME_URL
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

    let hint = null;
    if (card) {
      const hintEl =
        card.querySelector('[data-qa*="recommendation"]') ||
        card.querySelector('[data-qa*="reason"]');
      if (hintEl && hintEl.innerText) hint = hintEl.innerText.trim() || null;
    }

    position += 1;
    out.push({
      hh_id: id,
      url: href.split('?')[0].split('#')[0],
      title: title,
      company: company,
      snippet: snippet,
      feed_resume_hint: hint,
      feed_position: position,
    });
  }
  return out;
}
"""


def _row_to_card(row: dict[str, Any]) -> FeedCard | None:
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
        feed_resume_hint=row.get("feed_resume_hint"),
        feed_position=row.get("feed_position"),
    )


async def harvest_cards(page: Page) -> list[FeedCard]:
    """Read everything currently in the DOM and return parsed cards."""
    raw = cast(list[dict[str, Any]], await page.evaluate(_HARVEST_JS))
    cards: list[FeedCard] = []
    for row in raw:
        card = _row_to_card(row)
        if card is not None:
            cards.append(card)
    return cards


async def _dump_diagnostics(page: Page, cards: Sequence[FeedCard], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    html_path = directory / f"feed-{stamp}.html"
    json_path = directory / f"feed-{stamp}.json"
    try:
        html_path.write_text(await page.content(), encoding="utf-8")
    except Exception as exc:
        logger.warning("could not dump feed HTML: {exc}", exc=exc)
    json_path.write_text(
        json.dumps([dataclasses.asdict(c) for c in cards], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.bind(component="feed").info("diagnostics saved: {h} {j}", h=str(html_path), j=str(json_path))


async def discover_new_cards(
    page: Page,
    repo: JobRepositoryProtocol,
    *,
    max_scrolls: int,
    scroll_pause_seconds: float = 1.5,
    dump_dir: Path | None = None,
) -> list[FeedCard]:
    """Scroll the personalized feed until a known hh_id appears or `max_scrolls` is hit.

    Returns only new cards (those whose hh_id was not already in the DB).
    Diagnostics (page HTML + parsed JSON) are written to ``dump_dir`` if
    provided, which is the recommended path during initial selector
    validation.
    """
    bound = logger.bind(component="feed")
    bound.info("navigating to {url}", url=HH_HOME_URL)
    await page.goto(HH_HOME_URL, wait_until="domcontentloaded")
    await asyncio.sleep(scroll_pause_seconds)

    collected: dict[int, FeedCard] = {}
    saw_known_hh_id = False

    for cycle in range(max_scrolls + 1):
        cards = await harvest_cards(page)
        bound.info("scroll cycle {n}: {count} cards in DOM", n=cycle, count=len(cards))

        new_cards = [c for c in cards if c.hh_id not in collected]
        for c in new_cards:
            collected[c.hh_id] = c

        known = await repo.filter_known([c.hh_id for c in new_cards])
        if known:
            bound.info("hit {n} known hh_ids — stopping scroll", n=len(known))
            saw_known_hh_id = True
            break

        if cycle == max_scrolls:
            bound.warning("max_scrolls={max_scrolls} reached without hitting a known job", max_scrolls=max_scrolls)
            break

        await page.evaluate("() => window.scrollBy(0, window.innerHeight * 0.9)")
        await asyncio.sleep(scroll_pause_seconds)

    known_set = await repo.filter_known(list(collected))
    new_only = [c for c in collected.values() if c.hh_id not in known_set]

    if dump_dir is not None:
        await _dump_diagnostics(page, list(collected.values()), dump_dir)

    bound.info(
        "feed scan finished: total_in_dom={total} new={new} hit_known={hit}",
        total=len(collected),
        new=len(new_only),
        hit=saw_known_hh_id,
    )
    return new_only
