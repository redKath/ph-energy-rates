from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ph_energy_data.domain.enums import (
    CustomerClass,
    ExtractionMethod,
    RateBasis,
    RateStatus,
    UtilityType,
)
from ph_energy_data.storage.models import RateObservation, SourceDocument, Utility

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def db_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("PH_ENERGY_DATABASE_URL", url)
    return url


def _alembic() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def test_migration_matches_models(db_url: str) -> None:
    command.upgrade(_alembic(), "head")
    command.check(_alembic())


def _rate(source_id: int) -> RateObservation:
    return RateObservation(
        utility_id="beneco",
        period="2026-09",
        customer_class=CustomerClass.RESIDENTIAL,
        rate_per_kwh=Decimal("11.80"),
        rate_basis=RateBasis.PUBLISHED_TOTAL,
        source_document_id=source_id,
        extraction_method=ExtractionMethod.HTML_PARSER,
        extractor_version="beneco-1",
        status=RateStatus.PUBLISHED,
    )


def test_duplicate_observation_rejected(db_url: str) -> None:
    command.upgrade(_alembic(), "head")
    with Session(create_engine(db_url)) as session:
        session.add(Utility(id="beneco", name="BENECO", type=UtilityType.ELECTRIC_COOPERATIVE))
        doc = SourceDocument(
            utility_id="beneco",
            url="https://www.beneco.com.ph/rates.php",
            fetched_at=datetime(2026, 10, 20, tzinfo=UTC),
            content_type="text/html",
            sha256="0" * 64,
            archive_path="data/archive/beneco/x.html",
        )
        session.add(doc)
        session.flush()
        session.add(_rate(doc.id))
        session.flush()
        session.add(_rate(doc.id))
        with pytest.raises(IntegrityError):
            session.flush()
