from decimal import Decimal
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PH_ENERGY_")

    database_url: str = "postgresql+psycopg://ph_energy:ph_energy@127.0.0.1:5432/ph_energy"
    archive_dir: Path = Path("data/archive")
    user_agent: str = "ph-energy-data/0.1 (+https://github.com/redKath/ph-energy-rates)"
    fetch_delay_seconds: float = 2.0

    # Validation thresholds (PHP per kWh).
    rate_min: Decimal = Decimal("5")
    rate_max: Decimal = Decimal("40")
    mom_change_threshold: Decimal = Decimal("0.30")
    confidence_min: float = 0.8


def get_settings() -> Settings:
    return Settings()
