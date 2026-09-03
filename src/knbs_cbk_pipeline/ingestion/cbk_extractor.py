"""
CBK-specific extraction logic.

Two fetch modes registered in config/sources.yaml route here:
  - "api_json"     -> cbk_fx_rates, via the Frankfurter API's CBK provider
  - "html_scrape"  -> cbk_key_rates, scraped off the CBK homepage widget

Keeping both in one extractor (rather than one per fetch_mode) mirrors how
CBK data actually behaves: same institution, wildly different publishing
maturity per dataset.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from knbs_cbk_pipeline.ingestion.base_extractor import BaseExtractor, ExtractionResult


class CBKExtractor(BaseExtractor):
    def fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        fetch_mode = source_config["fetch_mode"]
        if fetch_mode == "api_json":
            return self._fetch_api_json(source_config)
        if fetch_mode == "html_scrape":
            return self._fetch_html(source_config)
        raise ValueError(f"Unsupported fetch_mode for CBKExtractor: {fetch_mode}")

    def _fetch_api_json(self, source_config: dict[str, Any]) -> ExtractionResult:
        response = self._get(source_config["endpoint"], params=source_config.get("params"))
        return ExtractionResult(
            source_id=source_config["id"],
            fetched_at=dt.datetime.now(dt.timezone.utc),
            content=response.content,
            content_type="application/json",
            source_url=str(response.url),
            metadata={"status_code": response.status_code},
        )

    def _fetch_html(self, source_config: dict[str, Any]) -> ExtractionResult:
        response = self._get(source_config["endpoint"])
        return ExtractionResult(
            source_id=source_config["id"],
            fetched_at=dt.datetime.now(dt.timezone.utc),
            content=response.content,
            content_type="text/html",
            source_url=str(response.url),
            metadata={"status_code": response.status_code},
        )
