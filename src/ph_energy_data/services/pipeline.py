import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.collectors.base import (
    Collector,
    Discovery,
    ExtractionError,
    FetchedDocument,
    Fetcher,
    FetchError,
    ReferenceTotals,
)
from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import CustomerClass, RateStatus, RunStatus
from ph_energy_data.domain.models import ExtractedRate
from ph_energy_data.domain.periods import previous_period
from ph_energy_data.storage.archive import ArchiveStore
from ph_energy_data.storage.models import PipelineRun, RateObservation, SourceDocument, Utility
from ph_energy_data.validation.rules import Context, validate

log = structlog.get_logger(__name__)

_DISCOVERY_ERRORS = (FetchError, ExtractionError)
_DOCUMENT_ERRORS = (FetchError, ExtractionError, ValidationError, SQLAlchemyError, OSError)
_MAX_ERRORS_REPORTED = 5


@dataclass(frozen=True)
class RunSummary:
    status: RunStatus
    documents_fetched: int
    rates_created: int
    rates_flagged: int
    error: str | None


def run_collector(
    collector: Collector,
    *,
    session_factory: sessionmaker[Session],
    fetcher: Fetcher,
    archive: ArchiveStore,
    settings: Settings,
) -> RunSummary:
    """Collect, archive, extract, validate and store one utility's rates. Safe to re-run."""
    utility = collector.utility
    log.info("run_started", utility=utility.id)
    with session_factory() as session:
        if session.get(Utility, utility.id) is None:
            session.add(Utility(**utility.model_dump()))
            session.flush()
        run = PipelineRun(
            utility_id=utility.id, started_at=datetime.now(UTC), status=RunStatus.RUNNING
        )
        session.add(run)
        session.commit()
        run_id = run.id

        documents_fetched = rates_created = rates_flagged = 0
        errors: list[str] = []
        discovery = Discovery(urls=[])
        try:
            discovery = collector.discover(fetcher)
        except _DISCOVERY_ERRORS as exc:
            errors.append(f"discover: {type(exc).__name__}: {exc}")
            log.error("discovery_failed", utility=utility.id, error=str(exc))
        for url in discovery.urls:
            try:
                document = fetcher.get(url)
                documents_fetched += 1
                new_rates = _store_document(
                    session, collector, document, discovery.reference_totals, archive, settings
                )
                session.commit()
            except _DOCUMENT_ERRORS as exc:
                session.rollback()
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
                log.error(
                    "document_failed", utility=utility.id, url=url, error_type=type(exc).__name__
                )
                continue
            rates_created += len(new_rates)
            rates_flagged += sum(rate.status is not RateStatus.PUBLISHED for rate in new_rates)

        finished_run = session.get_one(PipelineRun, run_id)
        finished_run.documents_fetched = documents_fetched
        finished_run.rates_created = rates_created
        finished_run.rates_flagged = rates_flagged
        finished_run.status = RunStatus.FAILED if errors else RunStatus.SUCCEEDED
        finished_run.error = _summarise(errors)
        finished_run.finished_at = datetime.now(UTC)
        session.commit()
        summary = RunSummary(
            status=finished_run.status,
            documents_fetched=documents_fetched,
            rates_created=rates_created,
            rates_flagged=rates_flagged,
            error=finished_run.error,
        )
    log.info(
        "run_finished",
        utility=utility.id,
        status=summary.status.value,
        documents_fetched=documents_fetched,
        rates_created=rates_created,
        rates_flagged=rates_flagged,
    )
    return summary


def _summarise(errors: list[str]) -> str | None:
    if not errors:
        return None
    hidden = len(errors) - _MAX_ERRORS_REPORTED
    suffix = f" (+{hidden} more)" if hidden > 0 else ""
    return "; ".join(errors[:_MAX_ERRORS_REPORTED]) + suffix


def _store_document(
    session: Session,
    collector: Collector,
    document: FetchedDocument,
    reference_totals: ReferenceTotals,
    archive: ArchiveStore,
    settings: Settings,
) -> list[RateObservation]:
    """Archive and extract one document unless it was already stored; return new rates."""
    utility_id = collector.utility.id
    sha256 = hashlib.sha256(document.content).hexdigest()
    already_stored = session.scalar(
        select(SourceDocument.id).where(
            SourceDocument.utility_id == utility_id, SourceDocument.sha256 == sha256
        )
    )
    if already_stored is not None:
        log.info("document_already_stored", utility=utility_id, url=document.url)
        return []
    extracted_rates = sorted(
        collector.extract(document, reference_totals), key=lambda rate: rate.period
    )
    source = SourceDocument(
        utility_id=utility_id,
        url=document.url,
        fetched_at=document.fetched_at,
        content_type=document.content_type,
        sha256=sha256,
        archive_path=archive.save(utility_id, sha256, document.content_type, document.content),
    )
    session.add(source)
    session.flush()
    stored: list[RateObservation] = []
    for extracted in extracted_rates:
        observation = _to_observation(session, utility_id, source.id, extracted, settings)
        if observation is not None:
            session.add(observation)
            stored.append(observation)
    log.info("document_stored", utility=utility_id, url=document.url, rates=len(stored))
    return stored


def _to_observation(
    session: Session,
    utility_id: str,
    source_document_id: int,
    extracted: ExtractedRate,
    settings: Settings,
) -> RateObservation | None:
    """Build the stored row, or None if this exact value is already recorded for the month."""
    same_month = session.scalars(
        select(RateObservation).where(
            RateObservation.utility_id == utility_id,
            RateObservation.period == extracted.period,
            RateObservation.customer_class == CustomerClass.RESIDENTIAL,
        )
    ).all()
    # A second source for a month is kept only if it adds the generation charge.
    if any(
        existing.rate_per_kwh == extracted.rate_per_kwh
        and existing.rate_basis == extracted.rate_basis
        and (
            extracted.generation_charge_per_kwh is None
            or existing.generation_charge_per_kwh is not None
        )
        for existing in same_month
    ):
        return None

    previous = session.scalars(
        select(RateObservation)
        .where(
            RateObservation.utility_id == utility_id,
            RateObservation.period == previous_period(extracted.period),
            RateObservation.status == RateStatus.PUBLISHED,
        )
        .order_by(RateObservation.id.desc())
    ).first()
    status, flags = validate(
        extracted, Context(settings, previous.rate_per_kwh if previous else None)
    )
    return RateObservation(
        utility_id=utility_id,
        customer_class=CustomerClass.RESIDENTIAL,
        source_document_id=source_document_id,
        status=status,
        flags=flags,
        **extracted.model_dump(),
    )
