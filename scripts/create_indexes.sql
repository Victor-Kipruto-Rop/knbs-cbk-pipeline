-- Create helpful indexes for fast mart queries
-- Run with: psql -U kcp -d kcp -f scripts/create_indexes.sql

CREATE INDEX IF NOT EXISTS idx_fct_period_code_ingested ON marts_marts.fct_economic_indicators (period_date DESC, indicator_code DESC, ingested_at DESC);
CREATE INDEX IF NOT EXISTS idx_fct_source_id ON marts_marts.fct_economic_indicators (source_id);
CREATE INDEX IF NOT EXISTS idx_fct_indicator_code ON marts_marts.fct_economic_indicators (indicator_code);
