# KNBS / CBK Open Economic Data Pipeline

A reproducible data engineering project that ingests Kenyan macroeconomic indicators from the Central Bank of Kenya (CBK) and Kenya National Bureau of Statistics (KNBS), validates and standardizes observations, loads PostgreSQL, and builds dbt marts.

## Local architecture

- PostgreSQL 16: staging, revision history and analytics schemas.
- Redis 7: API/query cache and invalidation.
- Python 3.12: extraction, raw artifact storage, validation and warehouse loading.
- dbt Core + dbt-postgres: analytical models and tests.
- Apache Airflow 2.10: optional local orchestration profile.

The default Compose profile starts only stateful dependencies. Pipeline and Airflow are opt-in so developers can test each layer without accidentally triggering live source downloads.

## Quick start (PowerShell)

    Copy-Item .env.example .env
    docker compose up -d postgres redis
    docker compose ps

Install locally:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -e ".[dev,analytics]"

Run the complete one-shot pipeline in Docker:

    docker compose --profile pipeline run --rm pipeline

Or run stages locally:

    python -m knbs_cbk_pipeline.ingestion.runner
    python -m knbs_cbk_pipeline.transformation.runner
    Set-Location dbt
    dbt deps
    dbt build --profiles-dir .
    Set-Location ..

## Airflow (optional)

    docker compose --profile orchestration up -d --build airflow
    docker compose logs -f airflow

Open http://localhost:8080. Airflow standalone creates a local admin account and prints its generated credentials in container logs. Change the password before sharing the environment. Airflow metadata is isolated in PostgreSQL database airflow; economic data remains in database kcp.

The Airflow image includes the project, dbt project and analytics dependencies. It loads the daily CBK DAG, monthly CPI DAG, quarterly GDP DAG and daily warehouse refresh DAG.

## Database ports and credentials

- Host PostgreSQL: localhost:5433
- Container PostgreSQL: postgres:5432
- Host Redis: localhost:6379
- Container Redis: redis:6379

Example credentials are for local development only. Override them before exposing any service beyond localhost. Never commit .env.

## Data flow

KNBS / CBK → immutable raw artifacts + sidecars → source-specific cleaners → schema validation → standardized observations → PostgreSQL staging + revision history → dbt staging / dimensions / fact → analytics.

Every raw artifact has a metadata sidecar with its source URL, fetch timestamp, content type, byte count and SHA-256 checksum. Transformations use the sidecar timestamp rather than filesystem modification time. KNBS landing pages are resolved to downloadable files and file signatures are checked before raw landing.

Current observations are stored in staging.economic_indicators. Changes to a previously loaded observation are appended to staging.economic_indicator_versions with the previous value and recorded timestamp. Older replays cannot overwrite a newer current observation.

## Source support and caveats

| Source | Extractor | Cleaner | Notes |
|---|---|---|---|
| CBK FX rates | JSON API | Yes | Frankfurter CBK provider |
| CBK key rates | HTML | Yes | Parses displayed observation dates when present |
| KNBS CPI | Landing page → XLSX | Yes | Workbook headers must remain recognizable |
| KNBS quarterly GDP | Landing page → XLSX | Initial generic parser | Confirm workbook units and sheet layout against a current KNBS release before treating values as certified |

GDP parser deliberately fails closed if it cannot recognize a quarter and GDP value column. Its unit label is provisional and must be confirmed against source workbook metadata. If the official landing page publishes PDF rather than XLSX, add a PDF-specific extraction/cleaning adapter rather than bypassing file validation.

## Tests and quality checks

    ruff check .
    pytest -q

CI runs linting, unit/integration tests, PostgreSQL connectivity, dbt dependency resolution and dbt build/tests. GitHub Actions must have available runner capacity for these checks to execute.

## Operational notes

- Ingestion and transformation commands return non-zero when a source fails.
- Source failures are recorded individually so Airflow can retry failed tasks.
- Freshness metrics use each source's configured SLA rather than a single global threshold.
- Raw artifacts are retained for replay; do not delete raw data before validating warehouse loads.
- docker compose down -v deletes local PostgreSQL and Redis volumes. Use only when intentionally resetting local state.
- This is an open-data pipeline, not an official publication or statistical authority. Preserve source provenance and review source corrections before downstream use.
