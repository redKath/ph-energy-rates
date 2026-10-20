import hashlib
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.collectors.base import Collector, FetchedDocument, Fetcher
from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import CustomerClass, RateStatus, RunStatus
from ph_energy_data.domain.models import ExtractedRate
from ph_energy_data.domain.periods import previous_period
from ph_energy_data.storage.archive import ArchiveStore
from ph_energy_data.storage.models import PipelineRun, RateObservation, SourceDocument, Utility
from ph_energy_data.validation.rules import Context, validate


def run_collector(
    collector: Collector,
    *,
    session_factory: sessionmaker[Session],
    fetcher: Fetcher,
    archive: ArchiveStore,
    settings: Settings,
) -> PipelineRun:
    """Collect, archive, extract, validate and store one utility's rates. Safe to re-run."""
    utility = collector.utility
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

        fetched = created = flagged = 0
        errors: list[str] = []
        try:
            urls = collector.discover(fetcher)
        except Exception as exc:
            urls = []
            errors.append(f"discover: {type(exc).__name__}: {exc}")
        for url in urls:
            try:
                document = fetcher.get(url)
                fetched += 1
                new_rates = _store_document(session, collector, document, archive, settings)
                session.commit()
            except Exception as exc:
                # One bad document must not block the rest of a backfill.
                session.rollback()
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
                continue
            created += len(new_rates)
            flagged += sum(r.status is not RateStatus.PUBLISHED for r in new_rates)

        run = session.get_one(PipelineRun, run_id)
        run.documents_fetched, run.rates_created, run.rates_flagged = fetched, created, flagged
        run.status = RunStatus.FAILED if errors else RunStatus.SUCCEEDED
        run.error = _summarise(errors)
        run.finished_at = datetime.now(UTC)
        session.commit()
        session.refresh(run)
        session.expunge(run)
        return run


def _summarise(errors: list[str]) -> str | None:
    if not errors:
        return None
    more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
    return "; ".join(errors[:5]) + more


def _store_document(
    session: Session,
    collector: Collector,
    document: FetchedDocument,
    archive: ArchiveStore,
    settings: Settings,
) -> list[RateObservation]:
    """Archive and extract one document unless it was already stored; return new rates."""
    utility_id = collector.utility.id
    sha256 = hashlib.sha256(document.content).hexdigest()
    seen = session.scalar(
        select(SourceDocument.id).where(
            SourceDocument.utility_id == utility_id, SourceDocument.sha256 == sha256
        )
    )
    if seen is not None:
        return []
    # Extract before archiving so an unreadable document leaves nothing behind.
    extracted_rates = sorted(collector.extract(document), key=lambda r: r.period)
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
    stored = []
    for extracted in extracted_rates:
        observation = _to_observation(session, utility_id, source.id, extracted, settings)
        if observation is not None:
            session.add(observation)
            stored.append(observation)
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
        o.rate_per_kwh == extracted.rate_per_kwh
        and o.rate_basis == extracted.rate_basis
        and (extracted.generation_charge_per_kwh is None or o.generation_charge_per_kwh is not None)
        for o in same_month
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
