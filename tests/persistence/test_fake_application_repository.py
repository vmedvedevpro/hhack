from __future__ import annotations

from hhack.matching.letter_writer import LetterDraft
from tests.persistence.fakes import FakeApplicationRepository


def _draft(*, job_id: int = 1, prompt_hash: str = "abc", body: str = "hi") -> LetterDraft:
    return LetterDraft(
        job_id=job_id,
        resume_id="resume-x",
        model="claude-haiku-4-5-20251001",
        prompt_hash=prompt_hash,
        cover_letter=body,
        language="ru",
        input_tokens=10,
        output_tokens=20,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


async def test_save_then_exists_is_true():
    repo = FakeApplicationRepository()
    assert await repo.save(_draft()) is True
    assert await repo.exists(job_id=1, prompt_hash="abc") is True


async def test_save_is_idempotent_on_job_and_prompt_hash():
    repo = FakeApplicationRepository()
    assert await repo.save(_draft(body="v1")) is True
    assert await repo.save(_draft(body="v2")) is False
    assert len(repo.rows) == 1
    assert repo.rows[0].cover_letter == "v1"


async def test_different_prompt_hash_creates_second_row():
    repo = FakeApplicationRepository()
    await repo.save(_draft(prompt_hash="old"))
    assert await repo.save(_draft(prompt_hash="new")) is True
    assert len(repo.rows) == 2
