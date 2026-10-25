{{ config(materialized='table') }}
select
    d.store_key,
    sum(d.net_revenue) as net_revenue,
    sum(d.margin_amount) as margin_amount,
    sum(d.order_count) as order_count,
    sum(d.net_revenue) / nullif(max(st.sq_ft), 0) as revenue_per_sq_ft
from {{ ref('fct_daily_sales') }} d
join {{ ref('dim_store') }} st on st.store_key = d.store_key
group by d.store_key
