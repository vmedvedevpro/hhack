"""One-shot exporter for ``applications`` review.

Phase 4 wants the operator to read 50+ generated cover letters end-to-end
before any of them get sent. Output is markdown grouped by vacancy with
match rationale + draft body side-by-side so the operator can sanity-check
the connection between "why we matched" and "what we wrote."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import select

from hhack.config import Settings
from hhack.domain.application import Application as ApplicationRow
from hhack.domain.job import Job
from hhack.domain.match import MatchResult as MatchResultRow
from hhack.persistence.database import create_session_factory


@dataclass(slots=True)
class _LetterBlock:
    job: Job
    draft: ApplicationRow
    match: MatchResultRow | None


@dataclass(frozen=True, slots=True)
class LetterExportSummary:
    output_path: Path
    draft_count: int


async def export_letters_to_markdown(
    settings: Settings,
    *,
    output_path: Path,
    statuses: list[str] | None = None,
) -> LetterExportSummary:
    """Render every ``applications`` row alongside its job + best match into markdown."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set; cannot export letters.")

    factory = create_session_factory(settings.database_url)
    async with factory() as session:
        stmt = select(ApplicationRow).order_by(ApplicationRow.created_at.desc())
        if statuses:
            stmt = stmt.where(ApplicationRow.status.in_(statuses))
        drafts = list((await session.execute(stmt)).scalars().all())

        job_ids = {d.job_id for d in drafts}
        jobs_by_id: dict[int, Job] = {}
        matches_by_pair: dict[tuple[int, str], MatchResultRow] = {}
        if job_ids:
            jobs = (await session.execute(select(Job).where(Job.id.in_(job_ids)))).scalars().all()
            jobs_by_id = {j.id: j for j in jobs}

            match_rows = (
                (await session.execute(select(MatchResultRow).where(MatchResultRow.job_id.in_(job_ids))))
                .scalars()
                .all()
            )
            for m in match_rows:
                key = (m.job_id, m.resume_id)
                existing = matches_by_pair.get(key)
                if existing is None or m.score > existing.score:
                    matches_by_pair[key] = m

    blocks: list[_LetterBlock] = []
    for d in drafts:
        job = jobs_by_id.get(d.job_id)
        if job is None:
            continue
        match = matches_by_pair.get((d.job_id, d.resume_id))
        blocks.append(_LetterBlock(job=job, draft=d, match=match))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = _render(blocks)
    output_path.write_text(rendered, encoding="utf-8")

    summary = LetterExportSummary(output_path=output_path, draft_count=len(blocks))
    logger.bind(component="letter_export").info(
        "wrote {n} draft(s) → {path}", n=summary.draft_count, path=str(output_path)
    )
    return summary


def _render(blocks: list[_LetterBlock]) -> str:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    lines: list[str] = [
        "# Letter review",
        "",
        f"Exported: {now}",
        "",
        f"Showing {len(blocks)} cover letter draft(s).",
        "",
        "---",
        "",
    ]
    for block in blocks:
        lines.extend(_render_block(block))
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _render_block(block: _LetterBlock) -> list[str]:
    job = block.job
    d = block.draft
    lines: list[str] = [
        f"## hh_id={job.hh_id} — {job.title}" + (f" — {job.company}" if job.company else ""),
        "",
        job.url,
        "",
        f"**Resume:** {d.resume_id[:8]}..{d.resume_id[-6:]}  ",
        f"**Language:** {d.language}  ",
        f"**Status:** {d.status}  ",
        f"**Letter length:** {len(d.cover_letter)} chars  ",
    ]
    if block.match is not None:
        lines.append(f"**Match score:** {block.match.score:.3f}  ")
        lines.append("")
        lines.append(f"_Match rationale:_ {block.match.rationale}")
    lines.append("")
    lines.append("### Cover letter")
    lines.append("")
    lines.append("> " + d.cover_letter.replace("\n", "\n> "))
    lines.append("")
    lines.append(
        f"_model={d.model} · prompt_hash={d.prompt_hash[:12]}… · "
        f"created={d.created_at.isoformat(timespec='seconds')}_"
    )
    lines.append("")
    return lines


__all__ = ["LetterExportSummary", "export_letters_to_markdown"]
