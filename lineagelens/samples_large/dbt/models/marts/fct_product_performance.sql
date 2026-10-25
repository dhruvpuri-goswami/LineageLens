{{ config(materialized='table') }}
select
    pm.product_id as product_key,
    pm.units_sold,
    pm.net_revenue,
    pm.margin_amount,
    pm.margin_amount / nullif(pm.net_revenue, 0) as margin_pct
from {{ ref('int_product_margin') }} pm
