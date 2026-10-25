{{ config(materialized='table') }}
select
    b.period_month,
    b.cost_center_id as cost_center_key,
    b.account_id as account_key,
    b.budget_amount
from {{ ref('int_budget_monthly') }} b
