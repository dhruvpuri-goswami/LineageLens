{{ config(materialized='view') }}
select
    entry_id,
    account_id,
    cost_center_id,
    posting_date,
    amount as amount_local,
    currency_code,
    entry_type
from {{ source('raw', 'fin_gl_entries') }}
