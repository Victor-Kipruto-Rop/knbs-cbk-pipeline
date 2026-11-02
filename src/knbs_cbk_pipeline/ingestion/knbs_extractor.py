"""KNBS bulletin discovery and download with strict file validation."""
from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from config.settings import settings
from knbs_cbk_pipeline.ingestion.base_extractor import BaseExtractor, ExtractionResult

_FORMATS = {
    "xlsx": (".xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK"),
    "xls": (".xls", "application/vnd.ms-excel", bytes.fromhex("D0CF11E0A1B11AE1")),
    "pdf": (".pdf", "application/pdf", b"%PDF"),
    "csv": (".csv", "text/csv", None),
}


class KNBSExtractor(BaseExtractor):
    def _discover_download(self, page_url: str, html: bytes, expected_format: str, keywords: list[str]) -> str:
        soup = BeautifulSoup(html, "lxml")
        candidates = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).strip()
            label = anchor.get_text(" ", strip=True).lower()
            target = urljoin(page_url, href)
            path = target.lower().split("?", 1)[0]
            if path.endswith(_FORMATS[expected_format][0]) or any(k.lower() in label for k in keywords):
                candidates.append(target)
        if not candidates:
            raise ValueError(
                f"KNBS landing page did not expose a {expected_format.upper()} download link; "
                "inspect the bulletin page and update download_link_keywords"
            )
        return candidates[0]

    def fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        expected = str(source_config.get("format", "xlsx")).lower()
        if expected not in _FORMATS:
            raise ValueError(f"Unsupported KNBS format: {expected}")
        response = self._get(source_config["endpoint"])
        expected_ext, expected_type, signature = _FORMATS[expected]
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        content = response.content
        source_url = str(response.url)

        looks_like_expected = (signature and content.startswith(signature)) or (
            expected == "csv" and "text/csv" in content_type
        )
        if not looks_like_expected:
            if "html" not in content_type and not content.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<")):
                raise ValueError(f"KNBS response is not a valid {expected.upper()} file (content-type={content_type})")
            download_url = self._discover_download(
                source_url, content, expected, source_config.get("download_link_keywords", [])
            )
            response = self._get(download_url)
            content, source_url = response.content, str(response.url)
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()

        if not content or len(content) > settings.max_download_bytes:
            raise ValueError(f"KNBS download size is invalid: {len(content)} bytes")
        if signature and not content.startswith(signature):
            raise ValueError(f"Downloaded KNBS file failed {expected.upper()} signature validation")
        if expected == "csv" and not (content_type == "text/csv" or b"," in content[:4096]):
            raise ValueError("Downloaded KNBS CSV does not resemble a CSV document")

        return ExtractionResult(
            source_id=source_config["id"],
            fetched_at=dt.datetime.now(dt.timezone.utc),
            content=content,
            content_type=expected_type,
            source_url=source_url,
            metadata={
                "status_code": response.status_code,
                "declared_format": expected,
                "validated_extension": expected_ext,
                "content_length": len(content),
            },
        )
