{{ config(materialized='table') }}
select
    b.period_month,
    b.cost_center_id,
    b.account_id,
    sum(b.budget_amount) as budget_amount
from {{ ref('stg_fin_budgets') }} b
group by b.period_month, b.cost_center_id, b.account_id
