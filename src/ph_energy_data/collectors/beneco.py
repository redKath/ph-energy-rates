import re
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from ph_energy_data.collectors.base import (
    Collector,
    Discovery,
    ExtractionError,
    FetchedDocument,
    Fetcher,
    ReferenceTotals,
    period_from_month_text,
)
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, UtilityType
from ph_energy_data.domain.models import ExtractedRate, Utility

URL = "https://www.beneco.com.ph/rates.php"
MAX_MONTHS = 24
EXTRACTOR_VERSION = "beneco-html-2"

_MONTH_LABEL = re.compile(r"^[A-Z][a-z]+ \d{4}$")
_FOUR_DP = Decimal("0.0001")
# BENECO's printed totals differ from the sum of its components by up to about 0.03.
_SUM_TOLERANCE = Decimal("0.05")
# Columns quoted per customer, per kW or as demand rather than per kWh.
_NOT_PER_KWH = re.compile(
    r"Retail Customer Charge|Demand|Php/cust|Php/kW(?!h)|VAT Transmission Ancillary", re.IGNORECASE
)


def _month_labels(soup: BeautifulSoup) -> list[str]:
    texts = (option.get_text(strip=True) for option in soup.find_all("option"))
    return [text for text in texts if _MONTH_LABEL.match(text)]


def _selected_labels(soup: BeautifulSoup) -> list[str]:
    return [option.get_text(strip=True) for option in soup.find_all("option", selected=True)]


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ExtractionError(f"BENECO value {text!r} is not a number") from exc


class BenecoCollector(Collector):
    utility = Utility(
        id="beneco",
        name="Benguet Electric Cooperative",
        type=UtilityType.ELECTRIC_COOPERATIVE,
        aliases=["BENECO"],
    )

    def discover(self, fetcher: Fetcher) -> Discovery:
        # The month selector lists every month BENECO shows, newest first.
        page = fetcher.get(f"{URL}?{urlencode({'q': 'month'})}")
        months = _month_labels(BeautifulSoup(page.content, "html.parser"))[:MAX_MONTHS]
        return Discovery(
            [f"{URL}?{urlencode({'q': 'month', 'monthyear': month})}" for month in months]
        )

    def extract(
        self, document: FetchedDocument, reference_totals: ReferenceTotals
    ) -> list[ExtractedRate]:
        soup = BeautifulSoup(document.content, "html.parser")
        if not _month_labels(soup):
            raise ExtractionError("BENECO month selector not found")
        selected_month = next(
            (label for label in _selected_labels(soup) if _MONTH_LABEL.match(label)),
            None,
        )
        requested_month = parse_qs(urlsplit(document.url).query).get("monthyear", [None])[0]
        if selected_month is None or (requested_month and requested_month != selected_month):
            raise ExtractionError(f"BENECO returned {selected_month!r} for {requested_month!r}")

        table = soup.find("table")
        if table is None:
            # The selector lists months BENECO has not published a breakdown for yet.
            return []
        rows = [
            [cell.get_text(" ", strip=True) for cell in table_row.find_all(["th", "td"])]
            for table_row in table.find_all("tr")
        ]
        header = rows[0] if rows else []
        residential = next((row for row in rows[1:] if row and row[0] == "Residential"), None)
        if (
            residential is None
            or len(residential) != len(header)
            or "Generation Charge" not in header
            or "Total Php/kWh" not in header
        ):
            raise ExtractionError("BENECO residential row or columns not found")

        total = _decimal(residential[header.index("Total Php/kWh")])
        generation = _decimal(residential[header.index("Generation Charge")])
        components = [
            _decimal(value)
            for name, value in zip(header[1:-1], residential[1:-1], strict=True)
            if value and not _NOT_PER_KWH.search(name)
        ]
        # The total should match the per-kWh components, which catches a misaligned table.
        components_sum = sum(components, Decimal(0))
        if abs(components_sum - total) > _SUM_TOLERANCE:
            raise ExtractionError(f"components sum to {components_sum} but total is {total}")

        return [
            ExtractedRate(
                period=period_from_month_text(selected_month, "%B %Y"),
                rate_per_kwh=total.quantize(_FOUR_DP),
                rate_basis=RateBasis.PUBLISHED_TOTAL,
                generation_charge_per_kwh=generation.quantize(_FOUR_DP),
                extraction_method=ExtractionMethod.HTML_PARSER,
                extractor_version=EXTRACTOR_VERSION,
            )
        ]
