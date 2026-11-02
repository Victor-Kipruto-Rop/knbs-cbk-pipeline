"""Operational alert delivery. Webhook absence degrades to structured logging."""
from __future__ import annotations
import httpx
import structlog
from config.settings import settings
from knbs_cbk_pipeline.observability.metrics import SourceHealth

log = structlog.get_logger()

def check_and_alert(health_records: list[SourceHealth]) -> list[str]:
    messages = []
    for health in health_records:
        if health.last_run_success is False:
            messages.append(f":x: {health.source_id} — last ingestion run FAILED.")
        if health.is_stale:
            messages.append(f":warning: {health.source_id} — data is stale (latest period: {health.latest_period_date or 'never loaded'}).")
    for message in messages:
        send_alert(message)
    return messages

def send_alert(message: str) -> None:
    if not settings.alert_webhook_url:
        log.warning("alert.would_send", message=message, note="KCP_ALERT_WEBHOOK_URL not set — logging only")
        return
    try:
        response = httpx.post(settings.alert_webhook_url, json={"text": message}, timeout=10)
        response.raise_for_status()
        log.info("alert.sent", message=message)
    except httpx.HTTPError as exc:
        log.error("alert.send_failed", message=message, error=str(exc))
