from pathlib import Path

import pytest

from ph_energy_data.config import Settings


def test_env_file_may_contain_keys_for_other_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text(
        "POSTGRES_PASSWORD=secret\nANTHROPIC_API_KEY=\nPH_ENERGY_DATABASE_URL=sqlite://\n"
    )
    monkeypatch.chdir(tmp_path)
    assert Settings().database_url == "sqlite://"
