# Runbook

## "Ingestion failed for source X"

1. Check `data/curated/_run_metadata.jsonl` (or query it) for the `error`
   field on the failed run.
2. If it's an HTTP error (403, 429, timeout): check whether the source's
   endpoint in `config/sources.yaml` still resolves manually
   (`curl -I <endpoint>`). CBK/KNBS occasionally rate-limit or move pages.
3. Retries are automatic (`tenacity`, up to 4 attempts, exponential
   backoff) — a failure means retries were already exhausted.
4. Fix the endpoint/params in `config/sources.yaml` if it moved, or add a
   `User-Agent`/header tweak in `ingestion/base_extractor.py` if it's a
   blocking issue.

## "Transformation failed for source X" / validator errors

This almost always means the source changed shape:
- **`cbk_key_rates`**: CBK's homepage widget markup changed. Check the raw
  HTML in `data/raw/cbk_key_rates/.../*.html` against
  `transformation/cleaners/cbk_cleaner.py`'s `_KEY_RATE_LABELS` — a label
  wording change (e.g. "Central Bank Rate" -> "CBR") needs a new dict
  entry.
- **`knbs_cpi`**: KNBS renamed or restructured columns in the bulletin.
  Open the raw `.xlsx` in `data/raw/knbs_cpi/...` and check actual column
  headers against `_MONTH_COL_CANDIDATES` / `_CPI_COL_CANDIDATES` /
  `_INFLATION_COL_CANDIDATES` in `knbs_cleaner.py`.
- **Zero rows**: the validator (`schema_checks.py`) treats this as a hard
  failure by design — it means the cleaner matched nothing, which is
  always a bug, never a legitimate "no data this period" state for these
  sources.

After fixing the cleaner, replay history without re-fetching:
```
python scripts/backfill.py --source-id <source_id>
```

## "Data is stale" alert

`observability/metrics.py::freshness_by_source` flags a source stale when
its latest loaded `period_date` is older than `freshness_sla_hours`
(per-source override in `config/sources.yaml`, default in
`config/settings.py`). Check:
1. Did the DAG actually run? (Airflow UI / `_run_metadata.jsonl`)
2. Did ingestion succeed but transformation silently produce 0 rows? See
   above.
3. Has the upstream source simply not published yet (e.g. KNBS running
   late on a monthly release)? If so, this is a true positive — no action
   needed beyond waiting, but worth confirming it isn't masking a real
   failure.

## dbt test failures

Run `dbt test --profiles-dir dbt -s <failing_model>` locally to see the
failing rows. Most likely causes:
- `relationships` test on `fct_economic_indicators.indicator_code` failing
  → a new `indicator_code` was introduced by a cleaner without a
  corresponding entry reachable from `dim_indicator`'s category `CASE`
  logic (it'll still show up, just check the row count moved as expected).
- `unique`/`not_null` on `id` in staging → the loader's natural-key hash
  collided or a cleaner emitted a null in a required column; check
  `transformation/validators/schema_checks.py` output for that run.
