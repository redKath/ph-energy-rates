from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ph_energy_data.domain.enums import ExtractionMethod, RateBasis, RateStatus
from ph_energy_data.domain.models import RateObservation


def _rate(**overrides: object) -> RateObservation:
    fields: dict[str, object] = {
        "utility_id": "beneco",
        "period": "2026-09",
        "rate_per_kwh": Decimal("11.80"),
        "rate_basis": RateBasis.PUBLISHED_TOTAL,
        "source_document_id": 1,
        "extraction_method": ExtractionMethod.HTML_PARSER,
        "extractor_version": "beneco-1",
        "status": RateStatus.PUBLISHED,
        "created_at": datetime(2026, 10, 20, tzinfo=UTC),
    }
    return RateObservation(**{**fields, **overrides})  # type: ignore[arg-type]


@pytest.mark.parametrize("period", ["2026-09", "2018-01", "2026-12"])
def test_valid_period(period: str) -> None:
    assert _rate(period=period).period == period


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "2026-9", "26-09", "May 2026", ""])
def test_invalid_period(period: str) -> None:
    with pytest.raises(ValidationError):
        _rate(period=period)


def test_negative_rate_rejected() -> None:
    with pytest.raises(ValidationError):
        _rate(rate_per_kwh=Decimal("-1"))


def test_bad_utility_slug_rejected() -> None:
    with pytest.raises(ValidationError):
        _rate(utility_id="Meralco Inc")
