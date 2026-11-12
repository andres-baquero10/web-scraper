"""Domain model for scraped Hacker News entries."""

from dataclasses import dataclass


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
