from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the local OpsCat MVP."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./opscat.db"
    opscat_mode: str = "local"
    report_dir: str = "data/mock_reports"
    night_autopilot_timezone: str = "Asia/Seoul"
    night_autopilot_quiet_start: str = "22:00"
    night_autopilot_quiet_end: str = "07:00"
    night_autopilot_max_automatic_risk: str = "low"
    night_autopilot_max_attempts: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
