from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ph_energy_data.domain.enums import RateStatus, UtilityType
from ph_energy_data.storage.models import RateObservation, SourceDocument, Utility


@dataclass(frozen=True)
class RateFilter:
    utility_id: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    status: RateStatus | None = RateStatus.PUBLISHED


def list_utilities(
    session: Session, *, type: UtilityType | None = None, province: str | None = None
) -> list[Utility]:
    query = select(Utility).order_by(Utility.id)
    if type is not None:
        query = query.where(Utility.type == type)
    if province is not None:
        # PSGC codes are hierarchical, so a province code is a prefix of its utilities' codes.
        query = query.where(Utility.psgc_code.startswith(province))
    return list(session.scalars(query))


def get_utility(session: Session, utility_id: str) -> Utility | None:
    return session.get(Utility, utility_id)


def _ordered_rates(f: RateFilter) -> Select[RateObservation]:
    query = select(RateObservation).order_by(
        RateObservation.utility_id, RateObservation.period, RateObservation.id
    )
    if f.utility_id is not None:
        query = query.where(RateObservation.utility_id == f.utility_id)
    if f.period_from is not None:
        query = query.where(RateObservation.period >= f.period_from)
    if f.period_to is not None:
        query = query.where(RateObservation.period <= f.period_to)
    if f.status is not None:
        query = query.where(RateObservation.status == f.status)
    return query


def list_rates(
    session: Session, f: RateFilter, *, limit: int, offset: int
) -> tuple[list[RateObservation], int]:
    query = _ordered_rates(f)
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return list(session.scalars(query.limit(limit).offset(offset))), total or 0


def get_rate(session: Session, rate_id: int) -> tuple[RateObservation, SourceDocument] | None:
    row = session.execute(
        select(RateObservation, SourceDocument)
        .join(SourceDocument, RateObservation.source_document_id == SourceDocument.id)
        .where(RateObservation.id == rate_id)
    ).first()
    return (row[0], row[1]) if row else None


def published_rates_with_sources(session: Session) -> list[tuple[RateObservation, SourceDocument]]:
    rows = session.execute(
        select(RateObservation, SourceDocument)
        .join(SourceDocument, RateObservation.source_document_id == SourceDocument.id)
        .where(RateObservation.status == RateStatus.PUBLISHED)
        .order_by(RateObservation.utility_id, RateObservation.period, RateObservation.id)
    )
    return [(r[0], r[1]) for r in rows]
