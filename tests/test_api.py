import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.api.app import build_app
from ph_energy_data.config import Settings
from ph_energy_data.services.pipeline import run_collector
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.models import Utility
from tests.conftest import STUB_PAGE, FakeFetcher, StubCollector


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], archive: LocalArchive, settings: Settings
) -> TestClient:
    run_collector(
        StubCollector(),
        session_factory=session_factory,
        fetcher=FakeFetcher(STUB_PAGE),
        archive=archive,
        settings=settings,
    )
    return TestClient(build_app(session_factory))


def test_utilities(client: TestClient) -> None:
    body = client.get("/v1/utilities").json()
    assert [utility["id"] for utility in body] == ["stub"]
    assert client.get("/v1/utilities", params={"type": "private_du"}).json() == []


def test_unknown_utility_uses_error_format(client: TestClient) -> None:
    response = client.get("/v1/utilities/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "utility_not_found"


def test_rates_filter_and_pagination(client: TestClient) -> None:
    body = client.get(
        "/v1/rates", params={"utility_id": "stub", "from": "2026-01", "to": "2026-03"}
    ).json()
    assert [rate["period"] for rate in body["items"]] == ["2026-01", "2026-02", "2026-03"]
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


def test_unknown_rate_uses_error_format(client: TestClient) -> None:
    response = client.get("/v1/rates/999999")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "rate_not_found"


def test_unknown_route_uses_error_format(client: TestClient) -> None:
    response = client.get("/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/v1/rates", {"utility_id": "Not A Slug"}),
        ("/v1/utilities", {"province": "%"}),
        ("/v1/utilities", {"type": "not_a_type"}),
    ],
)
def test_malformed_filters_rejected(client: TestClient, path: str, params: dict[str, str]) -> None:
    response = client.get(path, params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_province_filter_matches_code_prefix(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        stub = session.get(Utility, "stub")
        assert stub is not None
        stub.psgc_code = "0102800000"
        session.commit()
    matches = client.get("/v1/utilities", params={"province": "01028"}).json()
    assert [utility["id"] for utility in matches] == ["stub"]
    assert client.get("/v1/utilities", params={"province": "02"}).json() == []


def test_exports(client: TestClient) -> None:
    exported = client.get("/v1/exports/rates.json").json()
    assert exported["count"] == 12
    assert exported["license"] == "CC BY 4.0"
    rows = list(csv.DictReader(io.StringIO(client.get("/v1/exports/rates.csv").text)))
    assert len(rows) == 12
    assert rows[0]["utility_id"] == "stub"
    assert rows[0]["source_sha256"]
