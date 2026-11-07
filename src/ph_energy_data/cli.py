import logging
import sys

import structlog
import typer
import uvicorn

from ph_energy_data.collectors.fetcher import HttpFetcher
from ph_energy_data.collectors.registry import build_collectors
from ph_energy_data.config import get_settings
from ph_energy_data.services.pipeline import run_collector
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.db import make_session_factory

app = typer.Typer(no_args_is_help=True)


def _stderr_logger(*_: object) -> structlog.WriteLogger:
    return structlog.WriteLogger(file=sys.stderr)


def _configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=_stderr_logger,
    )


@app.callback()
def main() -> None:
    """PH energy rates pipeline."""
    _configure_logging()


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API server."""
    uvicorn.run("ph_energy_data.api.app:create_app", host=host, port=port, factory=True)


@app.command()
def collect(utility_id: str) -> None:
    """Collect and store the latest rates for one utility."""
    collectors = build_collectors()
    if utility_id not in collectors:
        raise typer.BadParameter(f"unknown utility {utility_id!r}; known: {sorted(collectors)}")
    settings = get_settings()
    summary = run_collector(
        collectors[utility_id],
        session_factory=make_session_factory(settings.database_url),
        fetcher=HttpFetcher(settings.user_agent, settings.fetch_delay_seconds),
        archive=LocalArchive(settings.archive_dir),
        settings=settings,
    )
    typer.echo(
        f"{summary.status}: fetched={summary.documents_fetched} created={summary.rates_created} "
        f"flagged={summary.rates_flagged}"
    )
    if summary.error:
        typer.echo(summary.error, err=True)
        raise typer.Exit(1)
