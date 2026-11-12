"""Every CSS selector used on the Hacker News front page.

Hacker News offers no stable markup contract. Centralizing selectors here keeps
any markup change to a single-file update.

Each entry spans two table rows: the ``tr.athing`` row (rank, title, item id)
and the ``<tr>`` immediately after it, whose ``td.subtext`` cell holds the
score and the links below the title.
"""

ROW = "tr.athing"
"""One per entry; its ``id`` attribute is the HN item id."""

SUBTEXT_ROW = "tr"
"""Tag of the row right after ``ROW``, found as its next sibling."""

SUBTEXT_CELL = "td.subtext"
"""Must be inside ``SUBTEXT_ROW``; otherwise that row isn't a subtext row.

Without this check, an entry whose subtext row is missing would read the
spacer row after it, find no score and no comments link, and pass as a job
post.
"""

RANK = "span.rank"
"""Displayed rank, e.g. ``"1."``."""

TITLE_LINK = "span.titleline > a"
"""The title link only, not the ``(site.com)`` suffix next to it."""

SCORE = "span.score"
"""``"N points"``. Absent on job posts."""

SUBTEXT_ITEM_LINKS = 'td.subtext a[href^="item?id="]'
"""Candidate comments links in the subtext row.

The comments link must be picked by its text (``"N comments"``, where HN puts
``&nbsp;`` between the number and the word, or ``"discuss"``), never by
position: the age link (``"3 hours ago"``) also points to ``item?id=``, and on
a job post it is the only such link.
"""
