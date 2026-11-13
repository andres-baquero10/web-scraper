import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.filters import Filter, apply_filter
from app.scraping.fetcher import FetchError
from app.scraping.parser import parse
from app.usage import UsageCacheStatus, UsageRepository
from tests.integration.conftest import HTML, START, TTL, FakeClock, FakePageFetcher


def _expected_numbers(selected: Filter) -> list[int]:
    return [e.number for e in apply_filter(parse(HTML).entries, selected)]


@pytest.mark.parametrize("selected", list(Filter))
def test_each_filter_returns_its_entries_in_order(
    client: TestClient, selected: Filter
) -> None:
    response = client.get("/entries", params={"filter": selected.value})

    assert response.status_code == 200
    numbers = [e["number"] for e in response.json()["entries"]]
    assert numbers == _expected_numbers(selected)


def test_filter_defaults_to_all(client: TestClient) -> None:
    response = client.get("/entries")

    assert response.status_code == 200
    numbers = [e["number"] for e in response.json()["entries"]]
    assert numbers == _expected_numbers(Filter.ALL)


def test_response_reports_freshness_and_entry_fields(client: TestClient) -> None:
    body = client.get("/entries").json()

    assert set(body) == {"fetched_at", "stale", "complete", "entries"}
    assert datetime.fromisoformat(body["fetched_at"]) == START
    assert body["stale"] is False
    assert body["complete"] is True
    assert set(body["entries"][0]) == {"number", "id", "title", "points", "comments"}


def test_invalid_filter_gives_422(client: TestClient) -> None:
    assert client.get("/entries", params={"filter": "bogus"}).status_code == 422


def test_failed_refresh_serves_old_data_as_stale(
    client: TestClient, fetcher: FakePageFetcher, clock: FakeClock
) -> None:
    client.get("/entries")
    clock.advance(TTL)
    fetcher.error = FetchError("HN returned 503")

    response = client.get("/entries")

    assert response.status_code == 200
    body = response.json()
    assert body["stale"] is True
    assert datetime.fromisoformat(body["fetched_at"]) == START
    assert len(body["entries"]) == 30


def test_failure_with_nothing_cached_gives_503(
    client: TestClient, fetcher: FakePageFetcher
) -> None:
    fetcher.error = FetchError("HN returned 503")

    response = client.get("/entries")

    assert response.status_code == 503
    assert response.json()["detail"]


def test_startup_creates_usage_schema(client: TestClient, db_path: Path) -> None:
    assert UsageRepository(db_path).recent(limit=1, offset=0) == []


def test_request_records_a_usage_row(client: TestClient, db_path: Path) -> None:
    response = client.get("/entries", params={"filter": "short"})

    [row] = UsageRepository(db_path).recent(limit=10, offset=0)
    assert row.request_id == response.headers["X-Request-ID"]
    assert row.requested_at == START
    assert row.filter is Filter.SHORT
    assert row.result_count == len(response.json()["entries"])
    assert row.cache_status is UsageCacheStatus.MISS
    assert row.data_fetched_at == START
    assert row.latency_ms >= 0
    assert row.status_code == 200
    assert row.error is None


def test_usage_cache_status_follows_the_cache(
    client: TestClient, db_path: Path, fetcher: FakePageFetcher, clock: FakeClock
) -> None:
    client.get("/entries")  # miss
    client.get("/entries")  # hit
    clock.advance(TTL)
    fetcher.error = FetchError("HN returned 503")
    client.get("/entries")  # stale

    rows = UsageRepository(db_path).recent(limit=10, offset=0)
    assert [r.cache_status for r in rows] == [
        UsageCacheStatus.STALE,
        UsageCacheStatus.HIT,
        UsageCacheStatus.MISS,
    ]


def test_503_is_recorded_as_empty_with_error(
    client: TestClient, db_path: Path, fetcher: FakePageFetcher
) -> None:
    fetcher.error = FetchError("HN returned 503")

    client.get("/entries")

    [row] = UsageRepository(db_path).recent(limit=10, offset=0)
    assert row.cache_status is UsageCacheStatus.EMPTY
    assert row.status_code == 503
    assert row.result_count == 0
    assert row.data_fetched_at is None
    assert row.error


def test_broken_usage_database_still_returns_200(
    client: TestClient, db_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE usage")

    response = client.get("/entries")

    assert response.status_code == 200
    assert len(response.json()["entries"]) == 30
    assert "Failed to save usage record" in caplog.text


def test_each_request_gets_its_own_request_id(client: TestClient) -> None:
    ids = [client.get("/entries").headers["X-Request-ID"] for _ in range(2)]

    assert ids[0] != ids[1]
    assert all(str(UUID(rid)) == rid for rid in ids)


def test_request_id_finds_the_usage_row(client: TestClient) -> None:
    client.get("/entries", params={"filter": "long"})
    response = client.get("/entries", params={"filter": "short"})
    request_id = response.headers["X-Request-ID"]

    [row] = client.get("/usage", params={"request_id": request_id}).json()

    assert row["request_id"] == request_id
    assert row["filter"] == "short"


def test_503_carries_a_request_id_for_its_usage_row(
    client: TestClient, db_path: Path, fetcher: FakePageFetcher
) -> None:
    fetcher.error = FetchError("HN returned 503")

    response = client.get("/entries")

    assert response.status_code == 503
    [row] = UsageRepository(db_path).recent(limit=10, offset=0)
    assert row.request_id == response.headers["X-Request-ID"]
    assert row.status_code == 503


def test_unexpected_error_gives_500_with_a_usage_row(
    client: TestClient, db_path: Path, fetcher: FakePageFetcher
) -> None:
    fetcher.error = RuntimeError("parser bug")

    response = client.get("/entries")

    assert response.status_code == 500
    [row] = UsageRepository(db_path).recent(limit=10, offset=0)
    assert row.request_id == response.headers["X-Request-ID"]
    assert row.status_code == 500
    assert row.cache_status is UsageCacheStatus.EMPTY
    assert row.error == "unexpected error: RuntimeError"
