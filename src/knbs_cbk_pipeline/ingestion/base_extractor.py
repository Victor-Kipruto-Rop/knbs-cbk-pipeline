"""Shared HTTP extraction behaviour with bounded retries and response limits."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Any
import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config.settings import settings

log = structlog.get_logger()

@dataclass
class ExtractionResult:
    source_id: str
    fetched_at: dt.datetime
    content: bytes
    content_type: str
    source_url: str
    metadata: dict[str, Any] = field(default_factory=dict)

class ExtractionError(Exception):
    """Raised when a source cannot be fetched after all retries are exhausted."""

class BaseExtractor:
    def __init__(self) -> None:
        self._client = httpx.Client(timeout=settings.request_timeout_seconds, headers={"User-Agent": settings.user_agent}, follow_redirects=True)

    def __enter__(self) -> "BaseExtractor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    @retry(stop=stop_after_attempt(settings.max_retries), wait=wait_exponential(multiplier=settings.retry_backoff_seconds, min=1, max=30), retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)), reraise=True)
    def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        log.info("extractor.request", url=url, params=params)
        response = self._client.get(url, params=params)
        response.raise_for_status()
        if len(response.content) > settings.max_download_bytes:
            raise ValueError(f"Response from {response.url} exceeds configured limit ({len(response.content)} > {settings.max_download_bytes} bytes)")
        return response

    def fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        raise NotImplementedError("Subclasses must implement fetch()")

    def safe_fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        try:
            return self.fetch(source_config)
        except Exception as exc:
            log.exception("extractor.failed", source_id=source_config.get("id"), error=str(exc))
            raise ExtractionError(f"Failed to extract source '{source_config.get('id')}': {exc}") from exc
