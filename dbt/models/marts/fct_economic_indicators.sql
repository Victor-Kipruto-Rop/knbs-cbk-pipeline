-- Central fact table: one row per (indicator, period, source) observation.
-- Every KNBS/CBK dataset lands here regardless of source, which is the
-- whole point of the tidy schema upstream — a new source only needs a new
-- cleaner, never a new mart.

with facts as (
    select
        indicator_code,
        period_date,
        source_id,
        value,
        ingested_at
    from {{ ref('stg_economic_indicators') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['f.indicator_code', 'f.period_date', 'f.source_id']) }}
        as indicator_period_key,
    f.indicator_code,
    d.indicator_name,
    d.indicator_category,
    d.unit,
    f.period_date,
    t.year,
    t.quarter,
    t.year_month,
    f.source_id,
    f.value,
    f.ingested_at
from facts f
left join {{ ref('dim_indicator') }} d on f.indicator_code = d.indicator_code
left join {{ ref('dim_time') }} t on f.period_date = t.date_day
