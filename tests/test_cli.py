from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog
from typer.testing import CliRunner

from ph_energy_data import cli
from ph_energy_data.domain.enums import RunStatus
from ph_energy_data.services.pipeline import RunSummary

runner = CliRunner()


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("PH_ENERGY_DATABASE_URL", "sqlite://")
    monkeypatch.setenv("PH_ENERGY_ARCHIVE_DIR", str(tmp_path))
    yield
    structlog.reset_defaults()


def _collect_beneco_with(monkeypatch: pytest.MonkeyPatch, summary: RunSummary) -> tuple[int, str]:
    monkeypatch.setattr(cli, "run_collector", lambda *args, **kwargs: summary)
    result = runner.invoke(cli.app, ["collect", "beneco"])
    return result.exit_code, result.output


def test_unknown_utility_is_a_usage_error() -> None:
    result = runner.invoke(cli.app, ["collect", "nope"])
    assert result.exit_code == 2
    assert "unknown utility" in result.output


def test_successful_run_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, output = _collect_beneco_with(
        monkeypatch, RunSummary(RunStatus.SUCCEEDED, 3, 2, 0, None)
    )
    assert exit_code == 0
    assert "succeeded: fetched=3 created=2 flagged=0" in output


def test_failed_run_exits_one_and_prints_error(monkeypatch: pytest.MonkeyPatch) -> None:
    summary = RunSummary(RunStatus.FAILED, 1, 0, 0, "some/url: ExtractionError: bad layout")
    exit_code, output = _collect_beneco_with(monkeypatch, summary)
    assert exit_code == 1
    assert "bad layout" in output
