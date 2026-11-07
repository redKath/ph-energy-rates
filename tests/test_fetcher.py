from collections.abc import Callable

import httpx
import pytest

from ph_energy_data.collectors.base import FetchError
from ph_energy_data.collectors.fetcher import HttpFetcher, RobotsDisallowed

USER_AGENT = "test-agent"
ROBOTS_TEXT = "User-agent: *\nDisallow: /private\n"


class FakeClock:
    """Time that only moves when the fetcher sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def read(self) -> float:
        return self.now


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response], clock: FakeClock | None = None
) -> HttpFetcher:
    clock = clock or FakeClock()
    return HttpFetcher(
        USER_AGENT,
        delay_seconds=2.0,
        transport=httpx.MockTransport(handler),
        sleep=clock.sleep,
        clock=clock.read,
    )


def _site(
    robots: httpx.Response, page: httpx.Response | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return robots
        return page or httpx.Response(
            200, text="<html></html>", headers={"content-type": "text/html"}
        )

    return handler


def _robots_file(text: str = ROBOTS_TEXT) -> httpx.Response:
    return httpx.Response(200, text=text, headers={"content-type": "text/plain"})


def test_returns_document_with_bare_content_type() -> None:
    page = httpx.Response(200, content=b"hi", headers={"content-type": "text/html; charset=utf-8"})
    document = _fetcher(_site(_robots_file(), page)).get("https://a.test/rates")
    assert (document.url, document.content, document.content_type) == (
        "https://a.test/rates",
        b"hi",
        "text/html",
    )


def test_path_disallowed_by_robots_is_not_fetched() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return _robots_file() if request.url.path == "/robots.txt" else httpx.Response(200)

    with pytest.raises(RobotsDisallowed):
        _fetcher(handler).get("https://a.test/private/rates")
    assert requested == ["/robots.txt"]


@pytest.mark.parametrize(
    "robots",
    [
        httpx.Response(404),
        httpx.Response(200, text="<html>not found</html>", headers={"content-type": "text/html"}),
    ],
)
def test_missing_robots_file_allows_fetching(robots: httpx.Response) -> None:
    document = _fetcher(_site(robots)).get("https://a.test/private/rates")
    assert document.content_type == "text/html"


def test_server_error_on_robots_blocks_fetching() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(503)

    with pytest.raises(FetchError, match=r"robots\.txt"):
        _fetcher(handler).get("https://a.test/rates")
    assert requested == ["/robots.txt"]


def test_unreachable_robots_blocks_fetching() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(FetchError, match="unreachable"):
        _fetcher(handler).get("https://a.test/rates")


def test_http_error_status_becomes_fetch_error() -> None:
    fetcher = _fetcher(_site(_robots_file(), httpx.Response(404)))
    with pytest.raises(FetchError, match="404"):
        fetcher.get("https://a.test/rates")


def test_requests_are_spaced_and_robots_is_read_once() -> None:
    clock = FakeClock()
    robots_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            robots_requests.append(request.url.path)
            return _robots_file()
        return httpx.Response(200, headers={"content-type": "text/html"})

    fetcher = _fetcher(handler, clock)
    fetcher.get("https://a.test/one")
    fetcher.get("https://a.test/two")
    assert robots_requests == ["/robots.txt"]
    # Three requests (robots, one, two) with a 2 second delay between each pair.
    assert clock.sleeps == [2.0, 2.0]
