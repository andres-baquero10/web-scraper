from collections.abc import Callable

import httpx
import pytest

from app.scraping.fetcher import HN_URL, USER_AGENT, FetchError, HNFetcher

Handler = Callable[[httpx.Request], httpx.Response]


def _fetcher(handler: Handler) -> HNFetcher:
    return HNFetcher(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.anyio
async def test_200_returns_the_body_of_a_get_to_hn() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="<html>front page</html>")

    assert await _fetcher(handler).fetch() == "<html>front page</html>"
    assert [(r.method, str(r.url)) for r in requests] == [("GET", HN_URL)]


@pytest.mark.anyio
async def test_sends_user_agent_and_timeout() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await HNFetcher(client, timeout=2.0).fetch()

    (request,) = requests
    assert request.headers["User-Agent"] == USER_AGENT
    assert request.extensions["timeout"]["read"] == 2.0


def _raise(exc: type[httpx.TransportError]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc("boom", request=request)

    return handler


@pytest.mark.anyio
@pytest.mark.parametrize(
    "handler",
    [
        _raise(httpx.ReadTimeout),
        _raise(httpx.ConnectError),
        lambda request: httpx.Response(503),
    ],
    ids=["timeout", "connection-error", "non-2xx"],
)
async def test_failures_raise_fetch_error(handler: Handler) -> None:
    with pytest.raises(FetchError) as info:
        await _fetcher(handler).fetch()
    assert isinstance(info.value.__cause__, httpx.HTTPError)
