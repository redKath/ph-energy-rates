from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.collectors.base import FetchedDocument
from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import RateStatus, RunStatus
from ph_energy_data.domain.models import ExtractedRate
from ph_energy_data.services.pipeline import run_collector
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.models import PipelineRun, RateObservation, SourceDocument
from tests.conftest import STUB_PAGE, FakeFetcher, StubCollector

PAGE = STUB_PAGE
collector = StubCollector()


def _run(
    session_factory: sessionmaker[Session], archive: LocalArchive, content: bytes = PAGE
) -> PipelineRun:
    return run_collector(
        collector,
        session_factory=session_factory,
        fetcher=FakeFetcher(content),
        archive=archive,
        settings=Settings(),
    )


def _count(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_collects_and_publishes(
    session_factory: sessionmaker[Session], archive: LocalArchive
) -> None:
    run = _run(session_factory, archive)
    assert run.status is RunStatus.SUCCEEDED
    assert run.rates_created == 12
    with session_factory() as session:
        statuses = set(session.scalars(select(RateObservation.status)))
        document = session.scalars(select(SourceDocument)).one()
    assert statuses == {RateStatus.PUBLISHED}
    assert (archive.root / document.archive_path).read_bytes() == PAGE


def test_rerun_same_document_adds_nothing(
    session_factory: sessionmaker[Session], archive: LocalArchive
) -> None:
    _run(session_factory, archive)
    run = _run(session_factory, archive)
    assert run.documents_fetched == 1
    assert run.rates_created == 0
    assert _count(session_factory, SourceDocument) == 1
    assert _count(session_factory, RateObservation) == 12


def test_changed_page_same_rates_adds_no_duplicates(
    session_factory: sessionmaker[Session], archive: LocalArchive
) -> None:
    _run(session_factory, archive)
    run = _run(session_factory, archive, PAGE + b"# changed" + bytes([10]))
    assert run.rates_created == 0
    assert _count(session_factory, SourceDocument) == 2
    assert _count(session_factory, RateObservation) == 12


def test_unrecognised_layout_fails_run_and_stores_nothing(
    session_factory: sessionmaker[Session], archive: LocalArchive
) -> None:
    run = _run(session_factory, archive, b"<html>maintenance</html>")
    assert run.status is RunStatus.FAILED
    assert "table not found" in (run.error or "")
    assert _count(session_factory, RateObservation) == 0
    assert _count(session_factory, SourceDocument) == 0


def test_second_source_kept_only_when_it_adds_generation(
    session_factory: sessionmaker[Session], archive: LocalArchive
) -> None:
    class WithGeneration(StubCollector):
        def extract(self, document: FetchedDocument) -> list[ExtractedRate]:
            return [
                r.model_copy(update={"generation_charge_per_kwh": Decimal("5")})
                for r in super().extract(document)
            ]

    _run(session_factory, archive)
    # Same totals, now with a generation charge: stored again, with their own source.
    run = run_collector(
        WithGeneration(),
        session_factory=session_factory,
        fetcher=FakeFetcher(PAGE + b"# second source" + bytes([10])),
        archive=archive,
        settings=Settings(),
    )
    assert run.rates_created == 12
    # Totals alone do not add anything once a row with generation exists.
    run = _run(session_factory, archive, PAGE + b"# third" + bytes([10]))
    assert run.rates_created == 0
