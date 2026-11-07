import re
from dataclasses import dataclass
from decimal import Decimal

from ph_energy_data.collectors.base import ExtractionError, period_from_month_text

_PERIOD = re.compile(r"month of ([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
_NUMBER = re.compile(r"^(-?)(\d*\.?\d+)$")
_TABLE_SEPARATOR = re.compile(r"^\|[\s:|-]+\|?$")
_SUM_TOLERANCE = Decimal("0.0005")
# Rows quoted per customer or per kW rather than per kWh.
_NOT_PER_KWH = re.compile(r"RETAILCUSTOMERCHARGE|DEMAND|KW(?!H)")


@dataclass(frozen=True)
class ParsedRates:
    period: str
    total_per_kwh: Decimal
    generation_per_kwh: Decimal


def _letters_only(text: str) -> str:
    """Label reduced to uppercase letters, so OCR spacing and punctuation drift is ignored."""
    return re.sub(r"[^A-Z]", "", text.upper())


def _parse_number(cell: str) -> Decimal | None:
    """Decimal from a cell (negatives appear as `-0.1` or `(.1)`), or None if not a number."""
    text = cell.replace(",", "").replace(" ", "")
    in_parentheses = text.startswith("(") and text.endswith(")")
    match = _NUMBER.match(text.strip("()"))
    if match is None:
        return None
    value = Decimal(match.group(2))
    return -value if in_parentheses or match.group(1) else value


def _table_rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("|") and not _TABLE_SEPARATOR.match(line):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def _is_residential_header_cell(cell: str) -> bool:
    return _letters_only(cell).startswith("RESIDENTIAL")


def parse_rate_table(markdown: str) -> ParsedRates:
    """Residential total and generation rate from a CAPELCO rates table.

    The total must equal the sum of the per-kWh component rows above it, which catches
    misread digits.
    """
    period_match = _PERIOD.search(markdown)
    if period_match is None:
        raise ExtractionError("CAPELCO billing month not found")
    month = period_match.group(1)[:3].title()
    period = period_from_month_text(f"{month} {period_match.group(2)}", "%b %Y")

    rows = _table_rows(markdown)
    # Merged header cells can be read twice ("RESIDENTIAL RESIDENTIAL").
    header = next((row for row in rows if any(map(_is_residential_header_cell, row))), None)
    if header is None:
        raise ExtractionError("CAPELCO residential column not found")
    column = next(index for index, cell in enumerate(header) if _is_residential_header_cell(cell))

    components: list[Decimal] = []
    generation: Decimal | None = None
    for row in rows[rows.index(header) + 1 :]:
        if len(row) <= column:
            continue
        label, value = _letters_only(row[0]), _parse_number(row[column])
        if "TOTALRATEPERKWH" in label:
            if value is None:
                raise ExtractionError("CAPELCO residential total not readable")
            if generation is None:
                raise ExtractionError("CAPELCO generation rate not found")
            components_sum = sum(components, Decimal(0))
            if abs(components_sum - value) > _SUM_TOLERANCE:
                raise ExtractionError(f"components sum to {components_sum} but total is {value}")
            return ParsedRates(period, value, generation)
        if value is None or _NOT_PER_KWH.search(label):
            continue
        if "GENERATION" in label:
            # Generation rate = adjusted generation rate + other generation adjustments (OGA).
            generation = (generation or Decimal(0)) + value
        components.append(value)
    raise ExtractionError("CAPELCO total rate row not found")
