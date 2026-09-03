-- Thin staging layer: rename/cast only, no business logic. Business logic
-- (unit conversions, indicator groupings) belongs in intermediate/ or
-- marts/, never here — staging should be a 1:1 mirror of the source that's
-- safe to rebuild at any time.

with source as (
    select * from {{ source('staging', 'economic_indicators') }}
)

select
    id,
    lower(trim(indicator_code)) as indicator_code,
    trim(indicator_name)        as indicator_name,
    cast(period_date as date)   as period_date,
    cast(value as double precision) as value,
    unit,
    lower(trim(source_id))      as source_id,
    ingested_at
from source
