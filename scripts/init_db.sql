-- Executed on first PostgreSQL volume initialization.
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;
ALTER ROLE kcp SET search_path TO staging, marts, public;
SELECT 'CREATE DATABASE airflow OWNER kcp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
COMMENT ON SCHEMA staging IS 'Tidy landing tables populated by the Python pipeline.';
COMMENT ON SCHEMA marts IS 'dbt analytical dimensions and fact tables.';
