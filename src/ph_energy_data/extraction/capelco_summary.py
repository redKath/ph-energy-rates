from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def parse_summary_table(html: bytes) -> dict[str, Decimal]:
    """Residential total per kWh by `YYYY-MM` from the summary table on CAPELCO's rates page.

    Rows look like `26-Sep | 15.782 | 15.084 | 12.5836 | Download Here!`.
    """
    totals: dict[str, Decimal] = {}
    in_table = False
    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        cells = [cell.get_text(strip=True) for cell in row.find_all(["th", "td"])]
        if cells[:2] == ["Period", "Residential"]:
            in_table = True
            continue
        year, _, month = cells[0].partition("-") if cells else ("", "", "")
        if not in_table or len(cells) < 2 or month[:3].lower() not in MONTHS or len(year) != 2:
            continue
        try:
            value = Decimal(cells[1])
        except InvalidOperation:
            continue
        totals[f"20{year}-{MONTHS.index(month[:3].lower()) + 1:02d}"] = value
    if not totals:
        raise ValueError("CAPELCO summary table not found")
    return totals
