"""Turn the HN front-page HTML into entries"""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from app.models import Entry
from app.scraping import selectors

# \s also matches the non-breaking space HN puts in "123&nbsp;comments".
_POINTS_RE = re.compile(r"(\d+)\s+points?")
_COMMENTS_RE = re.compile(r"(\d+)\s+comments?")
_DISCUSS = "discuss"


@dataclass(frozen=True)
class ParseResult:
    """Entries parsed from one page, in page order."""

    entries: tuple[Entry, ...]


def parse(html: str) -> ParseResult:
    """Parse every entry row on the front page."""
    soup = BeautifulSoup(html, "html.parser")
    entries = tuple(_parse_row(row) for row in soup.select(selectors.ROW))
    return ParseResult(entries=entries)


def parse_points(text: str) -> int | None:
    """``"N point(s)"`` -> N; anything else -> None."""
    match = _POINTS_RE.fullmatch(text.strip())
    return int(match.group(1)) if match else None


def parse_comments(text: str) -> int | None:
    """``"N comment(s)"`` -> N, ``"discuss"`` -> 0; anything else -> None."""
    text = text.strip()
    if text == _DISCUSS:
        return 0
    match = _COMMENTS_RE.fullmatch(text)
    return int(match.group(1)) if match else None


def _parse_row(row: Tag) -> Entry:
    rank = _required(row.select_one(selectors.RANK), "rank")
    title = _required(row.select_one(selectors.TITLE_LINK), "title")
    subtext = _subtext_row(row)
    raw_id = row.get("id")
    if raw_id is None:
        raise ValueError("missing id")

    score = subtext.select_one(selectors.SCORE)
    points = parse_points(score.get_text()) if score else None

    return Entry(
        number=int(rank.get_text().strip().rstrip(".")),
        id=int(str(raw_id)),
        title=title.get_text(),
        points=points,
        comments=_find_comments(subtext),
    )


def _subtext_row(row: Tag) -> Tag:
    """The element right after ``row``, which must be a subtext row.

    Only the immediate next element is accepted. Searching further would
    reach the spacer row or the next entry and misread the entry.
    """
    subtext = row.find_next_sibling()
    if (
        not isinstance(subtext, Tag)
        or subtext.name != selectors.SUBTEXT_ROW
        or subtext.select_one(selectors.SUBTEXT_CELL) is None
    ):
        raise ValueError("missing subtext row")
    return subtext


def _find_comments(subtext: Tag) -> int | None:
    for link in subtext.select(selectors.SUBTEXT_ITEM_LINKS):
        count = parse_comments(link.get_text())
        if count is not None:
            return count
    return None


def _required(tag: Tag | None, field: str) -> Tag:
    if tag is None:
        raise ValueError(f"missing {field}")
    return tag
