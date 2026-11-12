"""Download the Hacker News front page."""

import httpx

HN_URL = "https://news.ycombinator.com/"
USER_AGENT = "hn-scraper/0.1 (front-page scraper; one request per cache TTL)"


class FetchError(Exception):
    """The front page could not be downloaded, whatever the cause."""


class HNFetcher:
    """Fetches the HN front page. No retries: the cache allows one attempt per TTL."""

    def __init__(self, client: httpx.AsyncClient, timeout: float = 5.0) -> None:
        self._client = client
        self._timeout = timeout

    async def fetch(self) -> str:
        try:
            response = await self._client.get(
                HN_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FetchError(f"HN returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise FetchError(f"HN request failed: {type(exc).__name__}") from exc
        return response.text
