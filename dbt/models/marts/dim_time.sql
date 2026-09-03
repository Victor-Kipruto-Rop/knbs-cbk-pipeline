-- Date dimension. Generated from the distinct period_dates actually seen
-- in staging rather than a hardcoded date-spine range, so it never needs
-- manual extension as new data lands — it just grows with the fact table.

with distinct_dates as (
    select distinct period_date as date_day
    from {{ ref('stg_economic_indicators') }}
)

select
    date_day,
    extract(year from date_day)::int    as year,
    extract(month from date_day)::int   as month,
    extract(day from date_day)::int     as day,
    extract(quarter from date_day)::int as quarter,
    to_char(date_day, 'YYYY-MM')        as year_month,
    to_char(date_day, 'Month')          as month_name
from distinct_dates
