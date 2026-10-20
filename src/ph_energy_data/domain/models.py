from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ph_energy_data.domain.enums import (
    CustomerClass,
    ExtractionMethod,
    RateBasis,
    RateStatus,
    RunStatus,
    UtilityType,
)

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
# Billing month, ISO 8601 year-month.
Period = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
PhpPerKwh = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=4)]


class _Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Utility(_Model):
    id: Slug
    name: str
    type: UtilityType
    psgc_code: str | None = None
    aliases: list[str] = []
    erc_id: str | None = None
    nea_id: str | None = None


class SourceDocument(_Model):
    id: int | None = None
    utility_id: Slug
    url: str
    fetched_at: datetime
    content_type: str
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    archive_path: str


class ExtractedRate(_Model):
    """Candidate value from an extractor; not a fact until it passes validation."""

    period: Period
    rate_per_kwh: PhpPerKwh
    rate_basis: RateBasis
    generation_charge_per_kwh: PhpPerKwh | None = None
    extraction_method: ExtractionMethod
    extractor_version: str
    model: str | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None


class RateObservation(_Model):
    id: int | None = None
    utility_id: Slug
    period: Period
    customer_class: CustomerClass = CustomerClass.RESIDENTIAL
    rate_per_kwh: PhpPerKwh
    rate_basis: RateBasis
    generation_charge_per_kwh: PhpPerKwh | None = None
    currency: str = "PHP"
    source_document_id: int
    extraction_method: ExtractionMethod
    extractor_version: str
    model: str | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    status: RateStatus
    flags: list[str] = []
    created_at: datetime | None = None


class PipelineRun(_Model):
    id: int | None = None
    utility_id: Slug
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    documents_fetched: int = 0
    rates_created: int = 0
    rates_flagged: int = 0
    error: str | None = None
