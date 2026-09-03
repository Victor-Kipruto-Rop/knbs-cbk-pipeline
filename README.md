# KNBS/CBK Open Economic Data Pipeline

An open-data pipeline that ingests Kenyan economic indicators — CBK FX
rates, CBK policy rates, KNBS CPI/inflation — cleans and validates them
into a shared tidy schema, and builds a queryable star schema on top with
dbt.

## Status

- **Ingestion**: working end-to-end for `cbk_fx_rates` (Frankfurter/CBK
  JSON API), `cbk_key_rates` (HTML scrape), `knbs_cpi` (Excel bulletin).
  `knbs_gdp_quarterly` is registered but has no cleaner yet.
- **Transformation, validation, warehouse load**: working end-to-end,
  covered by tests running against SQLite (no live Postgres needed to
  verify logic).
- **dbt marts**: `dim_time`, `dim_indicator`, `fct_economic_indicators`
  defined; not yet run against a live warehouse in this environment (no
  Postgres available where this was built — see Quickstart to run it
  yourself).
- **Orchestration**: three Airflow DAGs (`cbk_daily_ingestion`,
  `knbs_bulletin_ingestion`, `warehouse_refresh`) — untested against a
  live Airflow instance, same reason as above.
- **Observability**: freshness/failure tracking and alerting implemented
  and tested against SQLite.

## Quickstart

```bash
cp .env.example .env
docker compose up -d postgres

pip install -e ".[dev]"

python -m knbs_cbk_pipeline.ingestion.runner
python -m knbs_cbk_pipeline.transformation.runner

cd dbt && dbt deps && dbt run --profiles-dir . && dbt test --profiles-dir .
```

Or, once Postgres is up: `./scripts/run_local.sh` does all of the above.

Query the result:
```sql
select * from marts.fct_economic_indicators
where indicator_category = 'exchange_rate'
order by period_date desc
limit 20;
```

## Running tests

```bash
pip install -e ".[dev]"
pytest
```

All 15 tests run without network access or a live database — HTTP calls
are mocked with `respx`, and warehouse logic is tested against in-memory
SQLite using the same upsert code path Postgres uses in production.

## Adding a new source

1. Add an entry to `config/sources.yaml`.
2. If it's a new institution (not CBK/KNBS), add an extractor in
   `src/knbs_cbk_pipeline/ingestion/` subclassing `BaseExtractor`.
3. Add a cleaner function in `transformation/cleaners/` that outputs the
   shared tidy schema (`indicator_code, indicator_name, period_date,
   value, unit, source_id`) — see `docs/architecture.md` for why this
   matters.
4. Register the cleaner in `transformation/runner.py`'s `_CLEANERS` dict.
5. Nothing in `dbt/models/marts/` needs to change — new indicators just
   start showing up in `fct_economic_indicators`.

## Docs

- [`docs/architecture.md`](docs/architecture.md) — data flow and design
  rationale
- [`docs/data_dictionary.md`](docs/data_dictionary.md) — every indicator
  code, unit, and known data-quality caveat
- [`docs/runbook.md`](docs/runbook.md) — failure triage
