#!/usr/bin/env bash
# Spins up Postgres, runs ingestion + transformation once, then dbt.
# For iterating locally without touching Airflow.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Starting Postgres"
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U kcp -d kcp > /dev/null 2>&1; do
  sleep 1
done

echo "==> Running ingestion"
python -m knbs_cbk_pipeline.ingestion.runner

echo "==> Running transformation + load"
python -m knbs_cbk_pipeline.transformation.runner

echo "==> Running dbt"
(cd dbt && dbt run --profiles-dir . && dbt test --profiles-dir .)

echo "==> Done. Query marts.fct_economic_indicators in Postgres to explore."
