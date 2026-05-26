"""Vacancy detail-page parser.

Opens a single ``https://hh.ru/vacancy/<id>`` URL and extracts whatever
structured fields we can pull out. Missing fields are returned as
``None`` and stored as ``NULL`` — the matcher (Phase 3) reads from
``full_text`` regardless of which structured fields landed.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from loguru import logger
from playwright.async_api import Page

from hhack.integrations.hh.urls import vacancy_url
from hhack.persistence.job_repository import JobDetails

_EXTRACT_JS = """
() => {
  const pickText = (selectors) => {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
    }
    return null;
  };

  const pickAttr = (selectors, attr) => {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        const v = el.getAttribute(attr);
        if (v) return v;
      }
    }
    return null;
  };

  return {
    full_text: pickText([
      '[data-qa="vacancy-description"]',
      '[data-qa="vacancy-description-text"]',
    ]),
    salary: pickText([
      '[data-qa="vacancy-salary"]',
      '[data-qa="vacancy-salary-compensation-type-text"]',
      '[data-qa="vacancy-view-compensation-type"]',
    ]),
    location: pickText([
      '[data-qa="vacancy-view-raw-address"]',
      '[data-qa="vacancy-view-location"]',
      '[data-qa="vacancy-view-address"]',
    ]),
    employment_type: pickText([
      '[data-qa="vacancy-view-employment-mode"]',
      '[data-qa="common-employment-text"]',
      '[data-qa="vacancy-view-employment"]',
    ]),
    posted_at_iso: pickAttr(
      [
        '[data-qa="vacancy-view-creation-time"] time',
        'time[datetime]',
      ],
      'datetime',
    ),
    posted_at_text: pickText([
      '[data-qa="vacancy-view-creation-time"]',
    ]),
  };
}
"""


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def fetch_job_details(page: Page, hh_id: int) -> JobDetails:
    """Navigate to the vacancy URL in the given page and extract detail fields."""
    bound = logger.bind(component="job_page", hh_id=hh_id)
    url = vacancy_url(hh_id)
    bound.info("opening {url}", url=url)
    await page.goto(url, wait_until="domcontentloaded")

    raw = cast(dict[str, Any], await page.evaluate(_EXTRACT_JS))
    posted_at = _parse_iso_datetime(raw.get("posted_at_iso"))

    details = JobDetails(
        hh_id=hh_id,
        full_text=raw.get("full_text"),
        salary=raw.get("salary"),
        location=raw.get("location"),
        employment_type=raw.get("employment_type"),
        posted_at=posted_at,
    )
    bound.info(
        "extracted fields: full_text={ft} salary={s} location={l} employment={e} posted_at={p}",
        ft=bool(details.full_text),
        s=bool(details.salary),
        l=bool(details.location),
        e=bool(details.employment_type),
        p=details.posted_at.isoformat() if details.posted_at else None,
    )
    return details
