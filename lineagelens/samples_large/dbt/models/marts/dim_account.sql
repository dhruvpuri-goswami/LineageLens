{{ config(materialized='table') }}
select
    a.account_id as account_key,
    a.account_name,
    a.account_group,
    a.pl_line
from {{ ref('stg_fin_accounts') }} a
