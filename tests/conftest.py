from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ph_energy_data.collectors.base import (
    Collector,
    Discovery,
    ExtractionError,
    FetchedDocument,
    Fetcher,
    FetchError,
    ReferenceTotals,
)
from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, UtilityType
from ph_energy_data.domain.models import ExtractedRate, Utility
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.models import Base

FIXTURES = Path(__file__).parent / "fixtures"


class FakeFetcher:
    """Serves canned bytes; tests never touch the network."""

    def __init__(self, content: bytes, content_type: str = "text/html") -> None:
        self.content = content
        self.content_type = content_type

    def get(self, url: str) -> FetchedDocument:
        return FetchedDocument(url, self.content, self.content_type, datetime.now(UTC))


STUB_PAGE = b"""STUB
2025-10 7.55
2025-11 8.71
2025-12 8.36
2026-01 7.70
2026-02 8.13
2026-03 8.17
2026-04 9.60
2026-05 9.70
2026-06 11.65
2026-07 12.29
2026-08 12.61
2026-09 11.80
"""


class StubCollector(Collector):
    """Parses `YYYY-MM value` lines under a STUB header; any other document is a layout error."""

    utility = Utility(id="stub", name="Stub Cooperative", type=UtilityType.ELECTRIC_COOPERATIVE)

    def discover(self, fetcher: Fetcher) -> Discovery:
        return Discovery(["https://stub.test/rates"])

    def extract(
        self, document: FetchedDocument, reference_totals: ReferenceTotals
    ) -> list[ExtractedRate]:
        lines = document.content.decode().splitlines()
        if not lines or lines[0] != "STUB":
            raise ExtractionError("table not found")
        return [
            ExtractedRate(
                period=period,
                rate_per_kwh=Decimal(value),
                rate_basis=RateBasis.PUBLISHED_TOTAL,
                extraction_method=ExtractionMethod.HTML_PARSER,
                extractor_version="stub-1",
            )
            for period, value in (line.split() for line in lines[1:] if not line.startswith("#"))
        ]


class RoutingFetcher:
    """Serves a canned (content, content type) per URL prefix; unlisted URLs fail to download."""

    def __init__(self, routes: dict[str, tuple[bytes, str]]) -> None:
        self.routes = routes

    def get(self, url: str) -> FetchedDocument:
        for prefix, (content, content_type) in self.routes.items():
            if url.startswith(prefix):
                return FetchedDocument(url, content, content_type, datetime.now(UTC))
        raise FetchError(url)


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    # SQLite ignores foreign keys by default; Postgres does not.
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(engine)
    engine.dispose()


@pytest.fixture
def archive(tmp_path: Path) -> LocalArchive:
    return LocalArchive(tmp_path / "archive")
