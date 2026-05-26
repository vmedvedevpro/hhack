from __future__ import annotations

from hhack.matching.matcher import MatchResult
from tests.persistence.fakes import FakeMatchRepository


def _result(*, job_id: int = 1, resume_id: str = "a", prompt_hash: str = "abc", score: float = 0.5) -> MatchResult:
    return MatchResult(
        job_id=job_id,
        resume_id=resume_id,
        model="claude-sonnet-4-6",
        prompt_hash=prompt_hash,
        score=score,
        rationale="rationale",
        payload={"score": score, "rationale": "rationale"},
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


async def test_save_then_exists_is_true():
    repo = FakeMatchRepository()
    assert await repo.save(_result()) is True
    assert await repo.exists(job_id=1, resume_id="a", prompt_hash="abc") is True


async def test_save_is_idempotent_on_unique_triple():
    repo = FakeMatchRepository()
    assert await repo.save(_result(score=0.5)) is True
    # Second insert with the same triple returns False and does not duplicate.
    assert await repo.save(_result(score=0.9)) is False
    assert len(repo.rows) == 1
    # The first score wins because the second insert was a no-op.
    assert repo.rows[0].score == 0.5


async def test_best_score_picks_max_across_resumes():
    repo = FakeMatchRepository()
    await repo.save(_result(resume_id="a", score=0.3))
    await repo.save(_result(resume_id="b", score=0.7))
    await repo.save(_result(job_id=2, resume_id="a", score=0.9))
    assert await repo.best_score(1) == 0.7
    assert await repo.best_score(2) == 0.9
    assert await repo.best_score(999) is None
