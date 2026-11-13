from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.filters import Filter
from app.usage import UsageCacheStatus, UsageRecord, UsageRepository
from tests.integration.conftest import START


def _seed(db_path: Path, count: int) -> None:
    """Write ``count`` rows; row i is requested i minutes after START."""
    repo = UsageRepository(db_path)
    for i in range(count):
        repo.record(
            UsageRecord(
                requested_at=START + timedelta(minutes=i),
                filter=Filter.SHORT,
                result_count=i,
                cache_status=UsageCacheStatus.HIT,
                data_fetched_at=START,
                latency_ms=3,
                status_code=200,
                error=None,
            )
        )


def _counts(response_json: list[dict[str, object]]) -> list[object]:
    return [row["result_count"] for row in response_json]


def test_returns_records_newest_first(client: TestClient, db_path: Path) -> None:
    _seed(db_path, 3)

    response = client.get("/usage")

    assert response.status_code == 200
    body = response.json()
    assert _counts(body) == [2, 1, 0]
    newest = body[0]
    assert set(newest) == {
        "id",
        "requested_at",
        "filter",
        "result_count",
        "cache_status",
        "data_fetched_at",
        "latency_ms",
        "status_code",
        "error",
    }
    assert newest["filter"] == "short"
    assert newest["cache_status"] == "hit"
    assert datetime.fromisoformat(newest["requested_at"]) == START + timedelta(
        minutes=2
    )
    assert datetime.fromisoformat(newest["data_fetched_at"]) == START
    assert newest["error"] is None


def test_limit_defaults_to_50(client: TestClient, db_path: Path) -> None:
    _seed(db_path, 51)

    body = client.get("/usage").json()

    assert _counts(body) == list(range(50, 0, -1))


def test_offset_pages_back_through_older_records(
    client: TestClient, db_path: Path
) -> None:
    _seed(db_path, 5)

    body = client.get("/usage", params={"limit": 2, "offset": 1}).json()

    assert _counts(body) == [3, 2]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_out_of_range_paging_gives_422(
    client: TestClient, params: dict[str, int]
) -> None:
    assert client.get("/usage", params=params).status_code == 422


def test_reading_usage_is_not_logged(client: TestClient) -> None:
    assert client.get("/usage").json() == []
    assert client.get("/usage").json() == []

    client.get("/entries")
    client.get("/usage")

    assert len(client.get("/usage").json()) == 1
