import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ph_energy_data.collectors.base import FetchedDocument

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    pass


class HttpFetcher:
    """httpx fetcher that identifies itself, honours robots.txt and spaces out requests."""

    def __init__(self, user_agent: str, delay_seconds: float = 2.0) -> None:
        self._user_agent = user_agent
        self._delay = delay_seconds
        self._last_request = 0.0
        self._robots: dict[str, RobotFileParser] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True
        )

    def _wait(self) -> None:
        pause = self._last_request + self._delay - time.monotonic()
        if pause > 0:
            time.sleep(pause)
        self._last_request = time.monotonic()

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            self._wait()
            response = self._client.get(f"{origin}/robots.txt")
            # Some sites answer with an HTML page instead of a 404; treat that as no robots.txt.
            is_robots = response.status_code == 200 and response.headers.get(
                "content-type", ""
            ).startswith("text/plain")
            parser.parse(response.text.splitlines() if is_robots else [])
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(self._user_agent, url)

    def get(self, url: str) -> FetchedDocument:
        if not self._allowed(url):
            raise RobotsDisallowed(url)
        self._wait()
        log.info("GET %s", url)
        response = self._client.get(url)
        response.raise_for_status()
        return FetchedDocument(
            url=str(response.url),
            content=response.content,
            content_type=response.headers.get("content-type", "application/octet-stream")
            .split(";")[0]
            .strip(),
            fetched_at=datetime.now(UTC),
        )
