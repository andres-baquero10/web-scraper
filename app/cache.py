"""In-memory cache of the latest front-page snapshot."""

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.models import Entry, Snapshot
from app.scraping.fetcher import FetchError

Clock = Callable[[], datetime]
"""Returns the current time (UTC)."""

Fetcher = Callable[[], Awaitable[Sequence[Entry]]]
"""Scrapes the front page and returns its entries; raises FetchError on failure."""

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CacheStatus(StrEnum):
    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    """Old data served because the last refresh failed."""


class NoDataError(Exception):
    """The last refresh failed and there is no older snapshot to serve."""


@dataclass(frozen=True)
class CacheResult:
    snapshot: Snapshot
    status: CacheStatus


class SnapshotCache:
    """Serves the cached snapshot until the TTL passes, then fetches again.

    Fetching happens only when ``get()`` is called after expiry. The TTL is
    timed from the last attempt, successful or not, so HN is contacted at
    most once per TTL and failures need no separate backoff. A failed
    refresh keeps the previous snapshot, which is served as stale.
    """

    def __init__(
        self, fetcher: Fetcher, ttl_seconds: float, clock: Clock = _utc_now
    ) -> None:
        self._fetcher = fetcher
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._snapshot: Snapshot | None = None
        self._last_attempt: datetime | None = None
        self._last_error: str | None = None
        """Why the latest attempt failed; only used for the NoDataError message."""

    async def get(self) -> CacheResult:
        """Return the current snapshot; raise NoDataError if there is none."""
        now = self._clock()
        if self._expired(now):
            self._last_attempt = now
            self._last_error = None
            try:
                entries = tuple(await self._fetcher())
                if not entries:
                    # An empty front page means a layout change or an error page.
                    raise FetchError("scrape returned no entries")
            except FetchError as exc:
                logger.warning("Refresh failed: %s", exc)
                self._last_error = str(exc)
            else:
                self._snapshot = Snapshot(entries=entries, fetched_at=now)
                return CacheResult(self._snapshot, CacheStatus.MISS)

        if self._snapshot is None:
            raise NoDataError(self._last_error or "Hacker News is unavailable")
        # Data is fresh only if it came from the latest attempt.
        fresh = self._snapshot.fetched_at == self._last_attempt
        status = CacheStatus.HIT if fresh else CacheStatus.STALE
        return CacheResult(self._snapshot, status)

    def _expired(self, now: datetime) -> bool:
        if self._last_attempt is None:
            return True
        age = (now - self._last_attempt).total_seconds()
        return age >= self._ttl_seconds
