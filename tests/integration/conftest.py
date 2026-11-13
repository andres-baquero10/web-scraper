from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

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
