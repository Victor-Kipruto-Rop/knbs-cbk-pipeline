"""Raw-to-warehouse transformation with deterministic replay and failure propagation."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable

import pandas as pd
import structlog
from sqlalchemy import Engine

from config.settings import settings
from knbs_cbk_pipeline.transformation.cleaners.cbk_cleaner import clean_fx_rates, clean_key_rates
from knbs_cbk_pipeline.transformation.cleaners.knbs_cleaner import clean_cpi, clean_gdp
from knbs_cbk_pipeline.transformation.transformers.standardize import standardize
from knbs_cbk_pipeline.transformation.validators.schema_checks import validate_tidy_frame
from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import ensure_schema, get_engine, upsert_indicators

log = structlog.get_logger()
CleanerFn = Callable[[bytes, dt.datetime], pd.DataFrame]
_CLEANERS: dict[str, CleanerFn] = {
    "cbk_fx_rates": clean_fx_rates,
    "cbk_key_rates": clean_key_rates,
    "knbs_cpi": clean_cpi,
    "knbs_gdp_quarterly": clean_gdp,
}


def _latest_raw_file(source_id: str, raw_dir: Path) -> Path | None:
    candidates = [p for p in (raw_dir / source_id).rglob("*") if p.is_file() and not p.name.endswith(".meta.json")]
    if not candidates:
        return None

    def fetched_at(path: Path) -> dt.datetime:
        sidecar = path.with_suffix(path.suffix + ".meta.json")
        if sidecar.exists():
            try:
                value = json.loads(sidecar.read_text(encoding="utf-8"))["fetched_at"]
                return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)

    return max(candidates, key=fetched_at)


def transform_and_load_source(source_id: str, engine: Engine, raw_dir: Path | None = None) -> int:
    raw_dir = raw_dir or settings.raw_data_dir
    cleaner = _CLEANERS.get(source_id)
    if cleaner is None:
        raise ValueError(f"No cleaner registered for source_id '{source_id}'")
    raw_file = _latest_raw_file(source_id, raw_dir)
    if raw_file is None:
        raise FileNotFoundError(f"No raw artifact found for source '{source_id}' under {raw_dir}")

    sidecar = raw_file.with_suffix(raw_file.suffix + ".meta.json")
    fetched_at = dt.datetime.fromtimestamp(raw_file.stat().st_mtime, tz=dt.timezone.utc)
    if sidecar.exists():
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
            fetched_at = dt.datetime.fromisoformat(metadata["fetched_at"].replace("Z", "+00:00"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid raw metadata sidecar for {raw_file}: {exc}") from exc

    tidy = cleaner(raw_file.read_bytes(), fetched_at)
    validation = validate_tidy_frame(tidy, source_id=source_id)
    if validation.warnings:
        log.warning("transform.validation_warnings", source_id=source_id, warnings=validation.warnings)
    validation.raise_if_invalid()
    clean_df = standardize(tidy, ingested_at=fetched_at)
    written = upsert_indicators(clean_df, engine)
    log.info("transform.loaded", source_id=source_id, rows=written, raw_path=str(raw_file))
    return written


def transform_and_load_all(source_ids: list[str] | None = None, engine: Engine | None = None) -> dict[str, int]:
    engine = engine or get_engine()
    ensure_schema(engine)
    ids = source_ids or list(_CLEANERS)
    results: dict[str, int] = {}
    for source_id in ids:
        try:
            results[source_id] = transform_and_load_source(source_id, engine)
        except Exception as exc:
            log.exception("transform.failed", source_id=source_id, error=str(exc))
            results[source_id] = -1
    return results


if __name__ == "__main__":
    results = transform_and_load_all()
    raise SystemExit(1 if any(count < 0 for count in results.values()) else 0)
