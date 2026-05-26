from datetime import UTC, datetime

from hhack.persistence.job_repository import FeedCard, JobDetails
from tests.persistence.fakes import FakeJobRepository


def _card(hh_id: int, *, position: int = 1) -> FeedCard:
    return FeedCard(
        hh_id=hh_id,
        url=f"https://hh.ru/vacancy/{hh_id}",
        title=f"Job {hh_id}",
        company="Acme",
        snippet="short text",
        feed_resume_hint=None,
        feed_position=position,
    )


async def test_upsert_inserts_new_and_returns_ids():
    repo = FakeJobRepository()
    inserted = await repo.upsert_feed_cards([_card(1), _card(2)])
    assert sorted(inserted) == [1, 2]


async def test_upsert_is_idempotent_on_hh_id():
    repo = FakeJobRepository()
    await repo.upsert_feed_cards([_card(1)])
    inserted = await repo.upsert_feed_cards([_card(1), _card(2)])
    assert inserted == [2]
    assert await repo.filter_known([1, 2, 3]) == {1, 2}


async def test_list_pending_details_excludes_detailed():
    repo = FakeJobRepository()
    await repo.upsert_feed_cards([_card(1), _card(2)])
    await repo.save_details(
        JobDetails(
            hh_id=1,
            full_text="body",
            salary=None,
            location=None,
            employment_type=None,
            posted_at=None,
        )
    )
    pending = await repo.list_pending_details(limit=10)
    assert [job.hh_id for job in pending] == [2]


async def test_save_details_returns_false_for_unknown_job():
    repo = FakeJobRepository()
    saved = await repo.save_details(
        JobDetails(
            hh_id=999,
            full_text=None,
            salary=None,
            location=None,
            employment_type=None,
            posted_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    assert saved is False
