import asyncio
from datetime import UTC, datetime, timedelta

import anyio
import pytest

from app.cache import CacheStatus, NoDataError, SnapshotCache
from app.models import Entry
from app.scraping.fetcher import FetchError

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
    """Returns ``count`` entries, or raises ``error`` when it is set.

    When ``gate`` is set, each fetch signals ``started`` and then blocks
    until the gate opens, so tests control exactly when it finishes.
    """

    def __init__(self, count: int = 30) -> None:
        self.count = count
        self.error: Exception | None = None
        self.calls = 0
        self.gate: asyncio.Event | None = None
        self.started = asyncio.Event()

    async def __call__(self) -> list[Entry]:
        self.calls += 1
        self.started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
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


@pytest.mark.anyio
async def test_failure_with_cached_data_serves_it_as_stale(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    first = await cache.get()
    clock.advance(TTL)
    fetcher.error = FetchError("HN returned 503")
    result = await cache.get()

    assert result.status is CacheStatus.STALE
    assert result.snapshot is first.snapshot
    assert result.snapshot.fetched_at == START


@pytest.mark.anyio
async def test_failure_with_nothing_cached_raises_no_data(
    cache: SnapshotCache, fetcher: FakeFetcher
) -> None:
    fetcher.error = FetchError("HN returned 503")

    with pytest.raises(NoDataError, match="HN returned 503"):
        await cache.get()


@pytest.mark.anyio
async def test_after_failure_waits_a_full_ttl_before_fetching_again(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get()
    clock.advance(TTL)
    fetcher.error = FetchError("timeout")
    await cache.get()

    clock.advance(TTL - 1)
    within_ttl = await cache.get()
    assert within_ttl.status is CacheStatus.STALE
    assert fetcher.calls == 2

    fetcher.error = None
    clock.advance(1)
    recovered = await cache.get()
    assert recovered.status is CacheStatus.MISS
    assert fetcher.calls == 3
    assert (await cache.get()).status is CacheStatus.HIT


@pytest.mark.anyio
async def test_failure_with_nothing_cached_is_not_retried_within_ttl(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    fetcher.error = FetchError("timeout")
    with pytest.raises(NoDataError):
        await cache.get()

    clock.advance(TTL - 1)
    with pytest.raises(NoDataError):
        await cache.get()
    assert fetcher.calls == 1


@pytest.mark.anyio
async def test_zero_entries_counts_as_a_failure(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    fetcher.count = 0
    with pytest.raises(NoDataError, match="no entries"):
        await cache.get()

    fetcher.count = 30
    clock.advance(TTL)
    first = await cache.get()
    fetcher.count = 0
    clock.advance(TTL)
    result = await cache.get()

    assert result.status is CacheStatus.STALE
    assert result.snapshot is first.snapshot


@pytest.mark.anyio
async def test_unexpected_error_propagates_and_later_calls_serve_stale(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    await cache.get()
    clock.advance(TTL)
    fetcher.error = RuntimeError("parser bug")
    with pytest.raises(RuntimeError):
        await cache.get()

    clock.advance(1)
    result = await cache.get()

    assert result.status is CacheStatus.STALE
    assert fetcher.calls == 2


CONCURRENT_CALLS = 50


@pytest.mark.anyio
async def test_concurrent_calls_on_empty_cache_share_one_fetch(
    cache: SnapshotCache, fetcher: FakeFetcher
) -> None:
    fetcher.gate = asyncio.Event()
    calls = [asyncio.create_task(cache.get()) for _ in range(CONCURRENT_CALLS)]
    await fetcher.started.wait()
    assert not any(call.done() for call in calls)

    fetcher.gate.set()
    results = await asyncio.gather(*calls)

    assert fetcher.calls == 1
    assert all(result.status is CacheStatus.MISS for result in results)
    assert all(result.snapshot is results[0].snapshot for result in results)


@pytest.mark.anyio
async def test_concurrent_calls_on_empty_cache_share_one_failure(
    cache: SnapshotCache, fetcher: FakeFetcher
) -> None:
    fetcher.gate = asyncio.Event()
    fetcher.error = FetchError("HN returned 503")
    calls = [asyncio.create_task(cache.get()) for _ in range(CONCURRENT_CALLS)]
    await fetcher.started.wait()

    fetcher.gate.set()
    results = await asyncio.gather(*calls, return_exceptions=True)

    assert fetcher.calls == 1
    assert all(isinstance(result, NoDataError) for result in results)


@pytest.mark.anyio
async def test_calls_during_a_refresh_get_the_cached_snapshot_without_waiting(
    cache: SnapshotCache, fetcher: FakeFetcher, clock: FakeClock
) -> None:
    previous = await cache.get()
    clock.advance(TTL)
    fetcher.started.clear()
    fetcher.gate = asyncio.Event()
    trigger = asyncio.create_task(cache.get())
    await fetcher.started.wait()

    with anyio.fail_after(1):
        during = [await cache.get() for _ in range(CONCURRENT_CALLS - 1)]

    assert all(result.status is CacheStatus.HIT for result in during)
    assert all(result.snapshot is previous.snapshot for result in during)
    assert not trigger.done()

    fetcher.gate.set()
    refreshed = await trigger

    assert fetcher.calls == 2
    assert refreshed.status is CacheStatus.MISS
    assert refreshed.snapshot.fetched_at == START + timedelta(seconds=TTL)
    assert (await cache.get()).snapshot is refreshed.snapshot
