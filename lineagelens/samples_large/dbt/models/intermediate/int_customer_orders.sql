{{ config(materialized='table') }}
select
    customer_id,
    min(order_date) as first_order_date,
    max(order_date) as last_order_date,
    count(distinct order_id) as lifetime_orders,
    sum(net_revenue) as lifetime_revenue,
    sum(net_revenue - cost_amount) as lifetime_margin
from {{ ref('int_order_lines_enriched') }}
group by customer_id
