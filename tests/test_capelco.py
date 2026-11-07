from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ph_energy_data.collectors.base import ExtractionError, FetchedDocument
from ph_energy_data.collectors.capelco import LISTING_URL, MAX_MONTHS, CapelcoCollector
from ph_energy_data.domain.enums import ExtractionMethod
from ph_energy_data.extraction.capelco_summary import parse_summary_table
from ph_energy_data.extraction.capelco_table import parse_rate_table
from tests.conftest import FIXTURES, FakeFetcher

MAY_MARKDOWN = (FIXTURES / "capelco" / "2026-05.md").read_text(encoding="utf8")
LISTING = (FIXTURES / "capelco" / "listing.html").read_bytes()
BASE = "https://capelco.com/official/wp-content/uploads"
MAY_URL = f"{BASE}/2026/05/2026-Rates-May.pdf"


class FakeOcr:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown

    def first_page_markdown(self, pdf: bytes) -> str:
        return self.markdown


def _document(url: str) -> FetchedDocument:
    return FetchedDocument(url, b"%PDF", "application/pdf", datetime.now(UTC))


def test_parses_residential_total_and_generation() -> None:
    parsed = parse_rate_table(MAY_MARKDOWN)
    assert parsed.period == "2026-05"
    assert parsed.total_per_kwh == Decimal("12.0664")
    assert parsed.generation_per_kwh == Decimal("6.9113")


def test_misread_component_is_rejected() -> None:
    # 0.5782 -> 0.5882: the components no longer add up to the printed total.
    with pytest.raises(ExtractionError, match="components sum"):
        parse_rate_table(MAY_MARKDOWN.replace("0.5782", "0.5882"))


def test_label_text_in_value_cell_is_ignored() -> None:
    # The OTCA(kW) row has its label repeated in the residential cell in the fixture.
    assert "(OTCA)(kW) | Other Transmission" in MAY_MARKDOWN
    assert parse_rate_table(MAY_MARKDOWN).total_per_kwh == Decimal("12.0664")


@pytest.mark.parametrize(
    ("markdown", "message"),
    [
        ("# nothing here", "billing month not found"),
        (MAY_MARKDOWN.replace("MAY 2026", "FOO 2026"), "unrecognised billing month"),
        (MAY_MARKDOWN.replace("RESIDENTIAL", "COMMERCIAL"), "residential column not found"),
        (MAY_MARKDOWN.replace("12.0664", "n/a"), "total not readable"),
        (MAY_MARKDOWN.replace("Adjusted Generation Rate", "Adjusted Gen Rate"), "generation rate"),
        (MAY_MARKDOWN.replace("TOTAL RATE PER KWH", "SUBTOTAL"), "total rate row not found"),
    ],
)
def test_unrecognised_table_raises(markdown: str, message: str) -> None:
    with pytest.raises(ExtractionError, match=message):
        parse_rate_table(markdown)


def test_discovers_newest_months_first() -> None:
    collector = CapelcoCollector(FakeOcr(MAY_MARKDOWN))
    discovery = collector.discover(FakeFetcher(LISTING))
    assert len(discovery.urls) == MAX_MONTHS + 1
    assert discovery.urls[0].endswith("2026-Rates-Sept.pdf")
    assert any(url.endswith("2026-Rates-May.pdf") for url in discovery.urls)
    # The listing page itself comes last, after the PDFs.
    assert discovery.urls[-1] == LISTING_URL
    assert discovery.reference_totals["2026-05"] == Decimal("12.0664")


def test_extract_uses_ocr_output() -> None:
    collector = CapelcoCollector(FakeOcr(MAY_MARKDOWN))
    (rate,) = collector.extract(_document(MAY_URL), {})
    assert (rate.period, rate.rate_per_kwh) == ("2026-05", Decimal("12.0664"))
    assert rate.generation_charge_per_kwh == Decimal("6.9113")
    assert rate.extraction_method is ExtractionMethod.OCR_PARSER


def test_filename_month_must_match_document() -> None:
    collector = CapelcoCollector(FakeOcr(MAY_MARKDOWN))
    with pytest.raises(ExtractionError, match="filename says"):
        collector.extract(_document(f"{BASE}/2026/03/2026-Rates-Mar.pdf"), {})


@pytest.mark.parametrize(
    ("name", "total", "generation"),
    [
        # Older layout: "(.0918)" negatives, generation split into energy charge + OGA rows.
        ("2018-01", "9.7802", "5.8483"),
        # Merged header read twice, "-0.0758" negatives.
        ("2024-06", "13.0482", "8.6644"),
        # Generation printed as one "Adjusted Generation Rate + OGA" row.
        ("2025-03", "11.5402", "6.1968"),
        ("2026-09", "15.7820", "10.0359"),
    ],
)
def test_layout_variants(name: str, total: str, generation: str) -> None:
    parsed = parse_rate_table((FIXTURES / "capelco" / f"{name}.md").read_text(encoding="utf8"))
    assert parsed.period == name
    assert (parsed.total_per_kwh, parsed.generation_per_kwh) == (
        Decimal(total),
        Decimal(generation),
    )


def test_summary_table_covers_every_month() -> None:
    totals = parse_summary_table(LISTING)
    assert len(totals) == 105
    assert totals["2018-01"] == Decimal("9.7802")
    assert totals["2026-08"] == Decimal("14.5417")
    assert totals["2026-09"] == Decimal("15.782")


def test_summary_table_missing_is_empty() -> None:
    assert parse_summary_table(b"<html><table><tr><td>nothing</td></tr></table></html>") == {}


def test_listing_page_yields_totals_without_generation() -> None:
    collector = CapelcoCollector(FakeOcr(MAY_MARKDOWN))
    page = FetchedDocument(LISTING_URL, LISTING, "text/html", datetime.now(UTC))
    rates = collector.extract(page, {})
    assert len(rates) == 105
    assert all(rate.generation_charge_per_kwh is None for rate in rates)
    assert {rate.extraction_method for rate in rates} == {ExtractionMethod.HTML_PARSER}


def test_listing_page_without_summary_table_raises() -> None:
    collector = CapelcoCollector(FakeOcr(MAY_MARKDOWN))
    page = FetchedDocument(LISTING_URL, b"<html></html>", "text/html", datetime.now(UTC))
    with pytest.raises(ExtractionError, match="summary table not found"):
        collector.extract(page, {})


def test_ocr_total_must_match_reference_total() -> None:
    collector = CapelcoCollector(FakeOcr(MAY_MARKDOWN))
    (rate,) = collector.extract(_document(MAY_URL), {"2026-05": Decimal("12.0664")})
    assert rate.rate_per_kwh == Decimal("12.0664")
    with pytest.raises(ExtractionError, match="summary table says"):
        collector.extract(_document(MAY_URL), {"2026-05": Decimal("12.5")})
