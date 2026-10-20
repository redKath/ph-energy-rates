import csv
import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.api.app import app
from ph_energy_data.api.deps import get_session
from ph_energy_data.config import Settings
from ph_energy_data.services.pipeline import run_collector
from ph_energy_data.storage.archive import LocalArchive
from tests.conftest import STUB_PAGE, FakeFetcher, StubCollector


@pytest.fixture
def client(session_factory: sessionmaker[Session], archive: LocalArchive) -> Iterator[TestClient]:
    run_collector(
        StubCollector(),
        session_factory=session_factory,
        fetcher=FakeFetcher(STUB_PAGE),
        archive=archive,
        settings=Settings(),
    )

    def override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_utilities(client: TestClient) -> None:
    body = client.get("/v1/utilities").json()
    assert [u["id"] for u in body] == ["stub"]
    assert client.get("/v1/utilities", params={"type": "private_du"}).json() == []


def test_unknown_utility_uses_error_format(client: TestClient) -> None:
    response = client.get("/v1/utilities/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "utility_not_found"


def test_rates_filter_and_pagination(client: TestClient) -> None:
    body = client.get(
        "/v1/rates", params={"utility_id": "stub", "from": "2026-01", "to": "2026-03"}
    ).json()
    assert [r["period"] for r in body["items"]] == ["2026-01", "2026-02", "2026-03"]
    assert body["pagination"] == {"total": 3, "limit": 50, "offset": 0}
    page = client.get("/v1/rates", params={"limit": 5, "offset": 10}).json()
    assert len(page["items"]) == 2
    assert page["pagination"]["total"] == 12


def test_rate_values_are_numbers(client: TestClient) -> None:
    first = client.get("/v1/rates", params={"limit": 1}).json()["items"][0]
    assert first["rate_per_kwh"] == 7.55


def test_invalid_period_rejected(client: TestClient) -> None:
    response = client.get("/v1/rates", params={"from": "May 2026"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_rate_detail_has_provenance(client: TestClient) -> None:
    rate_id = client.get("/v1/rates", params={"limit": 1}).json()["items"][0]["id"]
    source = client.get(f"/v1/rates/{rate_id}").json()["source"]
    assert source["url"] == "https://stub.test/rates"
    assert len(source["sha256"]) == 64


def test_exports(client: TestClient) -> None:
    exported = client.get("/v1/exports/rates.json").json()
    assert exported["count"] == 12
    assert exported["license"] == "CC BY 4.0"
    rows = list(csv.DictReader(io.StringIO(client.get("/v1/exports/rates.csv").text)))
    assert len(rows) == 12
    assert rows[0]["utility_id"] == "stub"
    assert rows[0]["source_sha256"]
