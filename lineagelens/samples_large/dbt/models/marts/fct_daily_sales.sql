{{ config(materialized='table') }}
select
    s.order_date,
    s.store_key,
    sum(s.net_revenue) as net_revenue,
    sum(s.margin_amount) as margin_amount,
    sum(s.quantity) as units,
    count(distinct s.order_id) as order_count
from {{ ref('fct_sales_lines') }} s
group by s.order_date, s.store_key
