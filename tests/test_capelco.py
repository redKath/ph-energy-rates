from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ph_energy_data.collectors import capelco
from ph_energy_data.collectors.base import FetchedDocument
from ph_energy_data.collectors.capelco import LISTING_URL, MAX_MONTHS, CapelcoCollector, collector
from ph_energy_data.domain.enums import ExtractionMethod
from ph_energy_data.extraction.capelco_summary import parse_summary_table
from ph_energy_data.extraction.capelco_table import parse_rate_table
from tests.conftest import FIXTURES, FakeFetcher

MAY_MARKDOWN = (FIXTURES / "capelco" / "2026-05.md").read_text(encoding="utf8")
LISTING = (FIXTURES / "capelco" / "listing.html").read_bytes()
BASE = "https://capelco.com/official/wp-content/uploads"


def _document(url: str) -> FetchedDocument:
    return FetchedDocument(url, b"%PDF", "application/pdf", datetime.now(UTC))


def test_parses_residential_total_and_generation() -> None:
    parsed = parse_rate_table(MAY_MARKDOWN)
    assert parsed.period == "2026-05"
    assert parsed.total_per_kwh == Decimal("12.0664")
    assert parsed.generation_per_kwh == Decimal("6.9113")


def test_misread_component_is_rejected() -> None:
    # 0.5782 -> 0.5882: the components no longer add up to the printed total.
    with pytest.raises(ValueError, match="components sum"):
        parse_rate_table(MAY_MARKDOWN.replace("0.5782", "0.5882"))


def test_label_text_in_value_cell_is_ignored() -> None:
    # The OTCA(kW) row has its label repeated in the residential cell in the fixture.
    assert "(OTCA)(kW) | Other Transmission" in MAY_MARKDOWN
    parse_rate_table(MAY_MARKDOWN)


def test_missing_table_raises() -> None:
    with pytest.raises(ValueError, match="billing month"):
        parse_rate_table("# nothing here")


def test_discovers_newest_months_first() -> None:
    urls = collector.discover(FakeFetcher(LISTING))
    assert len(urls) == MAX_MONTHS + 1
    assert urls[0].endswith("2026-Rates-Sept.pdf")
    assert any(u.endswith("2026-Rates-May.pdf") for u in urls)
    # The listing page itself comes last, after the PDFs.
    assert urls[-1] == LISTING_URL


def test_extract_uses_ocr_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capelco, "first_page_markdown", lambda pdf: MAY_MARKDOWN)
    (rate,) = collector.extract(_document(f"{BASE}/2026/05/2026-Rates-May.pdf"))
    assert (rate.period, rate.rate_per_kwh) == ("2026-05", Decimal("12.0664"))
    assert rate.extraction_method is ExtractionMethod.OCR_PARSER


def test_filename_month_must_match_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capelco, "first_page_markdown", lambda pdf: MAY_MARKDOWN)
    with pytest.raises(ValueError, match="filename says"):
        collector.extract(_document(f"{BASE}/2026/03/2026-Rates-Mar.pdf"))


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


def test_summary_table_missing_raises() -> None:
    with pytest.raises(ValueError, match="summary table"):
        parse_summary_table(b"<html><table><tr><td>nothing</td></tr></table></html>")


def test_listing_page_yields_totals_without_generation() -> None:
    page = FetchedDocument(LISTING_URL, LISTING, "text/html", datetime.now(UTC))
    rates = collector.extract(page)
    assert len(rates) == 105
    assert all(r.generation_charge_per_kwh is None for r in rates)
    assert {r.extraction_method for r in rates} == {ExtractionMethod.HTML_PARSER}


def test_ocr_total_must_match_summary_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(capelco, "first_page_markdown", lambda pdf: MAY_MARKDOWN)
    checked = CapelcoCollector()
    checked.discover(FakeFetcher(LISTING))
    url = f"{BASE}/2026/05/2026-Rates-May.pdf"
    (rate,) = checked.extract(_document(url))
    assert rate.rate_per_kwh == checked.summary["2026-05"]
    checked.summary["2026-05"] = Decimal("12.5")
    with pytest.raises(ValueError, match="summary table says"):
        checked.extract(_document(url))
