from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.collectors.base import (
    Collector,
    Discovery,
    FetchedDocument,
    Fetcher,
    FetchError,
    ReferenceTotals,
)
from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import RateStatus, RunStatus
from ph_energy_data.domain.models import ExtractedRate
from ph_energy_data.services.pipeline import RunSummary, run_collector
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.models import Base, PipelineRun, RateObservation, SourceDocument
from tests.conftest import STUB_PAGE, FakeFetcher, RoutingFetcher, StubCollector


def _run(
    session_factory: sessionmaker[Session],
    archive: LocalArchive,
    settings: Settings,
    content: bytes = STUB_PAGE,
    collector: Collector | None = None,
    fetcher: Fetcher | None = None,
) -> RunSummary:
    return run_collector(
        collector or StubCollector(),
        session_factory=session_factory,
        fetcher=fetcher or FakeFetcher(content),
        archive=archive,
        settings=settings,
    )


def _count(session_factory: sessionmaker[Session], model: type[Base]) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_collects_and_publishes(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    summary = _run(session_factory, archive, settings)
    assert summary.status is RunStatus.SUCCEEDED
    assert summary.rates_created == 12
    with session_factory() as session:
        statuses = set(session.scalars(select(RateObservation.status)))
        document = session.scalars(select(SourceDocument)).one()
        run = session.scalars(select(PipelineRun)).one()
    assert statuses == {RateStatus.PUBLISHED}
    assert (archive.root / document.archive_path).read_bytes() == STUB_PAGE
    assert (run.status, run.rates_created, run.finished_at is not None) == (
        RunStatus.SUCCEEDED,
        12,
        True,
    )


def test_rerun_same_document_adds_nothing(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    _run(session_factory, archive, settings)
    summary = _run(session_factory, archive, settings)
    assert summary.documents_fetched == 1
    assert summary.rates_created == 0
    assert _count(session_factory, SourceDocument) == 1
    assert _count(session_factory, RateObservation) == 12


def test_changed_page_same_rates_adds_no_duplicates(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    _run(session_factory, archive, settings)
    summary = _run(session_factory, archive, settings, STUB_PAGE + b"# changed\n")
    assert summary.rates_created == 0
    assert _count(session_factory, SourceDocument) == 2
    assert _count(session_factory, RateObservation) == 12


def test_unrecognised_layout_fails_run_and_stores_nothing(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    summary = _run(session_factory, archive, settings, b"<html>maintenance</html>")
    assert summary.status is RunStatus.FAILED
    assert "table not found" in (summary.error or "")
    assert _count(session_factory, RateObservation) == 0
    assert _count(session_factory, SourceDocument) == 0


def test_second_source_kept_only_when_it_adds_generation(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    class WithGeneration(StubCollector):
        def extract(
            self, document: FetchedDocument, reference_totals: ReferenceTotals
        ) -> list[ExtractedRate]:
            return [
                rate.model_copy(update={"generation_charge_per_kwh": Decimal("5")})
                for rate in super().extract(document, reference_totals)
            ]

    _run(session_factory, archive, settings)
    # Same totals, now with a generation charge: stored again, with their own source.
    summary = _run(
        session_factory, archive, settings, STUB_PAGE + b"# second source\n", WithGeneration()
    )
    assert summary.rates_created == 12
    # Totals alone do not add anything once a row with generation exists.
    summary = _run(session_factory, archive, settings, STUB_PAGE + b"# third\n")
    assert summary.rates_created == 0


def test_out_of_range_rate_is_stored_as_rejected(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    summary = _run(session_factory, archive, settings, b"STUB\n2026-01 99.00\n")
    assert summary.rates_created == 1
    assert summary.rates_flagged == 1
    with session_factory() as session:
        rate = session.scalars(select(RateObservation)).one()
    assert (rate.status, rate.flags) == (RateStatus.REJECTED, ["rate_out_of_range"])


class _MultiDocumentCollector(StubCollector):
    def discover(self, fetcher: Fetcher) -> Discovery:
        return Discovery(["https://stub.test/good", "https://stub.test/missing"])


def test_failed_download_does_not_block_other_documents(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    fetcher = RoutingFetcher({"https://stub.test/good": (STUB_PAGE, "text/html")})
    summary = _run(
        session_factory, archive, settings, collector=_MultiDocumentCollector(), fetcher=fetcher
    )
    assert summary.status is RunStatus.FAILED
    assert "https://stub.test/missing" in (summary.error or "")
    assert summary.rates_created == 12


def test_discovery_failure_is_reported(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    class UnreachableListing(StubCollector):
        def discover(self, fetcher: Fetcher) -> Discovery:
            raise FetchError("listing down")

    summary = _run(session_factory, archive, settings, collector=UnreachableListing())
    assert summary.status is RunStatus.FAILED
    assert (summary.error or "").startswith("discover: FetchError")
    assert summary.documents_fetched == 0


def test_unexpected_exception_is_not_swallowed(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    class Buggy(StubCollector):
        def extract(
            self, document: FetchedDocument, reference_totals: ReferenceTotals
        ) -> list[ExtractedRate]:
            raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        _run(session_factory, archive, settings, collector=Buggy())


def test_long_error_list_is_truncated(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> None:
    class ManyBadDocuments(StubCollector):
        def discover(self, fetcher: Fetcher) -> Discovery:
            return Discovery([f"https://stub.test/{number}" for number in range(8)])

    summary = _run(
        session_factory, archive, settings, collector=ManyBadDocuments(), fetcher=RoutingFetcher({})
    )
    assert (summary.error or "").endswith("(+3 more)")
