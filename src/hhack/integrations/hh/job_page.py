"""Vacancy detail-page parser.

Opens a single ``https://hh.ru/vacancy/<id>`` URL and extracts whatever
structured fields we can pull out. Missing fields are returned as
``None`` and stored as ``NULL`` — the matcher (Phase 3) reads from
``full_text`` regardless of which structured fields landed.

Two extraction sources are combined, DOM first and ``application/ld+json``
JobPosting second:

* DOM selectors give the field exactly as the page renders it (salary
  pre-formatted with currency, ``innerText`` of the description without
  decoration). They are brittle — HH renames ``data-qa`` between deploys
  and the branded vacancy template strips most of them entirely.
* The JSON-LD ``JobPosting`` block is part of HH's SEO contract with
  Google Jobs and is therefore present on every vacancy template,
  branded or not. It carries ``datePosted`` (which has never had a stable
  DOM selector), ``jobLocation.address`` and the full description even
  when the DOM has been re-skinned. We use it as fallback wherever DOM
  came back empty.

``employment_type`` is the one field with no JSON-LD source — it stays
DOM-only.
"""

from __future__ import annotations

import html
import re
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

  const dom = {
    full_text: pickText([
      '[data-qa="vacancy-description"]',
      '[data-qa="vacancy-description-text"]',
      '[itemprop="description"]',
      '.vacancy-branded-user-content',
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
      '[data-qa="vacancy-address-with-map"]',
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
  };

  // SEO JobPosting. HH ships at most one per page; pick the first one
  // whose @type matches. Anything that fails to parse is treated as
  // absent.
  let jsonLd = null;
  const scripts = document.querySelectorAll('script[type="application/ld+json"]');
  for (const s of scripts) {
    const raw = (s.textContent || '').trim();
    if (!raw) continue;
    try {
      const parsed = JSON.parse(raw);
      const candidates = Array.isArray(parsed) ? parsed : [parsed];
      for (const c of candidates) {
        if (c && c['@type'] === 'JobPosting') {
          jsonLd = c;
          break;
        }
      }
      if (jsonLd) break;
    } catch (e) {
      // Ignore malformed blocks — there should be a valid one elsewhere.
    }
  }

  return { dom, json_ld: jsonLd };
}
"""


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _strip_html(value: str | None) -> str | None:
    """Cheap HTML-to-text: paragraph tags → blank line, list/br → newline."""
    if not value:
        return None
    text = re.sub(r"</(p|h\d|div|tr|ul|ol)\s*>", "\n\n", value, flags=re.I)
    text = re.sub(r"</(li)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _BLANK_LINES_RE.sub("\n\n", text).strip()
    return text or None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _json_ld_location(job_location: Any) -> str | None:
    """Pull a human-readable city out of schema.org ``jobLocation``.

    HH gives a single Place but the spec allows a list, so handle both.
    Prefer ``addressLocality``; fall back to ``addressRegion`` or
    ``addressCountry`` if locality is absent.
    """
    if job_location is None:
        return None
    candidates = job_location if isinstance(job_location, list) else [job_location]
    for place in candidates:
        if not isinstance(place, dict):
            continue
        address = place.get("address")
        if not isinstance(address, dict):
            continue
        for key in ("addressLocality", "addressRegion", "addressCountry"):
            value = address.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _json_ld_salary(base_salary: Any) -> str | None:
    """Format schema.org ``baseSalary`` into a short string.

    DOM selectors win when present, so this is only reached for branded
    vacancies that did publish a salary in their structured data. Keep
    it minimal: ``"<min>-<max> <currency>"`` or ``"<value> <currency>"``.
    """
    if not isinstance(base_salary, dict):
        return None
    currency = base_salary.get("currency") or ""
    value = base_salary.get("value")
    if isinstance(value, dict):
        single = value.get("value")
        lo = value.get("minValue")
        hi = value.get("maxValue")
        if isinstance(single, int | float):
            amount = f"{int(single)}"
        elif isinstance(lo, int | float) and isinstance(hi, int | float):
            amount = f"{int(lo)}-{int(hi)}"
        elif isinstance(lo, int | float):
            amount = f"≥{int(lo)}"
        elif isinstance(hi, int | float):
            amount = f"≤{int(hi)}"
        else:
            return None
    elif isinstance(value, int | float):
        amount = f"{int(value)}"
    else:
        return None
    return f"{amount} {currency}".strip() or None


def combine_extracted(raw: dict[str, Any], hh_id: int) -> JobDetails:
    """Merge a DOM/JSON-LD extraction payload into ``JobDetails``.

    DOM wins where it has a value; JSON-LD fills the blanks. Kept as a
    pure function so unit tests can exercise the merge without a browser.
    """
    dom_payload = raw.get("dom") if isinstance(raw.get("dom"), dict) else {}
    json_ld = raw.get("json_ld") if isinstance(raw.get("json_ld"), dict) else None
    dom = cast(dict[str, Any], dom_payload)

    full_text = dom.get("full_text") or (_strip_html(json_ld.get("description")) if json_ld else None)
    salary = dom.get("salary") or (_json_ld_salary(json_ld.get("baseSalary")) if json_ld else None)
    location = dom.get("location") or (_json_ld_location(json_ld.get("jobLocation")) if json_ld else None)
    employment_type = dom.get("employment_type")
    posted_at = _parse_iso_datetime(dom.get("posted_at_iso") or (json_ld.get("datePosted") if json_ld else None))

    return JobDetails(
        hh_id=hh_id,
        full_text=full_text,
        salary=salary,
        location=location,
        employment_type=employment_type,
        posted_at=posted_at,
    )


async def fetch_job_details(page: Page, hh_id: int) -> JobDetails:
    """Navigate to the vacancy URL in the given page and extract detail fields."""
    bound = logger.bind(component="job_page", hh_id=hh_id)
    url = vacancy_url(hh_id)
    bound.info("opening {url}", url=url)
    await page.goto(url, wait_until="domcontentloaded")

    raw = cast(dict[str, Any], await page.evaluate(_EXTRACT_JS))
    details = combine_extracted(raw, hh_id)
    bound.info(
        "extracted fields: full_text={ft} salary={s} location={l} employment={e} posted_at={p} json_ld={j}",
        ft=bool(details.full_text),
        s=bool(details.salary),
        l=bool(details.location),
        e=bool(details.employment_type),
        p=details.posted_at.isoformat() if details.posted_at else None,
        j=raw.get("json_ld") is not None,
    )
    return details


__all__ = [
    "combine_extracted",
    "fetch_job_details",
]
