"""Canonical HH URLs and helpers."""

from __future__ import annotations

import re

HH_HOME_URL = "https://hh.ru/"

_VACANCY_PATH_RE = re.compile(r"/vacancy/(\d+)")


def vacancy_url(hh_id: int) -> str:
    return f"https://hh.ru/vacancy/{hh_id}"


def extract_hh_id(url: str) -> int | None:
    match = _VACANCY_PATH_RE.search(url)
    if not match:
        return None
    return int(match.group(1))
