{{ config(materialized='view') }}
select
    budget_id,
    cost_center_id,
    account_id,
    period_month,
    budget_amount
from {{ source('raw', 'fin_budgets') }}
