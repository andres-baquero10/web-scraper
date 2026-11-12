import dataclasses

import pytest

from app.models import Entry


def test_entry_is_frozen() -> None:
    entry = Entry(number=1, id=42, title="Hello", points=10, comments=3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.points = 99  # type: ignore[misc]


def test_entry_allows_missing_points_and_comments() -> None:
    job = Entry(number=7, id=43, title="We're hiring", points=None, comments=None)
    assert job.points is None
    assert job.comments is None
