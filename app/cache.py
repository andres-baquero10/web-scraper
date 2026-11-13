"""In-memory cache of the latest front-page snapshot."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.models import Entry, Snapshot

Clock = Callable[[], datetime]
"""Returns the current time (UTC)."""

Fetcher = Callable[[], Awaitable[Sequence[Entry]]]
"""Scrapes the front page and returns its entries."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CacheStatus(StrEnum):
    HIT = "hit"
    MISS = "miss"


@dataclass(frozen=True)
class CacheResult:
    snapshot: Snapshot
    status: CacheStatus


class SnapshotCache:
    """Serves the cached snapshot until the TTL passes, then fetches again.

    Fetching happens only when ``get()`` is called after expiry.
    """

    def __init__(
        self, fetcher: Fetcher, ttl_seconds: float, clock: Clock = _utc_now
    ) -> None:
        self._fetcher = fetcher
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._snapshot: Snapshot | None = None
        self._last_attempt: datetime | None = None

    async def get(self) -> CacheResult:
        now = self._clock()
        if self._snapshot is not None and not self._expired(now):
            return CacheResult(self._snapshot, CacheStatus.HIT)

        self._last_attempt = now
        entries = await self._fetcher()
        self._snapshot = Snapshot(entries=tuple(entries), fetched_at=now)
        return CacheResult(self._snapshot, CacheStatus.MISS)

    def _expired(self, now: datetime) -> bool:
        if self._last_attempt is None:
            return True
        age = (now - self._last_attempt).total_seconds()
        return age >= self._ttl_seconds
