from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ph_energy_data.domain import models as domain
from ph_energy_data.domain.enums import RateStatus, UtilityType
from ph_energy_data.storage.models import RateObservation, SourceDocument, Utility


@dataclass(frozen=True)
class RateFilter:
    utility_id: str | None = None
    period_from: str | None = None
    period_to: str | None = None
    status: RateStatus | None = RateStatus.PUBLISHED


def list_utilities(
    session: Session, *, utility_type: UtilityType | None = None, province: str | None = None
) -> list[domain.Utility]:
    query = select(Utility).order_by(Utility.id)
    if utility_type is not None:
        query = query.where(Utility.type == utility_type)
    if province is not None:
        # PSGC codes are hierarchical, so a province code is a prefix of its utilities' codes.
        query = query.where(Utility.psgc_code.startswith(province, autoescape=True))
    return [domain.Utility.model_validate(row) for row in session.scalars(query)]


def get_utility(session: Session, utility_id: str) -> domain.Utility | None:
    row = session.get(Utility, utility_id)
    return domain.Utility.model_validate(row) if row else None


def _ordered_rates(rate_filter: RateFilter) -> Select[RateObservation]:
    query = select(RateObservation).order_by(
        RateObservation.utility_id, RateObservation.period, RateObservation.id
    )
    if rate_filter.utility_id is not None:
        query = query.where(RateObservation.utility_id == rate_filter.utility_id)
    if rate_filter.period_from is not None:
        query = query.where(RateObservation.period >= rate_filter.period_from)
    if rate_filter.period_to is not None:
        query = query.where(RateObservation.period <= rate_filter.period_to)
    if rate_filter.status is not None:
        query = query.where(RateObservation.status == rate_filter.status)
    return query


def list_rates(
    session: Session, rate_filter: RateFilter, *, limit: int, offset: int
) -> tuple[list[domain.RateObservation], int]:
    query = _ordered_rates(rate_filter)
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    rows = session.scalars(query.limit(limit).offset(offset))
    return [domain.RateObservation.model_validate(row) for row in rows], total or 0


def get_rate(
    session: Session, rate_id: int
) -> tuple[domain.RateObservation, domain.SourceDocument] | None:
    row = session.execute(
        select(RateObservation, SourceDocument)
        .join(SourceDocument, RateObservation.source_document_id == SourceDocument.id)
        .where(RateObservation.id == rate_id)
    ).first()
    if row is None:
        return None
    rate, source = row
    return domain.RateObservation.model_validate(rate), domain.SourceDocument.model_validate(source)


def published_rates_with_sources(
    session: Session,
) -> list[tuple[domain.RateObservation, domain.SourceDocument]]:
    rows = session.execute(
        select(RateObservation, SourceDocument)
        .join(SourceDocument, RateObservation.source_document_id == SourceDocument.id)
        .where(RateObservation.status == RateStatus.PUBLISHED)
        .order_by(RateObservation.utility_id, RateObservation.period, RateObservation.id)
    )
    return [
        (domain.RateObservation.model_validate(rate), domain.SourceDocument.model_validate(source))
        for rate, source in rows
    ]
