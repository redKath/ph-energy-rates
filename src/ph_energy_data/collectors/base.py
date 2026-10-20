from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ph_energy_data.domain.models import ExtractedRate, Utility


@dataclass(frozen=True)
class FetchedDocument:
    url: str
    content: bytes
    content_type: str
    fetched_at: datetime


class Fetcher(Protocol):
    def get(self, url: str) -> FetchedDocument: ...


class Collector(ABC):
    """One utility's source. Subclass in its own module and expose an instance as `collector`."""

    utility: Utility

    @abstractmethod
    def discover(self, fetcher: Fetcher) -> list[str]:
        """URLs of the documents to collect."""

    @abstractmethod
    def extract(self, document: FetchedDocument) -> list[ExtractedRate]:
        """Candidate rates in a document. Raise ValueError if the layout is not recognised."""
