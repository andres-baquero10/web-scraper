from datetime import UTC, datetime, timedelta

import pytest

from app.cache import CacheStatus, SnapshotCache
from app.models import Entry

TTL = 60.0
START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _entries(count: int) -> list[Entry]:
    return [
        Entry(number=n, id=n, title=f"Story {n}", points=n, comments=n)
        for n in range(1, count + 1)
    ]


class FakeClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeFetcher:
    def __init__(self, count: int = 30) -> None:
        self.count = count
        self.calls = 0

    async def __call__(self) -> list[Entry]:
        self.calls += 1
        return _entries(self.count)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def cache(fetcher: FakeFetcher, clock: FakeClock) -> SnapshotCache:
    return SnapshotCache(fetcher, ttl_seconds=TTL, clock=clock)


@pytest.mark.anyio
async def test_first_call_is_a_miss_and_fetches(
    cache: SnapshotCache, fetcher: FakeFetcher
) -> None:
    result = await cache.get()

    assert result.status is CacheStatus.MISS
    assert fetcher.calls == 1
    assert result.snapshot.entries == tuple(_entries(30))
    assert result.snapshot.fetched_at == START


@pytest.mark.anyio
async def test_call_within_ttl_is_a_hit_without_fetching(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    first = await cache.get()
    clock.advance(TTL - 1)
    second = await cache.get()

    assert second.status is CacheStatus.HIT
    assert fetcher.calls == 1
    assert second.snapshot is first.snapshot


@pytest.mark.anyio
async def test_call_once_ttl_has_passed_fetches_again(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get()
    clock.advance(TTL)
    result = await cache.get()

    assert result.status is CacheStatus.MISS
    assert fetcher.calls == 2
    assert result.snapshot.fetched_at == START + timedelta(seconds=TTL)


@pytest.mark.anyio
async def test_partial_result_is_incomplete_and_cached(clock: FakeClock) -> None:
    fetcher = FakeFetcher(count=29)
    cache = SnapshotCache(fetcher, ttl_seconds=TTL, clock=clock)

    first = await cache.get()
    clock.advance(1)
    second = await cache.get()

    assert first.snapshot.complete is False
    assert second.status is CacheStatus.HIT
    assert fetcher.calls == 1


@pytest.mark.anyio
async def test_default_clock_stamps_snapshots_in_utc(fetcher: FakeFetcher) -> None:
    result = await SnapshotCache(fetcher, ttl_seconds=TTL).get()

    assert result.snapshot.fetched_at.tzinfo is UTC
