"""Response models for the HTTP API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


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
