{{ config(materialized='table') }}
select
    g.entry_id,
    g.account_id,
    g.cost_center_id,
    g.posting_date,
    g.entry_type,
    g.amount_local * fx.rate_to_usd as amount_usd
from {{ ref('stg_fin_gl_entries') }} g
join {{ ref('stg_fx_rates') }} fx on fx.currency_code = g.currency_code and fx.rate_date = g.posting_date
