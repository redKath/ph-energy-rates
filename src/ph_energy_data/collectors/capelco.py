import re
from typing import Protocol
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ph_energy_data.collectors.base import (
    Collector,
    Discovery,
    ExtractionError,
    FetchedDocument,
    Fetcher,
    ReferenceTotals,
)
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, UtilityType
from ph_energy_data.domain.models import ExtractedRate, Utility
from ph_energy_data.extraction.capelco_summary import MONTHS, parse_summary_table
from ph_energy_data.extraction.capelco_table import parse_rate_table

LISTING_URL = "https://capelco.com/official/power-rates/"
MAX_MONTHS = 12
EXTRACTOR_VERSION = "capelco-docling-1"
SUMMARY_VERSION = "capelco-summary-1"

_FILENAME = re.compile(r"(\d{4})-Rates-([A-Za-z]+)")


class PdfOcr(Protocol):
    def first_page_markdown(self, pdf: bytes) -> str: ...


def _period_from_url(url: str) -> str | None:
    match = _FILENAME.search(url.rsplit("/", 1)[-1])
    if match is None or match.group(2)[:3].lower() not in MONTHS:
        return None
    return f"{match.group(1)}-{MONTHS.index(match.group(2)[:3].lower()) + 1:02d}"


class CapelcoCollector(Collector):
    utility = Utility(
        id="capelco",
        name="Capiz Electric Cooperative",
        type=UtilityType.ELECTRIC_COOPERATIVE,
        aliases=["CAPELCO"],
    )

    def __init__(self, ocr: PdfOcr) -> None:
        self._ocr = ocr

    def discover(self, fetcher: Fetcher) -> Discovery:
        listing = fetcher.get(LISTING_URL)
        url_by_period: dict[str, str] = {}
        for link in BeautifulSoup(listing.content, "html.parser").find_all("a", href=True):
            url = urljoin(listing.url, str(link["href"]))
            period = _period_from_url(url)
            # An "_opt" file is a re-saved copy of the same month; prefer the original.
            if period and (period not in url_by_period or "_opt" in url_by_period[period]):
                url_by_period[period] = url
        newest_periods = sorted(url_by_period, reverse=True)[:MAX_MONTHS]
        # The listing goes last so the PDFs (which also carry generation) are stored first.
        return Discovery(
            urls=[*(url_by_period[period] for period in newest_periods), LISTING_URL],
            reference_totals=parse_summary_table(listing.content),
        )

    def extract(
        self, document: FetchedDocument, reference_totals: ReferenceTotals
    ) -> list[ExtractedRate]:
        if document.content_type != "application/pdf":
            return self._extract_summary_table(document)
        parsed = parse_rate_table(self._ocr.first_page_markdown(document.content))
        url_period = _period_from_url(document.url)
        if url_period and url_period != parsed.period:
            raise ExtractionError(f"PDF is for {parsed.period} but filename says {url_period}")
        expected = reference_totals.get(parsed.period)
        if expected is not None and expected != parsed.total_per_kwh:
            raise ExtractionError(
                f"OCR total {parsed.total_per_kwh} but summary table says {expected}"
            )
        return [
            ExtractedRate(
                period=parsed.period,
                rate_per_kwh=parsed.total_per_kwh,
                rate_basis=RateBasis.PUBLISHED_TOTAL,
                generation_charge_per_kwh=parsed.generation_per_kwh,
                extraction_method=ExtractionMethod.OCR_PARSER,
                extractor_version=EXTRACTOR_VERSION,
            )
        ]

    def _extract_summary_table(self, document: FetchedDocument) -> list[ExtractedRate]:
        totals = parse_summary_table(document.content)
        if not totals:
            raise ExtractionError("CAPELCO summary table not found")
        return [
            ExtractedRate(
                period=period,
                rate_per_kwh=total,
                rate_basis=RateBasis.PUBLISHED_TOTAL,
                extraction_method=ExtractionMethod.HTML_PARSER,
                extractor_version=SUMMARY_VERSION,
            )
            for period, total in totals.items()
        ]
