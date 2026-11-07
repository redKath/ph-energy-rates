from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from ph_energy_data.domain.models import ExtractedRate, Utility

ReferenceTotals = Mapping[str, Decimal]


class FetchError(Exception):
    """A document could not be downloaded."""


class ExtractionError(ValueError):
    """A document's layout or values were not recognised."""


def period_from_month_text(text: str, date_format: str) -> str:
    """`YYYY-MM` from a printed month such as `September 2026` (`%B %Y`)."""
    try:
        return datetime.strptime(text, date_format).strftime("%Y-%m")
    except ValueError as exc:
        raise ExtractionError(f"unrecognised billing month {text!r}") from exc


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    content: bytes
    content_type: str
    fetched_at: datetime


@dataclass(frozen=True)
class Discovery:
    urls: list[str]
    # Residential totals per kWh by `YYYY-MM` published elsewhere, used to cross-check extractions.
    reference_totals: ReferenceTotals = field(default_factory=dict)


class Fetcher(Protocol):
    def get(self, url: str) -> FetchedDocument: ...


class Collector(ABC):
    """One utility's source. Subclass in its own module and list it in `collectors/registry.py`."""

    utility: Utility

    @abstractmethod
    def discover(self, fetcher: Fetcher) -> Discovery:
        """URLs of the documents to collect."""

    @abstractmethod
    def extract(
        self, document: FetchedDocument, reference_totals: ReferenceTotals
    ) -> list[ExtractedRate]:
        """Candidate rates in a document. Raise ExtractionError if the layout is not recognised."""
