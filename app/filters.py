"""Filters over front-page entries."""

from collections.abc import Sequence
from enum import StrEnum

from app.models import Entry
from app.words import count_words

LONG_TITLE_MIN_WORDS = 6
"""Titles with more than 5 words are "long"; 5 or fewer are "short"."""


class Filter(StrEnum):
    LONG = "long"
    SHORT = "short"
    ALL = "all"


def _sort_key(value: int | None, rank: int) -> tuple[bool, int, int]:
    """Sort key: highest value first, None last, ties broken by lowest rank.

    Tuples compare element by element: False sorts before True, so entries
    with a value come before those without; negating the value puts the
    highest first; the rank settles ties.
    """
    has_no_value = value is None
    return (has_no_value, -(value or 0), rank)


def _is_long(entry: Entry) -> bool:
    return count_words(entry.title) >= LONG_TITLE_MIN_WORDS


def apply_filter(entries: Sequence[Entry], selected_filter: Filter) -> list[Entry]:
    """Return a new list of the entries selected by ``selected_filter``, in its order.

    - ``long``: titles with more than 5 words, most comments first.
    - ``short``: titles with 5 or fewer words, most points first.
    - ``all``: every entry, in front-page rank order.

    Entries without a value (job posts) come last, and ties keep rank order,
    so the output is deterministic. The input is never modified.
    """
    match selected_filter:
        case Filter.LONG:
            selected = [e for e in entries if _is_long(e)]
            return sorted(selected, key=lambda e: _sort_key(e.comments, e.number))
        case Filter.SHORT:
            selected = [e for e in entries if not _is_long(e)]
            return sorted(selected, key=lambda e: _sort_key(e.points, e.number))
        case Filter.ALL:
            return sorted(entries, key=lambda e: e.number)
