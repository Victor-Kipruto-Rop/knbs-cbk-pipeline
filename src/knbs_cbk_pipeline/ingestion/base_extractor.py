"""
Shared extraction behaviour: HTTP session config, retries with backoff,
and a consistent return contract (raw bytes/text + metadata) so every
extractor feeds the same raw_writer regardless of source.
"""
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
    """Uniform envelope returned by every extractor, regardless of source."""

    source_id: str
    fetched_at: dt.datetime
    content: bytes
    content_type: str          # e.g. "application/json", "text/html", "application/vnd.ms-excel"
    source_url: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ExtractionError(Exception):
    """Raised when a source cannot be fetched after all retries are exhausted."""


class BaseExtractor:
    """
    Common HTTP fetch logic. Concrete extractors (cbk_extractor,
    knbs_extractor) subclass this and implement `fetch(source_config)`,
    calling `self._get(...)` for the actual network call.
    """

    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )

    def __enter__(self) -> "BaseExtractor":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        log.info("extractor.request", url=url, params=params)
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response

    def fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        raise NotImplementedError("Subclasses must implement fetch()")

    def safe_fetch(self, source_config: dict[str, Any]) -> ExtractionResult:
        """Wraps fetch() so a single source failure never kills the whole run."""
        try:
            return self.fetch(source_config)
        except Exception as exc:  # noqa: BLE001 - intentionally broad at the run boundary
            log.error(
                "extractor.failed",
                source_id=source_config.get("id"),
                error=str(exc),
            )
            raise ExtractionError(
                f"Failed to extract source '{source_config.get('id')}': {exc}"
            ) from exc
