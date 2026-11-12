# Test fixtures

Saved HTML for the parser tests, so the suite never contacts Hacker News.

- `front_page.html`: an unmodified copy of the HN front page, captured on
  2026-11-12 with one logged-out request:

  ```sh
  curl -sS -A "hn-scraper-fixture-capture/0.1 (test fixture; single request)" \
    -o tests/fixtures/front_page.html https://news.ycombinator.com/
  ```

- `edge_cases.html`: hand-made, using the same row markup as the capture.
  It covers cases the capture happened not to include: a job post, a
  "discuss" entry, unusual titles, one malformed row and more than 30 rows.
  Each row is labelled with an HTML comment.

Recapture only when HN changes its markup, then update the expected values
in the parser tests.
