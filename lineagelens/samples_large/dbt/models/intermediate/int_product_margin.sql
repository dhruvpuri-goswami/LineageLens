{{ config(materialized='table') }}
select
    product_id,
    sum(quantity) as units_sold,
    sum(net_revenue) as net_revenue,
    sum(net_revenue - cost_amount) as margin_amount
from {{ ref('int_order_lines_enriched') }}
group by product_id
