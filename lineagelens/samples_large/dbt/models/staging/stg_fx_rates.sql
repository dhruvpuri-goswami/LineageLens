{{ config(materialized='view') }}
select
    rate_date,
    currency_code,
    rate_to_usd
from {{ source('raw', 'fx_rates') }}
