"""In-memory cache of the latest front-page snapshot."""

import asyncio
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


def utc_now() -> datetime:
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

    Only one refresh runs at a time. The request that starts it waits for
    the result; concurrent requests get the current snapshot straight away,
    or, when nothing is cached yet, wait for that same refresh.
    """

    def __init__(
        self, fetcher: Fetcher, ttl_seconds: float, clock: Clock = utc_now
    ) -> None:
        self._fetcher = fetcher
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._snapshot: Snapshot | None = None
        self._last_attempt: datetime | None = None
        self._last_error: str | None = None
        """Why the latest finished refresh failed; None if it succeeded."""
        self._refreshing: asyncio.Task[CacheResult] | None = None

    async def get(self) -> CacheResult:
        """Return the current snapshot; raise NoDataError if there is none."""
        now = self._clock()
        if self._refreshing is None and self._expired(now):
            self._last_attempt = now
            self._refreshing = asyncio.create_task(self._refresh(now))
            return await asyncio.shield(self._refreshing)
        if self._refreshing is not None and self._snapshot is None:
            return await asyncio.shield(self._refreshing)
        return self._cached()

    async def _refresh(self, now: datetime) -> CacheResult:
        try:
            entries = tuple(await self._fetcher())
            if not entries:
                # An empty front page means a layout change or an error page.
                raise FetchError("scrape returned no entries")
        except FetchError as exc:
            logger.warning("Refresh failed: %s", exc)
            self._last_error = str(exc)
            return self._cached()
        except BaseException:
            self._last_error = "unexpected error while refreshing"
            raise
        else:
            self._snapshot = Snapshot(entries=entries, fetched_at=now)
            self._last_error = None
            return CacheResult(self._snapshot, CacheStatus.MISS)
        finally:
            self._refreshing = None

    def _cached(self) -> CacheResult:
        if self._snapshot is None:
            raise NoDataError(self._last_error or "Hacker News is unavailable")
        status = CacheStatus.STALE if self._last_error else CacheStatus.HIT
        return CacheResult(self._snapshot, status)

    def _expired(self, now: datetime) -> bool:
        if self._last_attempt is None:
            return True
        age = (now - self._last_attempt).total_seconds()
        return age >= self._ttl_seconds
