import re
from decimal import Decimal

from bs4 import BeautifulSoup

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_TWO_DIGIT_YEAR = re.compile(r"^\d{2}$")
_DECIMAL = re.compile(r"^\d+(\.\d+)?$")


def parse_summary_table(html: bytes) -> dict[str, Decimal]:
    """Residential total per kWh by `YYYY-MM` from the summary table on CAPELCO's rates page.

    Rows look like `26-Sep | 15.782 | 15.084 | 12.5836 | Download Here!`.
    Returns an empty dict when the page has no summary table.
    """
    totals: dict[str, Decimal] = {}
    in_table = False
    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
        if cells[:2] == ["Period", "Residential"]:
            in_table = True
            continue
        if not in_table or len(cells) < 2:
            continue
        year, _, month = cells[0].partition("-")
        month_abbreviation = month[:3].lower()
        if (
            month_abbreviation not in MONTHS
            or not _TWO_DIGIT_YEAR.match(year)
            or not _DECIMAL.match(cells[1])
        ):
            continue
        totals[f"20{year}-{MONTHS.index(month_abbreviation) + 1:02d}"] = Decimal(cells[1])
    return totals
