import copy
import random
from collections import Counter
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.filters import Filter, apply_filter
from app.models import Entry
from app.words import count_words

LONG_TITLE = "one two three four five six"  # 6 words
SHORT_TITLE = "one two three four five"  # 5 words


def make_entry(
    number: int,
    title: str,
    points: int | None = 0,
    comments: int | None = 0,
) -> Entry:
    return Entry(
        number=number, id=1000 + number, title=title, points=points, comments=comments
    )


def numbers(entries: list[Entry]) -> list[int]:
    return [entry.number for entry in entries]


def test_filter_values() -> None:
    assert {f.value for f in Filter} == {"long", "short", "all"}
    assert Filter("long") is Filter.LONG


def test_long_keeps_titles_over_five_words_sorted_by_comments() -> None:
    entries = [
        make_entry(1, LONG_TITLE, comments=5),
        make_entry(2, SHORT_TITLE, comments=500),
        make_entry(3, LONG_TITLE, comments=50),
        make_entry(4, LONG_TITLE, comments=10),
    ]
    assert numbers(apply_filter(entries, Filter.LONG)) == [3, 4, 1]


def test_short_keeps_titles_of_five_or_fewer_words_sorted_by_points() -> None:
    entries = [
        make_entry(1, SHORT_TITLE, points=5),
        make_entry(2, LONG_TITLE, points=500),
        make_entry(3, "Hi", points=50),
        make_entry(4, "", points=10),
    ]
    assert numbers(apply_filter(entries, Filter.SHORT)) == [3, 4, 1]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (SHORT_TITLE, Filter.SHORT),
        (LONG_TITLE, Filter.LONG),
        ("This is - a self-explained example", Filter.SHORT),
    ],
)
def test_word_count_boundary(title: str, expected: Filter) -> None:
    entries = [make_entry(1, title)]
    other = Filter.LONG if expected is Filter.SHORT else Filter.SHORT
    assert numbers(apply_filter(entries, expected)) == [1]
    assert apply_filter(entries, other) == []


def test_all_returns_every_entry_in_rank_order() -> None:
    entries = [make_entry(n, LONG_TITLE if n % 2 else "Hi") for n in range(1, 31)]
    shuffled = entries.copy()
    random.Random(0).shuffle(shuffled)
    assert apply_filter(shuffled, Filter.ALL) == entries


# These set points and comments to the same value, so they hold for either
# sort field; the tests above check which field each filter sorts by.
FILTER_TITLES = [(Filter.LONG, LONG_TITLE), (Filter.SHORT, SHORT_TITLE)]


def same(number: int, title: str, value: int | None) -> Entry:
    return make_entry(number, title, points=value, comments=value)


@pytest.mark.parametrize(("selected_filter", "title"), FILTER_TITLES)
def test_ties_break_by_rank(selected_filter: Filter, title: str) -> None:
    entries = [same(9, title, 10), same(2, title, 10), same(5, title, 10)]
    assert numbers(apply_filter(entries, selected_filter)) == [2, 5, 9]


@pytest.mark.parametrize(("selected_filter", "title"), FILTER_TITLES)
def test_null_sorts_last_and_zero_sorts_above_null(
    selected_filter: Filter, title: str
) -> None:
    entries = [
        same(1, title, None),  # job post
        same(2, title, 0),  # e.g. "discuss"
        same(3, title, 7),
        same(4, title, None),
    ]
    assert numbers(apply_filter(entries, selected_filter)) == [3, 2, 1, 4]


@pytest.mark.parametrize("selected_filter", list(Filter))
def test_does_not_mutate_input_and_returns_new_list(selected_filter: Filter) -> None:
    entries = [
        make_entry(3, LONG_TITLE, points=1, comments=None),
        make_entry(1, SHORT_TITLE, points=None, comments=2),
        make_entry(2, "Hi", points=5, comments=5),
    ]
    original = copy.copy(entries)
    result = apply_filter(entries, selected_filter)
    assert entries == original
    assert result is not entries


# --- Hypothesis properties -------------------------------------------------

optional_counts = st.none() | st.integers(min_value=0, max_value=10_000)


@st.composite
def entry_lists(draw: st.DrawFn) -> list[Entry]:
    ranks = draw(st.lists(st.integers(1, 1000), unique=True, max_size=40))
    return [
        Entry(
            number=rank,
            id=rank,
            title=draw(st.text()),
            points=draw(optional_counts),
            comments=draw(optional_counts),
        )
        for rank in ranks
    ]


@given(entry_lists())
def test_long_and_short_partition_entries(entries: list[Entry]) -> None:
    long_ = apply_filter(entries, Filter.LONG)
    short = apply_filter(entries, Filter.SHORT)
    assert Counter(long_) + Counter(short) == Counter(entries)
    assert all(count_words(e.title) > 5 for e in long_)
    assert all(count_words(e.title) <= 5 for e in short)


@given(entry_lists())
def test_all_is_every_entry_by_rank(entries: list[Entry]) -> None:
    result = apply_filter(entries, Filter.ALL)
    assert Counter(result) == Counter(entries)
    assert numbers(result) == sorted(e.number for e in entries)


def assert_in_order(first: int | None, second: int | None, a: Entry, b: Entry) -> None:
    """Highest value first, None after any number, ties by lowest rank."""
    if first is None:
        assert second is None
        assert a.number < b.number
    elif second is not None:
        assert first > second or (first == second and a.number < b.number)


@given(entry_lists())
def test_long_is_ordered_by_comments(entries: list[Entry]) -> None:
    result = apply_filter(entries, Filter.LONG)
    for a, b in pairwise(result):
        assert_in_order(a.comments, b.comments, a, b)


@given(entry_lists())
def test_short_is_ordered_by_points(entries: list[Entry]) -> None:
    result = apply_filter(entries, Filter.SHORT)
    for a, b in pairwise(result):
        assert_in_order(a.points, b.points, a, b)
