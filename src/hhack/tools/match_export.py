"""One-shot exporter for ``match_results`` review.

Produces a markdown report grouped by vacancy, sorted by best score
descending. Operator reads it top-down, sanity-checks rationale and
breakdown, calibrates ``MATCH_RULES`` / ``MATCH_THRESHOLD``.

Not part of the worker hot path — runs only when invoked via
``hhack-feed export-matches``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select

from hhack.config import Settings
from hhack.domain.job import Job
from hhack.domain.match import MatchResult as MatchResultRow
from hhack.persistence.database import create_session_factory


@dataclass(slots=True)
class _JobBlock:
    job: Job
    matches: list[MatchResultRow]

    @property
    def best_score(self) -> float | None:
        if not self.matches:
            return None
        return max(m.score for m in self.matches)


@dataclass(frozen=True, slots=True)
class ExportSummary:
    output_path: Path
    job_count: int
    match_count: int
    matched: int
    skipped: int


async def export_matches_to_markdown(
    settings: Settings,
    *,
    output_path: Path,
    statuses: list[str] | None = None,
    only_with_matches: bool = True,
) -> ExportSummary:
    """Render every job + match_results row into a markdown review file."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set; cannot export matches.")

    factory = create_session_factory(settings.database_url)
    async with factory() as session:
        job_stmt = select(Job).order_by(Job.first_seen_at.desc())
        if statuses:
            job_stmt = job_stmt.where(Job.status.in_(statuses))
        jobs = list((await session.execute(job_stmt)).scalars().all())

        match_stmt = select(MatchResultRow).order_by(MatchResultRow.created_at.asc())
        matches = list((await session.execute(match_stmt)).scalars().all())

    matches_by_job: dict[int, list[MatchResultRow]] = {}
    for m in matches:
        matches_by_job.setdefault(m.job_id, []).append(m)

    blocks: list[_JobBlock] = []
    for job in jobs:
        block = _JobBlock(job=job, matches=matches_by_job.get(job.id, []))
        if only_with_matches and not block.matches:
            continue
        blocks.append(block)

    # Top-N descending by best score so the operator's eye lands on
    # the highest-stakes decisions first.
    blocks.sort(key=lambda b: (b.best_score if b.best_score is not None else -1), reverse=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render(blocks, total_jobs=len(jobs), total_matches=len(matches))
    output_path.write_text(rendered, encoding="utf-8")

    summary = ExportSummary(
        output_path=output_path,
        job_count=len(blocks),
        match_count=sum(len(b.matches) for b in blocks),
        matched=sum(1 for b in blocks if b.job.status == "matched"),
        skipped=sum(1 for b in blocks if b.job.status == "skipped"),
    )
    logger.bind(component="match_export").info(
        "wrote {n} job block(s) ({m} matches) → {path}",
        n=summary.job_count,
        m=summary.match_count,
        path=str(output_path),
    )
    return summary


def _render(blocks: list[_JobBlock], *, total_jobs: int, total_matches: int) -> str:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    lines: list[str] = [
        "# Match review",
        "",
        f"Exported: {now}",
        "",
        (f"Showing {len(blocks)} job(s) with match results " f"(of {total_jobs} total · {total_matches} match rows)."),
        "",
    ]
    matched = sum(1 for b in blocks if b.job.status == "matched")
    skipped = sum(1 for b in blocks if b.job.status == "skipped")
    detailed = sum(1 for b in blocks if b.job.status == "detailed")
    lines.append(f"Status breakdown: matched={matched} · skipped={skipped} · detailed={detailed}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for block in blocks:
        lines.extend(_render_block(block))
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _render_block(block: _JobBlock) -> list[str]:
    job = block.job
    facts: list[tuple[str, str | None]] = [
        ("Статус", job.status),
        ("Best score", f"{block.best_score:.3f}" if block.best_score is not None else None),
        ("Зарплата", job.salary),
        ("Локация", job.location),
        ("Формат", job.employment_type),
        ("Опубликовано", job.posted_at.date().isoformat() if job.posted_at else None),
    ]
    lines: list[str] = [
        f"## hh_id={job.hh_id} — {job.title}" + (f" — {job.company}" if job.company else ""),
        "",
        job.url,
        "",
    ]
    for label, value in facts:
        if value:
            lines.append(f"**{label}:** {value}  ")
    lines.append("")

    for m in sorted(block.matches, key=lambda x: x.score, reverse=True):
        lines.extend(_render_match(m))
    return lines


def _render_match(m: MatchResultRow) -> list[str]:
    short_id = f"{m.resume_id[:8]}..{m.resume_id[-6:]}"
    lines: list[str] = [
        f"### Resume {short_id} → score **{m.score:.3f}**",
        "",
        f"**Rationale:** {m.rationale}",
        "",
    ]
    payload = m.payload or {}
    breakdown = payload.get("breakdown") if isinstance(payload, dict) else None
    if isinstance(breakdown, dict) and breakdown:
        lines.append("**Breakdown:**")
        for dim in ("skills", "seniority", "location_comp"):
            entry = breakdown.get(dim)
            if isinstance(entry, dict):
                score = entry.get("score")
                note = entry.get("note")
                score_str = f"{score:.2f}" if isinstance(score, int | float) else "?"
                note_str = note if isinstance(note, str) else ""
                lines.append(f"- {dim}: {score_str} — {note_str}")
        lines.append("")
    red_flags = payload.get("red_flags") if isinstance(payload, dict) else None
    if isinstance(red_flags, list) and red_flags:
        lines.append("**Red flags:** " + "; ".join(str(rf) for rf in red_flags))
        lines.append("")
    elif isinstance(red_flags, list):
        lines.append("**Red flags:** —")
        lines.append("")
    lines.append(
        f"_model={m.model} · prompt_hash={m.prompt_hash[:12]}… · created={m.created_at.isoformat(timespec='seconds')}_"
    )
    lines.append("")
    return lines


__all__: list[str] = ["ExportSummary", "export_matches_to_markdown"]


# Keep mypy happy with the unused-Any flag on payload accesses.
_ = Any
