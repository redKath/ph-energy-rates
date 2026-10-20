import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit

from bs4 import BeautifulSoup

from ph_energy_data.collectors.base import Collector, FetchedDocument, Fetcher
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


class BenecoCollector(Collector):
    utility = Utility(
        id="beneco",
        name="Benguet Electric Cooperative",
        type=UtilityType.ELECTRIC_COOPERATIVE,
        aliases=["BENECO"],
    )

    def discover(self, fetcher: Fetcher) -> list[str]:
        # The month selector lists every month BENECO shows, newest first.
        page = fetcher.get(f"{URL}?{urlencode({'q': 'month'})}")
        months = _month_labels(BeautifulSoup(page.content, "html.parser"))[:MAX_MONTHS]
        return [f"{URL}?{urlencode({'q': 'month', 'monthyear': month})}" for month in months]

    def extract(self, document: FetchedDocument) -> list[ExtractedRate]:
        soup = BeautifulSoup(document.content, "html.parser")
        labels = _month_labels(soup)
        if not labels:
            raise ValueError("BENECO month selector not found")
        selected = next(
            (
                o.get_text(strip=True)
                for o in soup.find_all("option", selected=True)
                if _MONTH_LABEL.match(o.get_text(strip=True))
            ),
            None,
        )
        requested = parse_qs(urlsplit(document.url).query).get("monthyear", [None])[0]
        if selected is None or (requested and requested != selected):
            raise ValueError(f"BENECO returned {selected!r} for {requested!r}")

        table = soup.find("table")
        if table is None:
            # The selector lists months BENECO has not published a breakdown for yet.
            return []
        rows = [
            [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            for tr in table.find_all("tr")
        ]
        header = rows[0]
        residential = next((r for r in rows[1:] if r and r[0] == "Residential"), None)
        if (
            residential is None
            or "Generation Charge" not in header
            or "Total Php/kWh" not in header
        ):
            raise ValueError("BENECO residential row or columns not found")

        total = Decimal(residential[header.index("Total Php/kWh")])
        generation = Decimal(residential[header.index("Generation Charge")])
        components = [
            Decimal(value)
            for name, value in zip(header[1:-1], residential[1:-1], strict=True)
            if value and not _NOT_PER_KWH.search(name)
        ]
        # The total should match the per-kWh components, which catches a misaligned table.
        if abs(sum(components, Decimal(0)) - total) > _SUM_TOLERANCE:
            raise ValueError(
                f"components sum to {sum(components, Decimal(0))} but total is {total}"
            )

        return [
            ExtractedRate(
                period=datetime.strptime(selected, "%B %Y").strftime("%Y-%m"),
                rate_per_kwh=total.quantize(_FOUR_DP),
                rate_basis=RateBasis.PUBLISHED_TOTAL,
                generation_charge_per_kwh=generation.quantize(_FOUR_DP),
                extraction_method=ExtractionMethod.HTML_PARSER,
                extractor_version=EXTRACTOR_VERSION,
            )
        ]


collector = BenecoCollector()
