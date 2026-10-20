from decimal import Decimal

from ph_energy_data.config import Settings
from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, RateStatus
from ph_energy_data.domain.models import ExtractedRate
from ph_energy_data.validation.rules import Context, validate

SETTINGS = Settings()


def _rate(value: str = "10", **overrides: object) -> ExtractedRate:
    fields: dict[str, object] = {
        "period": "2026-09",
        "rate_per_kwh": Decimal(value),
        "rate_basis": RateBasis.PUBLISHED_TOTAL,
        "extraction_method": ExtractionMethod.HTML_PARSER,
        "extractor_version": "test-1",
    }
    return ExtractedRate(**{**fields, **overrides})  # type: ignore[arg-type]


def _validate(rate: ExtractedRate, previous: str | None = None) -> tuple[RateStatus, list[str]]:
    return validate(rate, Context(SETTINGS, Decimal(previous) if previous else None))


def test_normal_rate_published() -> None:
    assert _validate(_rate("10"), "9.5") == (RateStatus.PUBLISHED, [])


def test_out_of_range_rejected() -> None:
    assert _validate(_rate("4.99")) == (RateStatus.REJECTED, ["rate_out_of_range"])
    assert _validate(_rate("40.01")) == (RateStatus.REJECTED, ["rate_out_of_range"])


def test_large_month_over_month_change_flagged() -> None:
    assert _validate(_rate("13.1"), "10") == (RateStatus.FLAGGED, ["mom_change_exceeds_threshold"])
    assert _validate(_rate("7"), "10")[0] is RateStatus.PUBLISHED


def test_generation_must_be_below_total() -> None:
    rate = _rate("10", generation_charge_per_kwh=Decimal("10"))
    assert _validate(rate) == (RateStatus.REJECTED, ["generation_not_below_total"])


def test_low_confidence_flagged() -> None:
    assert _validate(_rate(confidence=0.5)) == (RateStatus.FLAGGED, ["low_confidence"])
