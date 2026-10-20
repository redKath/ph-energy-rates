from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from ph_energy_data.domain.enums import (
    CustomerClass,
    ExtractionMethod,
    RateBasis,
    RateStatus,
    UtilityType,
)

# Rates are PHP per kWh to 4 decimals; JSON consumers get a number, not a string.
Rate = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UtilityOut(_Out):
    id: str
    name: str
    type: UtilityType
    psgc_code: str | None
    aliases: list[str]
    erc_id: str | None
    nea_id: str | None


class RateOut(_Out):
    id: int
    utility_id: str
    period: str
    customer_class: CustomerClass
    rate_per_kwh: Rate
    rate_basis: RateBasis
    generation_charge_per_kwh: Rate | None
    currency: str
    extraction_method: ExtractionMethod
    status: RateStatus
    flags: list[str]
    created_at: datetime


class SourceOut(_Out):
    url: str
    fetched_at: datetime
    content_type: str
    sha256: str


class RateDetailOut(RateOut):
    source: SourceOut


class PaginationOut(BaseModel):
    total: int
    limit: int
    offset: int


class RatePage(BaseModel):
    items: list[RateOut]
    pagination: PaginationOut


class ExportRow(BaseModel):
    observation_id: int
    utility_id: str
    period: str
    customer_class: CustomerClass
    rate_per_kwh: Rate
    rate_basis: RateBasis
    generation_charge_per_kwh: Rate | None
    currency: str
    extraction_method: ExtractionMethod
    source_url: str
    source_fetched_at: datetime
    source_sha256: str
