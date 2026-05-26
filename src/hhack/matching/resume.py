"""Operator resumes loaded from the HH-sync cache.

Resumes are plain markdown, one file per HH resume id, materialized by
``hhack-feed sync-resumes``. The slot id is the filename without the
``.md`` suffix — i.e. the HH ``resume_id``, the same string that lands
in ``jobs.feed_resume_hint``. That alignment lets later phases route a
match to the resume HH itself recommended the vacancy for.

The matcher feeds the raw markdown into the prompt verbatim. No YAML
frontmatter, no structured schema (see D-023). PII has already been
stripped at sync time by ``integrations/hh/resume_page.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hhack.config import Settings

_DEFAULT_CACHE_DIR = Path("resumes/cache")
_MD_GLOB = "*.md"


@dataclass(frozen=True, slots=True)
class Resume:
    """One cached resume slot."""

    id: str
    path: Path
    content: str


def resumes_cache_dir(settings: Settings) -> Path:
    raw = settings.resumes_cache_dir or str(_DEFAULT_CACHE_DIR)
    return Path(raw).expanduser()


def load_resumes(settings: Settings) -> list[Resume]:
    """Read every cached resume, ordered by slot id for stability."""
    cache_dir = resumes_cache_dir(settings)
    if not cache_dir.is_dir():
        raise RuntimeError(
            f"Resume cache directory {cache_dir} does not exist. Run "
            f"`hhack-feed sync-resumes` first to populate it from HH."
        )
    paths = sorted(cache_dir.glob(_MD_GLOB))
    if not paths:
        raise RuntimeError(f"No resumes found in {cache_dir}. Run `hhack-feed sync-resumes` to fetch them.")
    out: list[Resume] = []
    for path in paths:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise RuntimeError(f"Resume cache file {path} is empty.")
        out.append(Resume(id=path.stem, path=path, content=content))
    return out


__all__ = ["Resume", "load_resumes", "resumes_cache_dir"]
