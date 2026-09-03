"""
Every ingestion run gets a record here, success or failure. This is the
control-table pattern: without it, "did yesterday's CPI load actually run?"
is a question you can only answer by grepping logs.

Local/demo mode appends to a JSONL file; swap `_persist` for a Postgres
insert (see warehouse/loaders) in production without changing callers.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

RUN_LOG_PATH = Path("data/curated/_run_metadata.jsonl")


@dataclass
class RunRecord:
    source_id: str
    success: bool
    started_at: str
    raw_path: str | None = None
    byte_size: int | None = None
    error: str | None = None
    finished_at: str = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )

    # NOTE: these constructors are intentionally NOT named `success`/`failure`
    # — a classmethod named the same as the `success: bool` field shadows the
    # field's class attribute during dataclass processing and silently turns
    # it into a defaulted field, breaking field ordering. Learned that one
    # the hard way while building this.
    @classmethod
    def mark_success(cls, source_id: str, raw_path: Path, byte_size: int) -> "RunRecord":
        return cls(
            source_id=source_id,
            success=True,
            started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            raw_path=str(raw_path),
            byte_size=byte_size,
        )

    @classmethod
    def mark_failure(cls, source_id: str, error: str) -> "RunRecord":
        return cls(
            source_id=source_id,
            success=False,
            started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            error=error,
        )


def record_run(run: RunRecord) -> None:
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG_PATH, "a") as f:
        f.write(json.dumps(asdict(run)) + "\n")


def read_recent_runs(limit: int = 50) -> list[dict]:
    if not RUN_LOG_PATH.exists():
        return []
    lines = RUN_LOG_PATH.read_text().strip().splitlines()
    return [json.loads(line) for line in lines[-limit:]]
