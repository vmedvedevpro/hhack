from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from hhack.matching.matcher import Matcher
from hhack.matching.resume import Resume
from hhack.persistence.job_repository import FeedCard, JobDetails
from hhack.workers import feed as feed_worker
from tests.integrations.fakes import FakeAnthropicClient, fake_tool_call
from tests.persistence.fakes import FakeJobRepository, FakeMatchRepository

RESUMES = [
    Resume(id="a", path=Path("/tmp/a.md"), content="resume A"),
    Resume(id="b", path=Path("/tmp/b.md"), content="resume B"),
]


def _card(hh_id: int = 1, *, position: int = 1) -> FeedCard:
    return FeedCard(
        hh_id=hh_id,
        url=f"https://hh.ru/vacancy/{hh_id}",
        title=f"Job {hh_id}",
        company="Acme",
        snippet="short",
        feed_resume_hint=None,
        feed_position=position,
    )


def _details(hh_id: int = 1) -> JobDetails:
    return JobDetails(
        hh_id=hh_id,
        full_text="Python, asyncio, postgres.",
        salary="200000 RUR",
        location="Москва",
        employment_type="Полная занятость",
        posted_at=datetime(2026, 5, 22, tzinfo=UTC),
    )


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, details: JobDetails) -> list[int]:
    """Replace ``fetch_job_details`` with a stub. Returns a list that records every call."""
    calls: list[int] = []

    async def _fake(page: object, hh_id: int) -> JobDetails:
        calls.append(hh_id)
        return details

    monkeypatch.setattr(feed_worker, "fetch_job_details", _fake)
    return calls


def _matcher(scores: dict[str, float]) -> tuple[Matcher, FakeAnthropicClient]:
    """Matcher whose returned score depends on which resume slot is in the system prompt."""

    def _respond(*, system: list[dict[str, object]], **_: object):
        slot = "a" if "resume A" in system[1]["text"] else "b"
        return fake_tool_call({"score": scores[slot], "rationale": "Тест", "breakdown": {}, "red_flags": []})

    client = FakeAnthropicClient(_respond)
    return Matcher(client=client, model="claude-sonnet-4-6"), client


async def test_discovered_job_flows_through_to_matched(monkeypatch: pytest.MonkeyPatch):
    job_repo = FakeJobRepository()
    match_repo = FakeMatchRepository()
    await job_repo.upsert_feed_cards([_card(1)])
    matcher, client = _matcher({"a": 0.82, "b": 0.4})
    fetch_calls = _patch_fetch(monkeypatch, _details(1))

    job = (await job_repo.list_processable(limit=10))[0]
    await feed_worker._process_job(
        job,
        page=None,
        job_repo=job_repo,
        match_repo=match_repo,
        matcher=matcher,
        resumes=RESUMES,
        threshold=0.65,
    )

    assert fetch_calls == [1]
    assert len(client.calls) == 2
    assert len(match_repo.rows) == 2
    scores = sorted(r.score for r in match_repo.rows)
    assert scores == [0.4, 0.82]
    assert job_repo.rows[1].status == "matched"


async def test_low_scores_mark_job_as_skipped(monkeypatch: pytest.MonkeyPatch):
    job_repo = FakeJobRepository()
    match_repo = FakeMatchRepository()
    await job_repo.upsert_feed_cards([_card(2)])
    matcher, _client = _matcher({"a": 0.3, "b": 0.2})
    _patch_fetch(monkeypatch, _details(2))

    job = (await job_repo.list_processable(limit=10))[0]
    await feed_worker._process_job(
        job,
        page=None,
        job_repo=job_repo,
        match_repo=match_repo,
        matcher=matcher,
        resumes=RESUMES,
        threshold=0.65,
    )

    assert job_repo.rows[2].status == "skipped"


