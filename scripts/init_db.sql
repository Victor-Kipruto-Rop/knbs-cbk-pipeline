-- Runs once, automatically, on first container start (mounted into
-- /docker-entrypoint-initdb.d by docker-compose.yml). Idempotent-safe via
-- IF NOT EXISTS since Postgres only runs init scripts on an empty data dir
-- anyway, but this keeps manual re-runs safe too.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

ALTER ROLE kcp SET search_path TO staging, marts, public;

COMMENT ON SCHEMA staging IS
  'Tidy-but-raw landing tables written directly by the Python loader (warehouse/loaders/postgres_loader.py).';
COMMENT ON SCHEMA marts IS
  'dbt-built star schema (dim_time, dim_indicator, fct_economic_indicators) for querying/BI.';
