"""Central, environment-driven configuration for local, CI and production runs."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KCP_", env_file=".env", extra="ignore")

    raw_data_dir: Path = Path("data/raw")
    staging_data_dir: Path = Path("data/staging")
    curated_data_dir: Path = Path("data/curated")
    database_url: str = "postgresql+psycopg2://kcp:kcp@localhost:5433/kcp"
    sources_config_path: Path = Path("config/sources.yaml")
    request_timeout_seconds: float = 30.0
    max_retries: int = 4
    retry_backoff_seconds: float = 2.0
    max_download_bytes: int = 50 * 1024 * 1024
    user_agent: str = "knbs-cbk-pipeline/0.2 (+https://github.com/Victor-Kipruto-Rop)"
    redis_url: str | None = None
    alert_webhook_url: str | None = None
    freshness_sla_hours: int = 48
    db_host: str = "localhost"
    db_port: int = 5433
    db_user: str = "kcp"
    db_password: str = "kcp"
    db_name: str = "kcp"

    def ensure_dirs(self) -> None:
        for directory in (self.raw_data_dir, self.staging_data_dir, self.curated_data_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
