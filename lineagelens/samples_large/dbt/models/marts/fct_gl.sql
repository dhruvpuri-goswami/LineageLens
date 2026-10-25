{{ config(materialized='table') }}
select
    g.entry_id as gl_key,
    g.account_id as account_key,
    g.cost_center_id as cost_center_key,
    g.posting_date,
    g.entry_type,
    g.amount_usd
from {{ ref('int_gl_usd') }} g
