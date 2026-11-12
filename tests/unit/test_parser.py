from pathlib import Path

import pytest

from app.models import Entry
from app.scraping.parser import ParseResult, parse, parse_comments, parse_points

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def front_page() -> ParseResult:
    return parse((FIXTURES / "front_page.html").read_text(encoding="utf-8"))


def test_real_capture_parses_to_30_entries(front_page: ParseResult) -> None:
    assert len(front_page.entries) == 30


def test_first_entry_matches_values_read_from_fixture(front_page: ParseResult) -> None:
    assert front_page.entries[0] == Entry(
        number=1, id=50467087, title="Jensen Huang resigns", points=2177, comments=2183
    )


def test_last_entry_matches_values_read_from_fixture(front_page: ParseResult) -> None:
    assert front_page.entries[-1] == Entry(
        number=30,
        id=50467305,
        title="Electric ship batteries promise compact, cooler power",
        points=52,
        comments=57,
    )


def test_ranks_run_from_1_to_30(front_page: ParseResult) -> None:
    assert [e.number for e in front_page.entries] == list(range(1, 31))


def test_title_entities_are_decoded(front_page: ParseResult) -> None:
    titles = {e.title for e in front_page.entries}
    assert "Outlook is down, and so is Microsoft's status page" in titles
    assert not any("&#x" in t for t in titles)


def test_every_story_in_capture_has_points_and_comments(
    front_page: ParseResult,
) -> None:
    # The capture contains no job posts, so every entry has both values.
    assert all(e.points is not None for e in front_page.entries)
    assert all(e.comments is not None for e in front_page.entries)


def test_result_entries_are_a_tuple(front_page: ParseResult) -> None:
    assert isinstance(front_page.entries, tuple)


_STORY_ROW = (
    '<tr class="athing submission" id="{id}"><td class="title">'
    '<span class="rank">{rank}.</span></td><td class="title">'
    '<span class="titleline"><a href="https://example.com">Story {id}</a></span>'
    "</td></tr>"
)
_SUBTEXT_ROW = (
    '<tr><td colspan="2"></td><td class="subtext"><span class="subline">'
    '<span class="score" id="score_{id}">5 points</span> '
    '<span class="age"><a href="item?id={id}">1 hour ago</a></span> | '
    '<a href="item?id={id}">3&nbsp;comments</a></span></td></tr>'
)
_SPACER_ROW = '<tr class="spacer" style="height:5px"></tr>'


def _page(*rows: str) -> str:
    return "<table>" + "".join(rows) + "</table>"


def test_story_missing_its_subtext_row_is_an_error_not_a_job_post() -> None:
    # The next <tr> is the spacer: it has no score and no comments link, so
    # reading it would make the story look like a job post.
    html = _page(
        _STORY_ROW.format(id=1, rank=1),
        _SPACER_ROW,
        _STORY_ROW.format(id=2, rank=2),
        _SUBTEXT_ROW.format(id=2),
    )
    with pytest.raises(ValueError, match="missing subtext row"):
        parse(html)


def test_story_as_last_row_is_an_error() -> None:
    with pytest.raises(ValueError, match="missing subtext row"):
        parse(_page(_STORY_ROW.format(id=1, rank=1)))


def test_missing_id_is_a_value_error_not_a_key_error() -> None:
    story = _STORY_ROW.format(id=1, rank=1).replace(' id="1"', "", 1)
    with pytest.raises(ValueError, match="missing id"):
        parse(_page(story, _SUBTEXT_ROW.format(id=1)))


def test_job_post_subtext_row_is_still_accepted() -> None:
    job_subtext = (
        '<tr><td colspan="2"></td><td class="subtext">'
        '<span class="age"><a href="item?id=1">1 hour ago</a></span></td></tr>'
    )
    result = parse(_page(_STORY_ROW.format(id=1, rank=1), job_subtext))
    assert result.entries == (
        Entry(number=1, id=1, title="Story 1", points=None, comments=None),
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2183\xa0comments", 2183),
        ("1\xa0comment", 1),
        ("12 comments", 12),
        ("discuss", 0),
        ("6 hours ago", None),
        ("hide", None),
        ("", None),
    ],
)
def test_comment_link_is_recognised_by_its_text(
    text: str, expected: int | None
) -> None:
    assert parse_comments(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2177 points", 2177), ("1 point", 1), ("points", None), ("", None)],
)
def test_points_text(text: str, expected: int | None) -> None:
    assert parse_points(text) == expected
