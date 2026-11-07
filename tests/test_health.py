from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.api.app import build_app


def test_health(session_factory: sessionmaker[Session]) -> None:
    response = TestClient(build_app(session_factory)).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
