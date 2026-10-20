import re
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ph_energy_data.collectors.base import Collector, FetchedDocument, Fetcher
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, UtilityType
from ph_energy_data.domain.models import ExtractedRate, Utility
from ph_energy_data.extraction.capelco_summary import MONTHS, parse_summary_table
from ph_energy_data.extraction.capelco_table import parse_rate_table
from ph_energy_data.extraction.docling_ocr import first_page_markdown

LISTING_URL = "https://capelco.com/official/power-rates/"
# OCR is slow, so only the most recent months are collected.
MAX_MONTHS = 12
EXTRACTOR_VERSION = "capelco-docling-1"
SUMMARY_VERSION = "capelco-summary-1"

_FILENAME = re.compile(r"(\d{4})-Rates-([A-Za-z]+)")


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

    def __init__(self) -> None:
        # Residential totals from the listing page, used to check each OCR result.
        self.summary: dict[str, Decimal] = {}

    def discover(self, fetcher: Fetcher) -> list[str]:
        listing = fetcher.get(LISTING_URL)
        try:
            self.summary = parse_summary_table(listing.content)
        except ValueError:
            self.summary = {}
        soup = BeautifulSoup(listing.content, "html.parser")
        by_period: dict[str, str] = {}
        for link in soup.find_all("a", href=True):
            url = urljoin(listing.url, str(link["href"]))
            period = _period_from_url(url)
            # An "_opt" file is a re-saved copy of the same month; prefer the original.
            if period and (period not in by_period or "_opt" in by_period[period]):
                by_period[period] = url
        newest = sorted(by_period, reverse=True)[:MAX_MONTHS]
        # The listing goes last so the PDFs (which also carry generation) are stored first.
        return [*(by_period[period] for period in newest), LISTING_URL]

    def extract(self, document: FetchedDocument) -> list[ExtractedRate]:
        if document.content_type != "application/pdf":
            return [
                ExtractedRate(
                    period=period,
                    rate_per_kwh=total,
                    rate_basis=RateBasis.PUBLISHED_TOTAL,
                    extraction_method=ExtractionMethod.HTML_PARSER,
                    extractor_version=SUMMARY_VERSION,
                )
                for period, total in parse_summary_table(document.content).items()
            ]
        parsed = parse_rate_table(first_page_markdown(document.content))
        url_period = _period_from_url(document.url)
        if url_period and url_period != parsed.period:
            raise ValueError(f"PDF is for {parsed.period} but filename says {url_period}")
        expected = self.summary.get(parsed.period)
        if expected is not None and expected != parsed.total_per_kwh:
            raise ValueError(f"OCR total {parsed.total_per_kwh} but summary table says {expected}")
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


collector = CapelcoCollector()
