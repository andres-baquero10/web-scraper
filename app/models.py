"""Domain model for scraped Hacker News entries."""

from dataclasses import dataclass
from datetime import datetime

FRONT_PAGE_SIZE = 30
"""Number of entries on a full HN front page."""


@dataclass(frozen=True)
class Entry:
    """One front-page entry.

    Frozen because the same entries are shared by every request served from
    the cache, so no caller may change them.
    """

    number: int
    """Rank shown on the front page (1-30)."""
    id: int
    """Hacker News item id."""
    title: str
    points: int | None
    """None for job posts, which have no score."""
    comments: int | None
    """None for job posts; 0 for a story showing "discuss"."""


@dataclass(frozen=True)
class Snapshot:
    """The entries from one scrape of the front page."""

    entries: tuple[Entry, ...]
    fetched_at: datetime
    """When the scrape happened (UTC)."""

    @property
    def complete(self) -> bool:
        """False if the scrape found fewer entries than a full front page."""
        return len(self.entries) >= FRONT_PAGE_SIZE
