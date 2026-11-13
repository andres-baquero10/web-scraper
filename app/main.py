"""Application factory: the one place where everything is wired together.

Run with ``uvicorn --factory app.main:create_app``.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routes import create_router
from app.cache import Clock, Fetcher, SnapshotCache, utc_now
from app.config import Settings
from app.models import Entry
from app.scraping.fetcher import HNFetcher
from app.scraping.parser import parse
from app.usage import UsageRepository

PageFetcher = Callable[[], Awaitable[str]]
"""Downloads the front page and returns its HTML; raises FetchError on failure."""


def _scraper(fetch_page: PageFetcher) -> Fetcher:
    """Turn a page fetcher into the entries fetcher the cache expects."""

    async def scrape() -> tuple[Entry, ...]:
        return parse(await fetch_page()).entries

    return scrape


def create_app(
    settings: Settings | None = None,
    fetcher: PageFetcher | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    http_client: httpx.AsyncClient | None = None
    if fetcher is None:
        http_client = httpx.AsyncClient()
        fetcher = HNFetcher(http_client, settings.fetch_timeout_seconds).fetch

    clock = clock or utc_now
    cache = SnapshotCache(_scraper(fetcher), settings.cache_ttl_seconds, clock)
    usage = UsageRepository(settings.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        usage.create_schema()
        yield
        if http_client is not None:
            await http_client.aclose()

    app = FastAPI(title="Hacker News scraper", lifespan=lifespan)
    app.include_router(create_router(cache, usage, clock))
    return app
