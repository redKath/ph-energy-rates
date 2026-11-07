from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ph_energy_data.collectors.base import ExtractionError, FetchedDocument
from ph_energy_data.collectors.beneco import MAX_MONTHS, BenecoCollector
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis
from tests.conftest import FIXTURES, FakeFetcher

URL = "https://www.beneco.com.ph/rates.php?q=month&monthyear="
SEPTEMBER = "September+2026"
collector = BenecoCollector()


def _fixture(name: str) -> bytes:
    return (FIXTURES / "beneco" / f"{name}.html").read_bytes()


def _document(name: str, month: str, content: bytes | None = None) -> FetchedDocument:
    return FetchedDocument(
        f"{URL}{month}", content or _fixture(name), "text/html", datetime.now(UTC)
    )


def _without_last_residential_cell(content: bytes) -> bytes:
    row_start = content.index(b"<td>Residential</td>")
    row_end = content.index(b"</tr>", row_start)
    last_cell_start = content.rindex(b"<td>", row_start, row_end)
    return content[:last_cell_start] + content[row_end:]


@pytest.mark.parametrize(
    ("name", "month", "period", "total", "generation"),
    [
        ("2026-09", SEPTEMBER, "2026-09", "11.8038", "6.7579"),
        ("2021-06", "June+2021", "2021-06", "8.4918", "4.4363"),
        ("2019-05", "May+2019", "2019-05", "9.2940", "5.1950"),
    ],
)
def test_extracts_residential_total_and_generation(
    name: str, month: str, period: str, total: str, generation: str
) -> None:
    (rate,) = collector.extract(_document(name, month), {})
    assert (rate.period, rate.rate_per_kwh) == (period, Decimal(total))
    assert rate.generation_charge_per_kwh == Decimal(generation)
    assert rate.rate_basis is RateBasis.PUBLISHED_TOTAL
    assert rate.extraction_method is ExtractionMethod.HTML_PARSER


def test_unpublished_month_has_no_rates() -> None:
    assert collector.extract(_document("2026-10-unpublished", "October+2026"), {}) == []


def test_page_for_another_month_is_rejected() -> None:
    with pytest.raises(ExtractionError, match="returned"):
        collector.extract(_document("2026-09", "August+2026"), {})


def test_unrecognised_layout_raises() -> None:
    page = b"<html>maintenance</html>"
    with pytest.raises(ExtractionError, match="selector not found"):
        collector.extract(_document("2026-09", SEPTEMBER, page), {})


def _september_with(old: bytes, new: bytes) -> bytes:
    original = _fixture("2026-09")
    assert old in original
    return original.replace(old, new)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        # Total 11.8038 -> 11.9038: the components no longer add up to it.
        (_september_with(b"11.8038", b"11.9038"), "components sum"),
        (_september_with(b"11.8038", b"n/a"), "is not a number"),
        (_september_with(b">Residential<", b">Commercial<"), "residential row or columns"),
        (
            _september_with(b"<small>Generation Charge<", b"<small>Gen<"),
            "residential row or columns",
        ),
        (_without_last_residential_cell(_fixture("2026-09")), "residential row or columns"),
        (_september_with(b"September 2026", b"Sept 2026"), "unrecognised billing month"),
    ],
)
def test_unrecognised_table_raises(content: bytes, message: str) -> None:
    month = "Sept+2026" if b"Sept 2026" in content else SEPTEMBER
    with pytest.raises(ExtractionError, match=message):
        collector.extract(_document("2026-09", month, content), {})


def test_discovers_newest_months_first() -> None:
    urls = collector.discover(FakeFetcher(_fixture("selector"))).urls
    assert len(urls) == MAX_MONTHS
    assert urls[0] == f"{URL}October+2026"
    assert urls[1] == f"{URL}September+2026"
