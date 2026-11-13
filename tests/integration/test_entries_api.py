from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.filters import Filter, apply_filter
from app.main import create_app
from app.scraping.fetcher import FetchError
from app.scraping.parser import parse
from app.usage import UsageRepository

FIXTURE = Path(__file__).parent.parent / "fixtures" / "front_page.html"
HTML = FIXTURE.read_text(encoding="utf-8")
TTL = 60.0
START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakePageFetcher:
    """Returns the saved front page, or raises ``error`` when it is set."""

    def __init__(self) -> None:
        self.error: Exception | None = None

    async def __call__(self) -> str:
        if self.error is not None:
            raise self.error
        return HTML


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fetcher() -> FakePageFetcher:
    return FakePageFetcher()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "usage.db"


@pytest.fixture
def client(
    db_path: Path, fetcher: FakePageFetcher, clock: FakeClock
) -> Iterator[TestClient]:
    settings = Settings(cache_ttl_seconds=TTL, db_path=db_path)
    app = create_app(settings, fetcher=fetcher, clock=clock)
    with TestClient(app) as test_client:  # runs the lifespan
        yield test_client


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
