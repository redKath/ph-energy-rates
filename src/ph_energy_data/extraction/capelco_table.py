import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

_PERIOD = re.compile(r"month of ([A-Za-z]+)\s+(\d{4})", re.IGNORECASE)
_NUMBER = re.compile(r"^(-?)(\d*\.?\d+)$")
_SUM_TOLERANCE = Decimal("0.0005")
# Rows quoted per customer or per kW rather than per kWh.
_NOT_PER_KWH = re.compile(r"RETAILCUSTOMERCHARGE|DEMAND|KW(?!H)")


@dataclass(frozen=True)
class ParsedRates:
    period: str
    total_per_kwh: Decimal
    generation_per_kwh: Decimal


def _key(text: str) -> str:
    """Label reduced to letters, so OCR spacing and punctuation drift is ignored."""
    return re.sub(r"[^A-Z]", "", text.upper())


def _number(cell: str) -> Decimal | None:
    """Decimal from a cell; negatives appear as `-0.1` or `(.1)`, otherwise None."""
    text = cell.replace(",", "").replace(" ", "")
    in_parentheses = text.startswith("(") and text.endswith(")")
    match = _NUMBER.match(text.strip("()"))
    if match is None:
        return None
    value = Decimal(match.group(2))
    return -value if in_parentheses or match.group(1) else value


def _rows(markdown: str) -> list[list[str]]:
    rows = []
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|?$", line):
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def parse_rate_table(markdown: str) -> ParsedRates:
    """Residential total and generation rate from a CAPELCO rates table.

    The total must equal the sum of the per-kWh component rows above it, which catches
    misread digits.
    """
    period_match = _PERIOD.search(markdown)
    if period_match is None:
        raise ValueError("CAPELCO billing month not found")
    month = period_match.group(1)[:3].title()
    period = datetime.strptime(f"{month} {period_match.group(2)}", "%b %Y").strftime("%Y-%m")

    rows = _rows(markdown)
    # Merged header cells can be read twice ("RESIDENTIAL RESIDENTIAL").
    header = next((r for r in rows if any(_key(c).startswith("RESIDENTIAL") for c in r)), None)
    if header is None:
        raise ValueError("CAPELCO residential column not found")
    column = next(i for i, c in enumerate(header) if _key(c).startswith("RESIDENTIAL"))

    components: list[Decimal] = []
    generation: Decimal | None = None
    for row in rows[rows.index(header) + 1 :]:
        if len(row) <= column:
            continue
        label, value = _key(row[0]), _number(row[column])
        if "TOTALRATEPERKWH" in label:
            if value is None:
                raise ValueError("CAPELCO residential total not readable")
            if generation is None:
                raise ValueError("CAPELCO generation rate not found")
            difference = abs(sum(components, Decimal(0)) - value)
            if difference > _SUM_TOLERANCE:
                raise ValueError(
                    f"components sum to {sum(components, Decimal(0))} but total is {value}"
                )
            return ParsedRates(period, value, generation)
        if value is None or _NOT_PER_KWH.search(label):
            continue
        if "GENERATION" in label:
            # Generation rate = adjusted generation rate + other generation adjustments (OGA).
            generation = (generation or Decimal(0)) + value
        components.append(value)
    raise ValueError("CAPELCO total rate row not found")
