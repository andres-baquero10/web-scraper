# Hacker News Scraper

A small HTTP service that scrapes the first 30 entries from the
[Hacker News](https://news.ycombinator.com/) front page and serves them through
two filters:

- **Long titles** (more than five words), ordered by number of comments.
- **Short titles** (five words or fewer), ordered by points.

Scraped entries are cached in memory, so Hacker News is contacted at most once a
minute however many requests arrive. Every request is recorded in a SQLite
usage log that you can read through the API or query directly.

Built with Python 3.12, FastAPI, httpx and BeautifulSoup.

- [Quickstart](#quickstart)
- [API](#api)
- [How the brief was interpreted](#how-the-brief-was-interpreted)
- [Key design decisions](#key-design-decisions)
- [Architecture](#architecture)
- [Testing](#testing)
- [Inspecting usage data](#inspecting-usage-data)
- [Configuration](#configuration)
- [Limitations and production notes](#limitations-and-production-notes)

## Quickstart

Requires Python 3.12+. There are no external services to set up.

With [uv](https://docs.astral.sh/uv/) (recommended, uses the committed lockfile):

```sh
uv sync --extra dev                                         # install
uv run uvicorn --factory app.main:create_app --reload       # run the service
uv run pytest                                               # run the tests
```

With pip:

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
uvicorn --factory app.main:create_app --reload
pytest
```

`--factory` is needed because `create_app()` builds the app (see
[Architecture](#architecture)). `--reload` restarts the server when code
changes, which is handy while reviewing; each restart also empties the cache.

Then open **http://localhost:8000/docs** to try the endpoints interactively, or:

```sh
curl 'http://localhost:8000/entries?filter=long'
curl 'http://localhost:8000/entries?filter=short'
curl 'http://localhost:8000/usage?limit=5'
```

## API

### `GET /entries?filter=long|short|all`

| `filter` | Selects | Ordered by |
|---|---|---|
| `long` | Titles with more than 5 words | Comments, highest first |
| `short` | Titles with 5 or fewer words | Points, highest first |
| `all` (default) | Every entry | Front-page rank |

Any other value gets a `422`.

```json
{
  "fetched_at": "2026-11-13T15:04:05.123456Z",
  "stale": false,
  "complete": true,
  "entries": [
    {
      "number": 19,
      "id": 50465352,
      "title": "Why Writing Correct Software Is Hard",
      "points": 315,
      "comments": 140
    },
    {
      "number": 29,
      "id": 50425017,
      "title": "A live tree of systemd jobs on the boot console",
      "points": 320,
      "comments": 120
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `fetched_at` | When this data was scraped from HN (UTC) |
| `stale` | `true` if the last refresh failed and older data is being served |
| `complete` | `false` if the scrape found fewer than 30 entries |
| `number` | The rank shown on the front page (`1`–`30`) |
| `id` | The HN item id (`https://news.ycombinator.com/item?id=<id>`) |
| `points`, `comments` | `null` for job posts, which have neither |

Every response, including errors, carries an **`X-Request-ID`** header. It is
the ID of that request's usage record, so `GET /usage?request_id=<id>` shows
exactly how the request was served.

| Situation | Response |
|---|---|
| Data in cache is fresh | `200` |
| Cache expired and refresh succeeded | `200` with new data |
| Refresh parsed only 1–29 entries | `200`, `complete: false` |
| Refresh failed, older data is cached | `200`, `stale: true` |
| Refresh failed, nothing cached yet | `503` with a short message |
| Unexpected error (a bug) | `500 Internal server error`, still recorded in the usage log |

### `GET /usage?limit=&offset=&request_id=`

Usage records for `/entries` requests, newest first.

- `limit`: 1–500, default 50.
- `offset`: 0–1,000,000, default 0.
- `request_id`: optional; returns only the record for that `X-Request-ID`.

Out-of-range values get a `422`. Calls to `/usage` itself are not recorded.

```json
[
  {
    "id": 2,
    "request_id": "df54edbb-0977-4d33-a361-832bc498ef90",
    "requested_at": "2026-11-13T15:04:05.123456Z",
    "filter": "short",
    "result_count": 8,
    "cache_status": "hit",
    "data_fetched_at": "2026-11-13T15:04:05.123456Z",
    "latency_ms": 0.118,
    "status_code": 200,
    "error": null
  }
]
```

## How the brief was interpreted

The brief leaves a few things open. These are the readings I chose.

### Counting words

> "Consider only the spaced words and exclude any symbols. 'This is - a
> self-explained example' should be counted as having 5 words."

**Rule:** split the title on whitespace. A token is a word if it contains at
least one Unicode letter or digit.

Of the obvious readings, this is the only one that gives the example its 5:

| Reading | `This is - a self-explained example` |
|---|---|
| Split on spaces, count every token | 6 (counts `-`) |
| Split on spaces *and* symbols | 6 (splits `self-explained`) |
| Count only tokens made purely of letters and digits | 4 (drops `self-explained`) |
| **Split on spaces, keep tokens with a letter or digit** | **5** ✓ |

| Token | Words | Why |
|---|---|---|
| `HN:`, `C++`, `don't`, `$100`, `3.5`, `café`, `Москва` | 1 each | Contains a letter or digit |
| `-`, `—`, `&`, `...`, `___`, `🚀` | 0 each | Symbols only |

The check uses `str.isalnum()` rather than the regex `\w`, because `\w` treats
`_` as a letter and would count `___` as a word.

### Filters

- **"More than five" and "fewer than or equal to five"** split the entries in
  two. Every entry appears in exactly one of `long` and `short`, which a
  property-based test checks.
- **Both orderings are highest first.** "Ordered by the number of comments
  first" means comments is the sort key.
- **Ties are broken by front-page rank**, so the output is deterministic.
- **Job posts are kept.** They are part of the first 30 entries, but have no
  points or comments. They return `null` for both (a fake `0` would hide the
  missing data) and sort last.
- **"discuss" means 0 comments.** HN shows it instead of a count on stories
  nobody has commented on yet.
- **`all`** returns the unfiltered 30 in rank order. It isn't in the brief, but
  it shows what the filters start from.

### `number` is the front-page rank, so filtered results have gaps

`number` is the rank HN displays (`1.`–`30.`). Filtered results keep it, so a
`long` response might show `19, 29, 20, …`. That is intended: renumbering would
lose where the story sits on the front page. Each entry also carries HN's item
`id`, which is stable across scrapes and links back to the source.

### Scraping HTML instead of the official API

HN has an official [Firebase API](https://github.com/HackerNews/API) that would
be more stable than parsing HTML. I didn't use it because the brief asks for
"scraping techniques". The scraper identifies itself with a descriptive
`User-Agent`.

## Key design decisions

### 1. Cache the 30 entries, and contact HN at most once per TTL

The 30 scraped entries are kept in memory for a TTL: 60 seconds by default,
configurable, never below 30.

**Why:** HN's `robots.txt` asks crawlers to wait 30 seconds between
requests, and HN throttles clients that don't. Without a cache, every request
to this service would become a request to HN. Under any real traffic we would
break that rule within seconds and get blocked. That's why the TTL can't go
below 30 s.

The cost is small: the front page changes over minutes, each response says
how old its data is (`fetched_at`), and cache hits are faster because they
skip the round trip to HN.

The cache stores the raw entries, not filtered results. One cache entry serves
every filter, and the filters always agree with each other.

### 2. The TTL is timed from the last *attempt*, not the last success

**Why:** it keeps the 30-second rule even when things go wrong. If the TTL
were timed from the last success, a failed fetch would leave the cache
expired, so the next request would try HN again, and the one after that.
While HN is down or throttling us, we would hit it on every request, which is
exactly when we should back off, and getting throttled would keep us
throttled. Timed from the last attempt, a failure waits a full TTL like any
other refresh. In the meantime, requests get the old data (see
[decision 4](#4-prefer-old-data-over-an-error-and-say-so)). This one rule
replaces retries and failure backoff.

### 3. Refresh only when a request needs it, and only one at a time

There is no background job and no scrape at startup. The first request after
the TTL expires triggers the refresh.

Only one refresh runs at a time:

- The request that starts it waits for it (`cache_status: miss`).
- Requests arriving meanwhile are served the current data immediately
  (`hit`). They don't wait, and they don't trigger a second fetch.
- Only when nothing is cached yet (just after startup) do they wait for that
  same refresh and share its result.

**Why:** without this, every request arriving just after expiry would fetch
from HN separately. With it, one request per TTL waits for the fetch and
everyone else gets a cache hit. Refreshing on demand also means the service
never contacts HN when nobody is using it.

### 4. Prefer old data over an error, and say so

When a refresh fails, the service keeps serving the older data with
`stale: true`, and returns a `503` only when nothing is cached yet. A partial
scrape is served with `complete: false`. Every case is listed under
[API](#api).

A scrape with 0 entries counts as a failure. It means an error page or a
layout change, not an empty front page, so a `200 []` would be a lie.

**Why:** old data with its age visible is more useful than an error, and the
`stale` and `complete` flags make the gaps visible instead of hiding them.

### 5. Parse each row on its own; keep every selector in one module

A row that fails to parse is skipped and logged with the reason; the other 29
are still returned. All CSS selectors live in
[`app/scraping/selectors.py`](app/scraping/selectors.py).

**Why:** HN's markup has no stability guarantee. One odd row shouldn't throw
away the whole page, and when the markup changes, the fix is one file.

Two parsing details that prevent subtle bugs:

- The comments link is found by its **text** (`"N comments"` or `"discuss"`),
  not its position. The age link (`"3 hours ago"`) points to the same URL, and
  on a job post it's the only link there.
- An entry's details row must be the row *immediately* after it. Otherwise a
  story with a missing details row would read the spacer row, find no score,
  and pass as a job post.

### 6. Usage tracking in SQLite, one row per `/entries` request

The brief requires the request timestamp and the filter. Each record also
captures how the crawler behaved:

| Field | Why it's there |
|---|---|
| `request_id` | Matches the `X-Request-ID` response header, so a response can be traced to its record |
| `requested_at` | Required by the brief (UTC) |
| `filter` | Required by the brief |
| `result_count` | How many entries were returned; also exposes short scrapes |
| `cache_status` | `hit`, `miss`, `stale` or `empty` (no data served: a 503 or 500). Gives the cache hit rate and outage count |
| `data_fetched_at` | How old the served data was |
| `latency_ms` | Time spent handling the request, to microsecond resolution (cache hits are well under 1 ms) |
| `status_code`, `error` | What went wrong, if anything |

**Why SQLite:** it's built into Python, needs no setup, and is a single file a
reviewer can open with `sqlite3`.

Rules around it:

- **Tracking never breaks the service.** If saving a record fails, the error is
  logged and the request still succeeds.
- **The write doesn't block the server.** `sqlite3` is synchronous, so it runs
  in a worker thread (`asyncio.to_thread`).
- **Errors are recorded too.** A 503 or an unexpected 500 still writes a row,
  and the client still gets a request ID to look it up with.
- **No personal data.** No IP addresses or user agents are stored.
- **Only `/entries` is tracked.** Logging calls to `/usage` would fill the log
  with requests to read the log.

### 7. One endpoint with a `filter` parameter

`GET /entries?filter=long|short|all` instead of one path per filter.

**Why:** one handler, no repetition. FastAPI validates the enum and rejects
typos with a `422` instead of silently falling back, and the value maps
directly to the usage record's `filter` field. The response holds only the
data and its freshness; it doesn't echo the filter or a count, which the
client already has.

### 8. Few dependencies

| Package | Why |
|---|---|
| `fastapi` + `uvicorn` | HTTP API with validation and an interactive `/docs` page for free |
| `httpx` | Async HTTP client; FastAPI's test client needs it anyway |
| `beautifulsoup4` | A readable parser, on Python's built-in `html.parser` (no `lxml`) |
| `pytest`, `hypothesis`, `ruff`, `mypy` | Dev only: tests, property-based tests, lint, strict types |

Python's standard library covers the rest (`sqlite3`, `asyncio`, `dataclasses`,
`uuid`).

### 9. Titles are untrusted input

Titles are written by strangers on the internet.

- Database writes use parameterized queries (no SQL injection).
- Titles are logged with `repr()`, so control characters can't forge log lines.
- The API only returns JSON, so titles are never rendered as HTML.

## Architecture

```
app/
  main.py            create_app(): builds and wires everything
  config.py          Settings from environment variables; enforces TTL ≥ 30 s
  models.py          Entry and Snapshot (frozen dataclasses)
  words.py           count_words()                                (pure)
  filters.py         Filter enum + apply_filter()                 (pure)
  scraping/
    selectors.py     every CSS selector used on the HN page
    parser.py        parse(html) -> entries, row by row           (pure)
    fetcher.py       HNFetcher: one GET to HN, User-Agent
  cache.py           SnapshotCache: TTL, single-flight refresh, stale on failure
  usage.py           UsageRepository: SQLite reads and writes
  api/
    routes.py        GET /entries, GET /usage
    schemas.py       response models
tests/
  fixtures/          saved HN HTML
  unit/              one test module per app module
  integration/       the HTTP API through create_app() with fakes
```

## Testing

```sh
uv run pytest          # 149 tests, about 2 seconds
uv run ruff check .    # lint
uv run mypy            # strict type checking of app/ and tests/
```

- **No network.** The parser runs against saved HTML in
  [`tests/fixtures/`](tests/fixtures/): a real, unmodified front-page capture
  and a hand-made page of edge cases.
- **No sleeping.** Time and the HN fetcher are injected, so cache expiry and
  concurrent refreshes are tested deterministically.
- **Real SQLite.** Usage tests use a real database in a temporary file.
- **Property-based tests.** [Hypothesis](https://hypothesis.readthedocs.io/)
  generates titles nobody would write by hand (non-breaking spaces, combining
  characters, symbol-only strings) to check word counting and the filters.

## Inspecting usage data

Through the API: `GET /usage`, or `GET /usage?request_id=<X-Request-ID>` for one
request.

All timestamps are UTC, in ISO-8601 format.

## Configuration

Settings come from environment variables:

| Variable | Default | Notes |
|---|---|---|
| `HN_CACHE_TTL_SECONDS` | `60` | Startup fails if below `30` (HN's crawl delay) |
| `HN_FETCH_TIMEOUT_SECONDS` | `5` | Timeout for the request to HN |
| `HN_DB_PATH` | `usage.db` | SQLite file for usage records, created on startup |

```sh
HN_CACHE_TTL_SECONDS=120 uv run uvicorn --factory app.main:create_app
```

## Limitations and production notes

Known limits of this version, and what I'd change before running it in production.

- **Single process.** The cache lives in memory, so N workers would each keep
  their own cache and fetch from HN N times per TTL, breaking the crawl delay.
  Scaling out means moving the cache to a shared store such as Redis, with a
  distributed lock for the refresh and possibly a background refresher.
- **`/usage` has no authentication.** It's acceptable here because no personal
  data is stored, but it would need authentication before a public deployment.
- **Usage records are kept forever, and `/usage` scans the whole table.** Each
  row takes about 190 bytes including its index, so a million requests is
  roughly 200 MB. Every `/usage` call currently scans and sorts the full table.
  Production would need a retention policy, an index on `requested_at`, and
  paging that continues from the last record seen, since `OFFSET` re-reads
  every skipped row.
- **Usage records can be lost under heavy load.** SQLite handles one write at
  a time, so with many requests arriving together some writes could fail.
  Because tracking never breaks a request, those records would be dropped with
  only a log line, and the usage log would undercount. A database built for
  concurrent writes, or batching the writes, would fix this.
- **Languages without spaces count as one word per run.** A Chinese or Japanese
  title with no spaces counts as 1 word. This follows "consider only the
  spaced words"; real word segmentation is out of scope.
- **HTML scraping is fragile by nature.** Most markup changes are loud: rows
  fail to parse and are logged, giving `complete: false`, or `stale` data or a
  `503` if every row fails. Two are silent: if HN renamed the score element or
  reworded the comments link, stories would parse with `points: null` or
  `comments: null`, because job posts legitimately have neither. A check that
  flags rows with only one of the two would catch this.
