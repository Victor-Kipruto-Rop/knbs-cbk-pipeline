"""
KNBS-specific extraction logic.

KNBS doesn't expose an API — datasets (CPI, GDP, etc.) are published as
downloadable Excel/PDF bulletins. This extractor just downloads the file
as-is; format-specific parsing happens downstream in transformation/cleaners.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from knbs_cbk_pipeline.ingestion.base_extractor import BaseExtractor, ExtractionResult

_CONTENT_TYPE_BY_FORMAT = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "pdf": "application/pdf",
}


class KNBSExtractor(BaseExtractor):
    def fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        response = self._get(source_config["endpoint"])
        declared_format = source_config.get("format", "xlsx")
        content_type = response.headers.get(
            "content-type", _CONTENT_TYPE_BY_FORMAT.get(declared_format, "application/octet-stream")
        ).split(";")[0]

        return ExtractionResult(
            source_id=source_config["id"],
            fetched_at=dt.datetime.now(dt.timezone.utc),
            content=response.content,
            content_type=content_type,
            source_url=str(response.url),
            metadata={"status_code": response.status_code, "declared_format": declared_format},
        )
