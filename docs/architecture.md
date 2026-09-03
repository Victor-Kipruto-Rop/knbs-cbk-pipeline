# Architecture

## Data flow

```
CBK / KNBS sources
        │
        ▼
 ingestion/runner.py          reads config/sources.yaml, dispatches to
   (cbk_extractor,             cbk_extractor or knbs_extractor, lands raw
    knbs_extractor)            bytes + metadata sidecar via raw_writer.py
        │
        ▼
   data/raw/{source_id}/{yyyy}/{mm}/{dd}/...     ← immutable, replayable
        │
        ▼
 transformation/runner.py     picks latest raw file per source, routes to
   (cbk_cleaner,                the matching cleaner, validates the tidy
    knbs_cleaner,                output (schema_checks.py), standardizes
    schema_checks,               (standardize.py), and upserts into
    standardize)                 staging.economic_indicators
        │
        ▼
 warehouse/loaders/postgres_loader.py    idempotent upsert, keyed on
                                          (indicator_code, period_date, source_id)
        │
        ▼
   staging.economic_indicators (Postgres)
        │
        ▼
 dbt (dbt/models/staging, dbt/models/marts)
        │
        ▼
   marts.dim_time, marts.dim_indicator, marts.fct_economic_indicators
        │
        ▼
   BI / dashboard / API layer
```

## Why a shared tidy schema

Every cleaner — regardless of source — outputs the same six columns:
`indicator_code, indicator_name, period_date, value, unit, source_id`.
This is the single decision that keeps the mart layer simple: `dim_time`,
`dim_indicator`, and `fct_economic_indicators` never need to know how many
sources feed them. Adding a new KNBS/CBK dataset means writing one cleaner
function that emits this shape — nothing downstream changes.

## Why raw landing is immutable

`raw_writer.py` writes every fetch to a timestamped, append-only path
before any parsing happens. This means:
- A cleaner bug can be fixed and *replayed* against history via
  `scripts/backfill.py`, without re-fetching from CBK/KNBS.
- If CBK changes their HTML layout mid-month, the raw HTML from before the
  change is still there to diagnose against.

## Why idempotent upsert, not append-only fact loading

Reruns are a fact of life in data engineering — a failed DAG task gets
retried, a manual backfill overlaps a scheduled run, a person triggers
`scripts/backfill.py` twice by mistake. `warehouse/loaders/postgres_loader.py`
upserts on `(indicator_code, period_date, source_id)`, so none of those
scenarios create duplicate rows. This is tested in
`tests/unit/test_loader.py` against a real upsert, not mocked.

## Why CBK and KNBS get separate Airflow DAGs

CBK's FX/rate feeds are daily and stable. KNBS bulletins are
monthly/quarterly and structurally fragile (Excel layout changes between
releases). Splitting them means a KNBS layout-change failure doesn't block
or noisily retry alongside the daily CBK DAG, and the two failure modes
(network flake vs. schema drift) get different retry policies.
