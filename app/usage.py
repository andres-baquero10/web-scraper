"""Usage records for /entries requests, stored in SQLite."""

import logging
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from app.filters import Filter

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_at    TEXT    NOT NULL,
    filter          TEXT    NOT NULL,
    result_count    INTEGER NOT NULL,
    cache_status    TEXT    NOT NULL,
    data_fetched_at TEXT,
    latency_ms      INTEGER NOT NULL,
    status_code     INTEGER NOT NULL,
    error           TEXT
)
"""

_COLUMNS = (
    "requested_at, filter, result_count, cache_status, "
    "data_fetched_at, latency_ms, status_code, error"
)


class UsageCacheStatus(StrEnum):
    """How the data in a response was served."""

    HIT = "hit"
    MISS = "miss"
    STALE = "stale"
    EMPTY = "empty"
    """Nothing was cached, so the request got a 503."""


@dataclass(frozen=True)
class UsageRecord:
    """One /entries request."""

    requested_at: datetime
    filter: Filter
    result_count: int
    cache_status: UsageCacheStatus
    data_fetched_at: datetime | None
    """When the returned data was scraped; None if no data was returned."""
    latency_ms: int
    status_code: int
    error: str | None


@dataclass(frozen=True)
class StoredUsageRecord(UsageRecord):
    id: int


def _to_text(value: datetime | None) -> str | None:
    """UTC ISO-8601; raises ValueError for naive datetimes."""
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError(f"naive datetime {value!r}; usage timestamps must be UTC")
    return value.astimezone(UTC).isoformat()


def _from_text(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


class UsageRepository:
    """
    Writes and reads usage records.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def create_schema(self) -> None:
        """Create the usage table if it doesn't exist; safe to call repeatedly."""
        with closing(self._connect()) as conn, conn:
            conn.execute(_SCHEMA)

    def record(self, rec: UsageRecord) -> None:
        """Save one record. Never raises: a usage failure must not fail a request."""
        try:
            values = (
                _to_text(rec.requested_at),
                rec.filter.value,
                rec.result_count,
                rec.cache_status.value,
                _to_text(rec.data_fetched_at),
                rec.latency_ms,
                rec.status_code,
                rec.error,
            )
            with closing(self._connect()) as conn, conn:
                conn.execute(
                    f"INSERT INTO usage ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
        except Exception:
            logger.exception("Failed to save usage record")

    def recent(self, limit: int, offset: int) -> list[StoredUsageRecord]:
        """Return records newest first. Storage errors are raised."""
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"SELECT id, {_COLUMNS} FROM usage "
                "ORDER BY requested_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [
            StoredUsageRecord(
                id=row_id,
                requested_at=datetime.fromisoformat(requested_at),
                filter=Filter(filter_),
                result_count=result_count,
                cache_status=UsageCacheStatus(cache_status),
                data_fetched_at=_from_text(data_fetched_at),
                latency_ms=latency_ms,
                status_code=status_code,
                error=error,
            )
            for (
                row_id,
                requested_at,
                filter_,
                result_count,
                cache_status,
                data_fetched_at,
                latency_ms,
                status_code,
                error,
            ) in rows
        ]
