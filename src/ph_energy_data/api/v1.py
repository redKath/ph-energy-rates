import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ph_energy_data.api.deps import get_session
from ph_energy_data.api.errors import ApiError
from ph_energy_data.api.schemas import (
    ExportRow,
    PaginationOut,
    RateDetailOut,
    RateOut,
    RatePage,
    SourceOut,
    UtilityOut,
)
from ph_energy_data.domain.enums import RateStatus, UtilityType
from ph_energy_data.services import rates as service

router = APIRouter(prefix="/v1")
SessionDep = Annotated[Session, Depends(get_session)]
PeriodQuery = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


@router.get("/utilities", response_model=list[UtilityOut])
def list_utilities(
    session: SessionDep,
    type: UtilityType | None = None,
    province: Annotated[str | None, Query(description="PSGC province code prefix")] = None,
) -> list[UtilityOut]:
    rows = service.list_utilities(session, type=type, province=province)
    return [UtilityOut.model_validate(u) for u in rows]


@router.get("/utilities/{utility_id}", response_model=UtilityOut)
def get_utility(utility_id: str, session: SessionDep) -> UtilityOut:
    utility = service.get_utility(session, utility_id)
    if utility is None:
        raise ApiError(404, "utility_not_found", f"no utility {utility_id!r}")
    return UtilityOut.model_validate(utility)


@router.get("/rates", response_model=RatePage)
def list_rates(
    session: SessionDep,
    utility_id: str | None = None,
    from_: Annotated[PeriodQuery, Query(alias="from")] = None,
    to: PeriodQuery = None,
    status: RateStatus | None = RateStatus.PUBLISHED,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RatePage:
    rows, total = service.list_rates(
        session, service.RateFilter(utility_id, from_, to, status), limit=limit, offset=offset
    )
    return RatePage(
        items=[RateOut.model_validate(r) for r in rows],
        pagination=PaginationOut(total=total, limit=limit, offset=offset),
    )


@router.get("/rates/{rate_id}", response_model=RateDetailOut)
def get_rate(rate_id: int, session: SessionDep) -> RateDetailOut:
    found = service.get_rate(session, rate_id)
    if found is None:
        raise ApiError(404, "rate_not_found", f"no rate {rate_id}")
    rate, source = found
    return RateDetailOut(
        **RateOut.model_validate(rate).model_dump(), source=SourceOut.model_validate(source)
    )


def _export_rows(session: Session) -> list[dict[str, object]]:
    return [
        ExportRow(
            observation_id=r.id,
            source_url=s.url,
            source_fetched_at=s.fetched_at,
            source_sha256=s.sha256,
            **RateOut.model_validate(r).model_dump(
                include=set(ExportRow.model_fields) - {"observation_id"}
            ),
        ).model_dump(mode="json")
        for r, s in service.published_rates_with_sources(session)
    ]


@router.get("/exports/rates.json")
def export_json(session: SessionDep) -> dict[str, object]:
    rows = _export_rows(session)
    return {"license": "CC BY 4.0", "count": len(rows), "rates": rows}


@router.get("/exports/rates.csv")
def export_csv(session: SessionDep) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(ExportRow.model_fields))
    writer.writeheader()
    writer.writerows(_export_rows(session))
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="rates.csv"'},
    )
