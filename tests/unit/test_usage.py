import logging
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.filters import Filter
from app.usage import StoredUsageRecord, UsageCacheStatus, UsageRecord, UsageRepository

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _record(requested_at: datetime = START) -> UsageRecord:
    return UsageRecord(
        requested_at=requested_at,
        filter=Filter.LONG,
        result_count=12,
        cache_status=UsageCacheStatus.HIT,
        data_fetched_at=START - timedelta(seconds=20),
        latency_ms=0.042,
        status_code=200,
        error=None,
    )


@pytest.fixture
def repo(tmp_path: Path) -> UsageRepository:
    repository = UsageRepository(tmp_path / "usage.db")
    repository.create_schema()
    return repository


def test_record_round_trips_every_field(repo: UsageRepository) -> None:
    record = _record()
    repo.record(record)

    [stored] = repo.recent(limit=10, offset=0)

    assert stored == StoredUsageRecord(id=stored.id, **vars(record))
    assert isinstance(stored.id, int)


def test_timestamps_are_stored_as_utc_iso_8601(
    repo: UsageRepository, tmp_path: Path
) -> None:
    utc_minus_5 = timezone(timedelta(hours=-5))
    repo.record(_record(requested_at=datetime(2026, 1, 1, 7, 0, tzinfo=utc_minus_5)))

    with closing(sqlite3.connect(tmp_path / "usage.db")) as conn:
        raw = conn.execute("SELECT requested_at FROM usage").fetchone()[0]

    assert raw == "2026-01-01T12:00:00+00:00"


def test_recent_returns_newest_first(repo: UsageRepository) -> None:
    for minutes in (1, 3, 2):
        repo.record(_record(requested_at=START + timedelta(minutes=minutes)))

    times = [r.requested_at for r in repo.recent(limit=10, offset=0)]

    assert times == [START + timedelta(minutes=m) for m in (3, 2, 1)]


def test_limit_and_offset_page_through_records(repo: UsageRepository) -> None:
    for minutes in range(5):
        repo.record(_record(requested_at=START + timedelta(minutes=minutes)))

    pages = [
        [r.requested_at.minute for r in repo.recent(limit=2, offset=offset)]
        for offset in (0, 2, 4)
    ]

    assert pages == [[4, 3], [2, 1], [0]]


def test_error_text_is_stored_literally(repo: UsageRepository) -> None:
    payload = "'); DROP TABLE usage; --"
    record = replace(
        _record(),
        result_count=0,
        cache_status=UsageCacheStatus.EMPTY,
        data_fetched_at=None,
        status_code=503,
        error=payload,
    )
    repo.record(record)

    [stored] = repo.recent(limit=10, offset=0)

    assert stored == StoredUsageRecord(id=stored.id, **vars(record))


def test_record_on_broken_database_logs_and_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repo = UsageRepository(tmp_path / "usage.db")  # schema never created

    with caplog.at_level(logging.ERROR, logger="app.usage"):
        repo.record(_record())

    assert "Failed to save usage record" in caplog.text


def test_create_schema_is_idempotent(repo: UsageRepository) -> None:
    repo.create_schema()
    repo.record(_record())

    assert len(repo.recent(limit=10, offset=0)) == 1
