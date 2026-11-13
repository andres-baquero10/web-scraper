import dataclasses
from datetime import UTC, datetime

import pytest

from app.models import Entry, Snapshot


def test_entry_is_frozen() -> None:
    entry = Entry(number=1, id=42, title="Hello", points=10, comments=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.points = 99  # type: ignore[misc]


def test_entry_allows_missing_points_and_comments() -> None:
    job = Entry(number=7, id=43, title="We're hiring", points=None, comments=None)
    assert job.points is None
    assert job.comments is None


def _entries(count: int) -> tuple[Entry, ...]:
    return tuple(
        Entry(number=n, id=n, title=f"Story {n}", points=n, comments=n)
        for n in range(1, count + 1)
    )


def test_snapshot_is_frozen() -> None:
    snapshot = Snapshot(entries=_entries(1), fetched_at=datetime.now(UTC))
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.entries = ()  # type: ignore[misc]


@pytest.mark.parametrize(("count", "complete"), [(30, True), (29, False)])
def test_snapshot_is_complete_only_with_30_entries(count: int, complete: bool) -> None:
    snapshot = Snapshot(entries=_entries(count), fetched_at=datetime.now(UTC))
    assert snapshot.complete is complete
