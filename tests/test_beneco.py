from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ph_energy_data.collectors.base import FetchedDocument
from ph_energy_data.collectors.beneco import MAX_MONTHS, collector
from ph_energy_data.collectors.registry import discover_collectors
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis
from tests.conftest import FIXTURES, FakeFetcher

URL = "https://www.beneco.com.ph/rates.php?q=month&monthyear="


def _fixture(name: str) -> bytes:
    return (FIXTURES / "beneco" / f"{name}.html").read_bytes()


def _document(name: str, month: str, content: bytes | None = None) -> FetchedDocument:
    return FetchedDocument(
        f"{URL}{month}", content or _fixture(name), "text/html", datetime.now(UTC)
    )


@pytest.mark.parametrize(
    ("name", "month", "period", "total", "generation"),
    [
        ("2026-09", "September+2026", "2026-09", "11.8038", "6.7579"),
        ("2021-06", "June+2021", "2021-06", "8.4918", "4.4363"),
        ("2019-05", "May+2019", "2019-05", "9.2940", "5.1950"),
    ],
)
def test_extracts_residential_total_and_generation(
    name: str, month: str, period: str, total: str, generation: str
) -> None:
    (rate,) = collector.extract(_document(name, month))
    assert (rate.period, rate.rate_per_kwh) == (period, Decimal(total))
    assert rate.generation_charge_per_kwh == Decimal(generation)
    assert rate.rate_basis is RateBasis.PUBLISHED_TOTAL
    assert rate.extraction_method is ExtractionMethod.HTML_PARSER


def test_unpublished_month_has_no_rates() -> None:
    assert collector.extract(_document("2026-10-unpublished", "October+2026")) == []


def test_misaligned_table_is_rejected() -> None:
    content = _fixture("2026-09").replace(b"11.8038", b"11.9038")
    with pytest.raises(ValueError, match="components sum"):
        collector.extract(_document("2026-09", "September+2026", content))


def test_page_for_another_month_is_rejected() -> None:
    with pytest.raises(ValueError, match="returned"):
        collector.extract(_document("2026-09", "August+2026"))


def test_unrecognised_layout_raises() -> None:
    with pytest.raises(ValueError, match="selector not found"):
        collector.extract(_document("2026-09", "September+2026", b"<html>maintenance</html>"))


def test_discovers_newest_months_first() -> None:
    urls = collector.discover(FakeFetcher(_fixture("selector")))
    assert len(urls) == MAX_MONTHS
    assert urls[0] == f"{URL}October+2026"
    assert urls[1] == f"{URL}September+2026"


def test_registry_finds_beneco() -> None:
    assert "beneco" in discover_collectors()