async def test_already_detailed_job_skips_fetch_and_still_matches(monkeypatch: pytest.MonkeyPatch):
    job_repo = FakeJobRepository()
    match_repo = FakeMatchRepository()
    await job_repo.upsert_feed_cards([_card(3)])
    await job_repo.save_details(_details(3))
    assert job_repo.rows[3].status == "detailed"

    matcher, _client = _matcher({"a": 0.9, "b": 0.9})
    fetch_calls = _patch_fetch(monkeypatch, _details(3))

    job = (await job_repo.list_processable(limit=10))[0]
    await feed_worker._process_job(
        job,
        page=None,
        job_repo=job_repo,
        match_repo=match_repo,
        matcher=matcher,
        resumes=RESUMES,
        threshold=0.65,
    )

    assert fetch_calls == []
    assert len(match_repo.rows) == 2
    assert job_repo.rows[3].status == "matched"


async def test_existing_match_is_not_re_called(monkeypatch: pytest.MonkeyPatch):
    job_repo = FakeJobRepository()
    match_repo = FakeMatchRepository()
    await job_repo.upsert_feed_cards([_card(4)])
    await job_repo.save_details(_details(4))

    matcher, client = _matcher({"a": 0.9, "b": 0.9})
    _patch_fetch(monkeypatch, _details(4))

    job = (await job_repo.list_processable(limit=10))[0]

    # First pass: both resumes get matched.
    await feed_worker._process_job(
        job,
        page=None,
        job_repo=job_repo,
        match_repo=match_repo,
        matcher=matcher,
        resumes=RESUMES,
        threshold=0.65,
    )
    assert len(client.calls) == 2
    assert job_repo.rows[4].status == "matched"

    # Reset status back to detailed (simulating a partial run) and re-process.
    job_repo.rows[4].status = "detailed"
    job = (await job_repo.list_processable(limit=10))[0]
    await feed_worker._process_job(
        job,
        page=None,
        job_repo=job_repo,
        match_repo=match_repo,
        matcher=matcher,
        resumes=RESUMES,
        threshold=0.65,
    )
    # No additional LLM calls were issued; status was re-derived from existing rows.
    assert len(client.calls) == 2
    assert job_repo.rows[4].status == "matched"


async def test_pacer_called_before_hh_fetch_only(monkeypatch: pytest.MonkeyPatch):
    """Discovered job → pacer fires; detailed job → pacer does not."""
    job_repo = FakeJobRepository()
    match_repo = FakeMatchRepository()
    await job_repo.upsert_feed_cards([_card(10), _card(11)])
    await job_repo.save_details(_details(11))  # 11 is already detailed

    matcher, _client = _matcher({"a": 0.9, "b": 0.9})
    _patch_fetch(monkeypatch, _details(10))

    calls: list[int] = []

    async def pacer() -> None:
        calls.append(1)

    jobs = sorted(await job_repo.list_processable(limit=10), key=lambda j: j.hh_id)
    for job in jobs:
        await feed_worker._process_job(
            job,
            page=None,
            job_repo=job_repo,
            match_repo=match_repo,
            matcher=matcher,
            resumes=RESUMES,
            threshold=0.65,
            before_hh_action=pacer,
        )

    # 10 is discovered → pacer fired once; 11 was already detailed → no extra HH call.
    assert len(calls) == 1


async def test_matcher_disabled_keeps_job_in_detailed(monkeypatch: pytest.MonkeyPatch):
    job_repo = FakeJobRepository()
    match_repo = FakeMatchRepository()
    await job_repo.upsert_feed_cards([_card(5)])
    _patch_fetch(monkeypatch, _details(5))

    job = (await job_repo.list_processable(limit=10))[0]
    await feed_worker._process_job(
        job,
        page=None,
        job_repo=job_repo,
        match_repo=match_repo,
        matcher=None,
        resumes=[],
        threshold=0.65,
    )

    assert job_repo.rows[5].status == "detailed"
    assert match_repo.rows == []
