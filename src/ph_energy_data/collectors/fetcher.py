import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from ph_energy_data.collectors.base import FetchedDocument, FetchError

log = structlog.get_logger(__name__)


class RobotsDisallowed(FetchError):
    """robots.txt forbids fetching the URL."""


class HttpFetcher:
    """httpx fetcher that identifies itself, honours robots.txt and spaces out requests."""

    def __init__(
        self,
        user_agent: str,
        delay_seconds: float = 2.0,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._user_agent = user_agent
        self._delay_seconds = delay_seconds
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self._robots: dict[str, RobotFileParser] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=30,
            follow_redirects=True,
            transport=transport,
        )

    def _wait_for_turn(self) -> None:
        if self._last_request_at is not None:
            remaining = self._last_request_at + self._delay_seconds - self._clock()
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def _load_robots(self, origin: str) -> RobotFileParser:
        self._wait_for_turn()
        try:
            response = self._client.get(f"{origin}/robots.txt")
        except httpx.HTTPError as exc:
            raise FetchError(f"robots.txt unreachable for {origin}: {exc}") from exc
        if response.status_code >= 500:
            raise FetchError(f"robots.txt for {origin} returned {response.status_code}")
        # Some sites answer a missing robots.txt with an HTML page instead of a 404.
        is_robots_file = response.status_code == 200 and response.headers.get(
            "content-type", ""
        ).startswith("text/plain")
        parser = RobotFileParser()
        parser.parse(response.text.splitlines() if is_robots_file else [])
        return parser

    def _is_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            self._robots[origin] = self._load_robots(origin)
        return self._robots[origin].can_fetch(self._user_agent, url)

    def get(self, url: str) -> FetchedDocument:
        if not self._is_allowed(url):
            raise RobotsDisallowed(url)
        self._wait_for_turn()
        log.info("fetch", url=url)
        try:
            response = self._client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"{url}: {exc}") from exc
        return FetchedDocument(
            url=str(response.url),
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream")
            .split(";")[0]
            .strip(),
            fetched_at=datetime.now(UTC),
        )
