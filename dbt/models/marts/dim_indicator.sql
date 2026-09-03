-- Indicator dimension: one row per distinct indicator_code, carrying its
-- display name, unit, owning source, and a coarse category. The category
-- mapping is the one piece of business logic in the mart layer — it's
-- centralized here so any downstream chart/report groups indicators the
-- same way instead of every consumer reinventing "what kind of number is
-- this".

with distinct_indicators as (
    select distinct
        indicator_code,
        indicator_name,
        unit,
        source_id
    from {{ ref('stg_economic_indicators') }}
)

select
    indicator_code,
    indicator_name,
    unit,
    source_id,
    case
        when indicator_code like 'cbk_fx_%'        then 'exchange_rate'
        when indicator_code like 'cbk_%rate%'
          or indicator_code in ('cbk_central_bank_rate', 'cbk_repo_rate', 'cbk_kbrr',
                                 'cbk_91day_tbill', 'cbk_discount_window')
                                                     then 'policy_rate'
        when indicator_code like 'knbs_cpi%'         then 'price_index'
        when indicator_code like 'knbs_inflation%'   then 'inflation'
        when indicator_code like 'knbs_gdp%'         then 'output'
        else 'other'
    end as indicator_category
from distinct_indicators
