{{ config(materialized='table') }}
select
    co.customer_id as customer_key,
    co.first_order_date,
    co.last_order_date,
    co.lifetime_orders,
    co.lifetime_revenue,
    co.lifetime_margin,
    co.lifetime_revenue / nullif(co.lifetime_orders, 0) as avg_order_value,
    datediff('day', co.last_order_date, current_date) as days_since_last_order
from {{ ref('int_customer_orders') }} co
