from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.collectors.base import FetchedDocument
from ph_energy_data.collectors.meralco import LISTING_URL, collector
from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import ExtractionMethod, RateStatus, RunStatus
from ph_energy_data.services.pipeline import run_collector
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.models import RateObservation
from tests.conftest import FIXTURES, FakeFetcher, RoutingFetcher

BASE = "https://meralcomain.s3.ap-southeast-1.amazonaws.com"
OCT = f"{BASE}/2026-10/10-2026_residential_bills.pdf"
SEP = f"{BASE}/2026-09/09-2026_residential_bills.pdf"
PDF = (FIXTURES / "meralco" / "residential_bills_2026-10.pdf").read_bytes()
LISTING = (FIXTURES / "meralco" / "listing.html").read_bytes()


def _document(url: str = OCT, content: bytes = PDF) -> FetchedDocument:
    return FetchedDocument(url, content, "application/pdf", datetime.now(UTC))


def test_extracts_overall_rate_and_generation() -> None:
    (rate,) = collector.extract(_document())
    assert rate.period == "2026-10"
    assert rate.rate_per_kwh == Decimal("15.0615")
    assert rate.generation_charge_per_kwh == Decimal("10.2005")
    assert rate.extraction_method is ExtractionMethod.PDF_PARSER


def test_period_must_match_url() -> None:
    with pytest.raises(ValueError, match="URL says"):
        collector.extract(_document(url=SEP))


def test_unreadable_pdf_raises() -> None:
    with pytest.raises(ValueError, match="unreadable"):
        collector.extract(_document(content=b"not a pdf"))


def test_discovers_bill_links_from_listing() -> None:
    urls = collector.discover(FakeFetcher(LISTING))
    assert OCT in urls
    assert len(urls) == len(set(urls)) == 4
    assert all("residential_bills" in u for u in urls)


def test_bad_document_does_not_block_others(
    session_factory: sessionmaker[Session], archive: LocalArchive
) -> None:
    fetcher = RoutingFetcher(
        {LISTING_URL: LISTING, OCT: PDF, SEP: b"<html>not a pdf</html>"}, "application/pdf"
    )
    # Listing pages are HTML; the routing fetcher serves one content type for brevity.
    run = run_collector(
        collector,
        session_factory=session_factory,
        fetcher=fetcher,
        archive=archive,
        settings=Settings(),
    )
    assert run.status is RunStatus.FAILED
    assert "09-2026_residential_bills.pdf" in (run.error or "")
    assert run.rates_created == 1
    with session_factory() as session:
        (stored,) = session.scalars(select(RateObservation)).all()
    assert (stored.period, stored.status) == ("2026-10", RateStatus.PUBLISHED)


@pytest.mark.parametrize(
    ("name", "url_month", "period", "rate", "generation"),
    [
        # Final digit of the printed rate is split off in the PDF text ("1 3.1145").
        ("2025-12", "2025-12/12-2025", "2025-12", "13.1145", None),
        # Heading is "Jul-26" and several numbers contain stray spaces.
        ("2026-07", "2026-07/07-2026", "2026-07", "14.8261", "9.2504"),
    ],
)
def test_layout_variants(
    name: str, url_month: str, period: str, rate: str, generation: str | None
) -> None:
    content = (FIXTURES / "meralco" / f"residential_bills_{name}.pdf").read_bytes()
    url = f"{BASE}/{url_month}_residential_bills.pdf"
    (extracted,) = collector.extract(_document(url, content))
    assert (extracted.period, extracted.rate_per_kwh) == (period, Decimal(rate))
    if generation:
        assert extracted.generation_charge_per_kwh == Decimal(generation)
