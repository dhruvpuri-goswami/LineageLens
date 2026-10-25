{{ config(materialized='table') }}
select
    l.order_id as order_key,
    l.customer_id as customer_key,
    l.store_id as store_key,
    l.channel_code as channel_key,
    l.order_date,
    count(*) as line_count,
    sum(l.quantity) as units,
    sum(l.net_revenue) as order_revenue,
    sum(l.net_revenue - l.cost_amount) as order_margin
from {{ ref('int_order_lines_enriched') }} l
group by l.order_id, l.customer_id, l.store_id, l.channel_code, l.order_date
