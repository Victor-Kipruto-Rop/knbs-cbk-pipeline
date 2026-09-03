"""
Central, env-driven configuration for the pipeline.

Nothing here should be hardcoded per-environment — local dev, CI, and
production all read the same code path and differ only by env vars.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KCP_", env_file=".env", extra="ignore")

    # --- Storage paths (local dev / demo mode) ---
    raw_data_dir: Path = Path("data/raw")
    staging_data_dir: Path = Path("data/staging")
    curated_data_dir: Path = Path("data/curated")

    # --- Database ---
    database_url: str = "postgresql+psycopg2://kcp:kcp@localhost:5432/kcp"

    # --- Source registry ---
    sources_config_path: Path = Path("config/sources.yaml")

    # --- HTTP behaviour ---
    request_timeout_seconds: float = 30.0
    max_retries: int = 4
    retry_backoff_seconds: float = 2.0
    user_agent: str = "knbs-cbk-pipeline/0.1 (+https://github.com/Victor-Kipruto-Rop)"

    # --- Observability ---
    alert_webhook_url: str | None = None  # e.g. Slack incoming webhook
    freshness_sla_hours: int = 48

    def ensure_dirs(self) -> None:
        for d in (self.raw_data_dir, self.staging_data_dir, self.curated_data_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
