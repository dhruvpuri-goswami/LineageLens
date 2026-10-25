{{ config(materialized='view') }}
select
    account_id,
    account_name,
    account_group,
    pl_line
from {{ source('raw', 'fin_accounts') }}
