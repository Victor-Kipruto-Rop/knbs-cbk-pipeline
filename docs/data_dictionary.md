# Data Dictionary

## Sources (config/sources.yaml)

| source_id | owner | cadence | format | notes |
|---|---|---|---|---|
| `cbk_fx_rates` | CBK | daily | JSON (Frankfurter API, CBK provider) | Indicative FX rates, base USD |
| `cbk_key_rates` | CBK | daily | HTML (homepage widget scrape) | Central Bank Rate, Inter-Bank Rate, T-Bill, inflation, lending/savings/deposit rates, KBRR |
| `knbs_cpi` | KNBS | monthly | XLSX bulletin | Consumer Price Index + annual inflation rate |
| `knbs_gdp_quarterly` | KNBS | quarterly | XLSX bulletin | GDP report (registered, cleaner not yet implemented) |

## Indicator codes (staging.economic_indicators / marts.fct_economic_indicators)

| indicator_code | indicator_name | unit | category | source |
|---|---|---|---|---|
| `cbk_fx_usd_{ccy}` | `{ccy}` exchange rate vs USD | `{ccy} per USD` | exchange_rate | cbk_fx_rates |
| `cbk_central_bank_rate` | Central Bank Rate | percent | policy_rate | cbk_key_rates |
| `cbk_interbank_rate` | Inter-Bank Rate | percent | policy_rate | cbk_key_rates |
| `cbk_discount_window` | CBK Discount Window | percent | policy_rate | cbk_key_rates |
| `cbk_91day_tbill` | 91-Day T-Bill | percent | policy_rate | cbk_key_rates |
| `cbk_repo_rate` | REPO | percent | policy_rate | cbk_key_rates |
| `cbk_inflation_rate` | Inflation Rate (CBK widget) | percent | inflation | cbk_key_rates |
| `cbk_lending_rate` | Lending Rate | percent | policy_rate | cbk_key_rates |
| `cbk_savings_rate` | Savings Rate | percent | policy_rate | cbk_key_rates |
| `cbk_deposit_rate` | Deposit Rate | percent | policy_rate | cbk_key_rates |
| `cbk_kbrr` | KBRR | percent | policy_rate | cbk_key_rates |
| `knbs_cpi_index` | Consumer Price Index | index (base year = 100) | price_index | knbs_cpi |
| `knbs_inflation_rate_annual` | Annual inflation rate | percent | inflation | knbs_cpi |

## Natural key

Every row in `staging.economic_indicators` and `marts.fct_economic_indicators`
is uniquely identified by `(indicator_code, period_date, source_id)`. This is
what the loader upserts on and what dbt tests enforce uniqueness against.

## Known data quality caveats

- **`cbk_key_rates` period_date** is the *fetch* date, not each rate's true
  as-of date — CBK's homepage widget mixes `dd/mm/yyyy` and `Month,YYYY`
  formats inconsistently across rows, so we anchor to fetch time and treat
  the value as "most recently published as of this fetch."
- **`cbk_key_rates` is HTML-scraped** from a page not designed as a data
  feed. A CBK site redesign will break `transformation/cleaners/cbk_cleaner.py`'s
  `_KEY_RATE_LABELS` mapping — this is why it's a hardcoded dict, not
  inferred: a mismatch fails loudly (zero rows -> validator error) instead
  of silently mis-tagging a rate.
- **`knbs_cpi` column matching is fuzzy** (`_find_column` in
  `knbs_cleaner.py`) because KNBS bulletin column headers are not stable
  release to release.
