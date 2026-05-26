"""Canonical HH URLs and helpers."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

HH_HOME_URL = "https://hh.ru/"

_VACANCY_PATH_RE = re.compile(r"/vacancy/(\d+)")


def vacancy_url(hh_id: int) -> str:
    return f"https://hh.ru/vacancy/{hh_id}"


def extract_hh_id(url: str) -> int | None:
    match = _VACANCY_PATH_RE.search(url)
    if not match:
        return None
    return int(match.group(1))


def extract_resume_id(url: str) -> str | None:
    """Pull ``resume=<id>`` out of a ``/search/vacancy?...`` URL.

    HH's "Посмотреть N вакансий" buttons carry the operator's resume id
    in the query string; we persist it as ``feed_resume_hint`` so later
    phases can tell which resume HH was recommending against.
    """
    for key, value in parse_qsl(urlparse(url).query, keep_blank_values=False):
        if key == "resume" and value:
            return value
    return None


def search_url_with_page(url: str, page_index: int) -> str:
    """Return ``url`` with ``page=<page_index>`` replacing any existing ``page`` param.

    HH SERP pagination is driven by ``&page=N`` (0-based); the operator's
    other query params (``resume``, ``hhtmFromLabel``, ``hhtmFrom``) stay
    intact, so the SERP keeps its provenance and HH's analytics keep
    matching what a human-clicked URL would carry.
    """
    parsed = urlparse(url)
    params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "page"]
    params.append(("page", str(page_index)))
    return urlunparse(parsed._replace(query=urlencode(params)))
