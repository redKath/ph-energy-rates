import logging

import typer
import uvicorn

from ph_energy_data.collectors.fetcher import HttpFetcher
from ph_energy_data.collectors.registry import discover_collectors
from ph_energy_data.config import get_settings
from ph_energy_data.services.pipeline import run_collector
from ph_energy_data.storage.archive import LocalArchive
from ph_energy_data.storage.db import make_session_factory

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """PH energy rates pipeline."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API server."""
    uvicorn.run("ph_energy_data.api.app:app", host=host, port=port)


@app.command()
def collect(utility_id: str) -> None:
    """Collect and store the latest rates for one utility."""
    collectors = discover_collectors()
    if utility_id not in collectors:
        raise typer.BadParameter(f"unknown utility {utility_id!r}; known: {sorted(collectors)}")
    settings = get_settings()
    run = run_collector(
        collectors[utility_id],
        session_factory=make_session_factory(settings.database_url),
        fetcher=HttpFetcher(settings.user_agent, settings.fetch_delay_seconds),
        archive=LocalArchive(settings.archive_dir),
        settings=settings,
    )
    typer.echo(
        f"{run.status}: fetched={run.documents_fetched} created={run.rates_created} "
        f"flagged={run.rates_flagged}"
    )
    if run.error:
        typer.echo(run.error, err=True)
        raise typer.Exit(1)
