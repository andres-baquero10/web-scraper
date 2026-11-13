"""Response models for the HTTP API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.filters import Filter
from app.usage import UsageCacheStatus


class EntryPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    id: int
    title: str
    points: int | None
    comments: int | None


class EntriesResponse(BaseModel):
    fetched_at: datetime
    """When the data was scraped (UTC)."""
    stale: bool
    """True if served after a failed refresh."""
    complete: bool
    """False if the scrape found fewer than 30 entries."""
    entries: list[EntryPublic]


class UsageRecordPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    requested_at: datetime
    """When the /entries request arrived (UTC)."""
    filter: Filter
    result_count: int
    cache_status: UsageCacheStatus
    data_fetched_at: datetime | None
    """When the returned data was scraped (UTC); null if no data was returned."""
    latency_ms: float
    """Time spent handling the request, in milliseconds (microsecond resolution)."""
    status_code: int
    error: str | None
