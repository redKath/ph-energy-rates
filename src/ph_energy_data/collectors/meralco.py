import io
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urljoin

import pdfplumber
from bs4 import BeautifulSoup

from ph_energy_data.collectors.base import Collector, FetchedDocument, Fetcher
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, UtilityType
from ph_energy_data.domain.models import ExtractedRate, Utility

LISTING_URL = "https://company.meralco.com.ph/news-and-advisories/rates-archives"
# Each listing page covers four months.
MAX_PAGES = 3
EXTRACTOR_VERSION = "meralco-pdf-1"

_BILLS_LINK = re.compile(r"residential_bills")
_URL_PERIOD = re.compile(r"/(\d{4})-(\d{2})/")
_HEADING_PERIOD = re.compile(r"^(?:([A-Z][a-z]+ \d{4})|([A-Z][a-z]{2}-\d{2}))$", re.MULTILINE)
# The PDF text has stray spaces inside some numbers ("1 ,940.64", "9 .2504").
_SPLIT_NUMBER = re.compile(r"(\d) (?=[,.]\d)")
# A leading digit of the final value can be split off ("1 3.1145"); the bill cross-check
# below confirms any repaired value.
_SPLIT_TAIL = re.compile(r"(?<= )(\d) (\d+\.\d{4})$")
_BILL_ROW = re.compile(r"^200 (\d[\d,]*\.\d\d) .* (\d[\d,]*\.\d\d)$")
_RATE_ROW = re.compile(r"^200 (\d+\.\d{4}) .* (\d+\.\d{4})$")
_TYPICAL_KWH = 200
_FOUR_DP = Decimal("0.0001")
_TOLERANCE = Decimal("0.0001")


def _money(text: str) -> Decimal:
    return Decimal(text.replace(",", ""))


def _period(text: str) -> str:
    heading = _HEADING_PERIOD.search(text)
    if heading is None:
        raise ValueError("Meralco billing month not found")
    if heading.group(1):
        return datetime.strptime(heading.group(1), "%B %Y").strftime("%Y-%m")
    return datetime.strptime(heading.group(2), "%b-%y").strftime("%Y-%m")


class MeralcoCollector(Collector):
    utility = Utility(
        id="meralco",
        name="Manila Electric Company",
        type=UtilityType.PRIVATE_DU,
        aliases=["Meralco"],
    )

    def discover(self, fetcher: Fetcher) -> list[str]:
        urls: list[str] = []
        for page in range(MAX_PAGES):
            listing = fetcher.get(f"{LISTING_URL}?page={page}")
            soup = BeautifulSoup(listing.content, "html.parser")
            found = [
                urljoin(listing.url, str(a["href"]))
                for a in soup.find_all("a", href=True)
                if _BILLS_LINK.search(str(a["href"]))
            ]
            if not found:
                break
            urls.extend(u for u in found if u not in urls)
        return urls

    def extract(self, document: FetchedDocument) -> list[ExtractedRate]:
        try:
            with pdfplumber.open(io.BytesIO(document.content)) as pdf:
                text = pdf.pages[0].extract_text() or ""
        except Exception as exc:
            raise ValueError(f"unreadable Meralco PDF: {exc}") from exc

        period = _period(text)
        url_period = _URL_PERIOD.search(document.url)
        if url_period and f"{url_period.group(1)}-{url_period.group(2)}" != period:
            raise ValueError(f"PDF is for {period} but URL says {url_period.group(0)}")

        if "For Non-Lifeline Customers" not in text:
            raise ValueError("Meralco non-lifeline table not found")
        bill = rate = None
        for raw in text.split("For Non-Lifeline Customers", 1)[1].splitlines():
            line = _SPLIT_NUMBER.sub(lambda m: m.group(1), raw.strip())
            line = _SPLIT_TAIL.sub(lambda m: m.group(1) + m.group(2), line)
            bill = bill or _BILL_ROW.match(line)
            rate = rate or _RATE_ROW.match(line)
        if bill is None or rate is None:
            raise ValueError(f"no {_TYPICAL_KWH} kWh row in Meralco bills table")

        # The page prints the overall rate per kWh and the bill in pesos for 200 kWh;
        # the two must agree, which also catches digits garbled by the PDF text layer.
        generation, overall = Decimal(rate.group(1)), Decimal(rate.group(2))
        bill_generation, bill_total = _money(bill.group(1)), _money(bill.group(2))
        if abs(bill_total / _TYPICAL_KWH - overall) > _TOLERANCE:
            raise ValueError(f"overall rate {overall} disagrees with bill total {bill_total}")
        if abs(bill_generation / _TYPICAL_KWH - generation) > _TOLERANCE:
            raise ValueError(f"generation {generation} disagrees with bill {bill_generation}")
        return [
            ExtractedRate(
                period=period,
                rate_per_kwh=overall,
                rate_basis=RateBasis.PUBLISHED_TOTAL,
                generation_charge_per_kwh=generation,
                extraction_method=ExtractionMethod.PDF_PARSER,
                extractor_version=EXTRACTOR_VERSION,
            )
        ]


collector = MeralcoCollector()
