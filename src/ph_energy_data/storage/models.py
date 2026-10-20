from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ph_energy_data.domain.enums import (
    CustomerClass,
    ExtractionMethod,
    RateBasis,
    RateStatus,
    RunStatus,
    UtilityType,
)


def _enum[E: StrEnum](cls: type[E]) -> Enum:
    # Stored as text with a CHECK constraint so SQLite and Postgres behave the same.
    return Enum(
        cls,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        name=f"ck_{cls.__name__.lower()}",
    )


class Base(DeclarativeBase):
    pass


class Utility(Base):
    __tablename__ = "utility"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[UtilityType] = mapped_column(_enum(UtilityType))
    psgc_code: Mapped[str | None] = mapped_column(String(16))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    erc_id: Mapped[str | None] = mapped_column(String(64))
    nea_id: Mapped[str | None] = mapped_column(String(64))


class SourceDocument(Base):
    __tablename__ = "source_document"
    __table_args__ = (UniqueConstraint("utility_id", "sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[str] = mapped_column(ForeignKey("utility.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_type: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    archive_path: Mapped[str] = mapped_column(Text)


class RateObservation(Base):
    __tablename__ = "rate_observation"
    __table_args__ = (
        UniqueConstraint("utility_id", "period", "customer_class", "source_document_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[str] = mapped_column(ForeignKey("utility.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    customer_class: Mapped[CustomerClass] = mapped_column(_enum(CustomerClass))
    rate_per_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    rate_basis: Mapped[RateBasis] = mapped_column(_enum(RateBasis))
    generation_charge_per_kwh: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    currency: Mapped[str] = mapped_column(String(3), default="PHP")
    source_document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"))
    extraction_method: Mapped[ExtractionMethod] = mapped_column(_enum(ExtractionMethod))
    extractor_version: Mapped[str] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float | None] = mapped_column()
    status: Mapped[RateStatus] = mapped_column(_enum(RateStatus), index=True)
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(UTC)
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    utility_id: Mapped[str] = mapped_column(ForeignKey("utility.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus))
    documents_fetched: Mapped[int] = mapped_column(default=0)
    rates_created: Mapped[int] = mapped_column(default=0)
    rates_flagged: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
