from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from ph_energy_data.api.errors import install_error_handlers
from ph_energy_data.api.v1 import router as v1
from ph_energy_data.config import get_settings
from ph_energy_data.storage.db import make_session_factory


def build_app(session_factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI(title="PH Energy Rates", version="0.1.0")
    app.state.session_factory = session_factory
    install_error_handlers(app)
    app.include_router(v1)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_app() -> FastAPI:
    """Entry point for uvicorn's `--factory` mode."""
    return build_app(make_session_factory(get_settings().database_url))
