{{ config(materialized='view') }}
select
    line_id,
    order_id,
    product_id,
    qty as quantity,
    unit_price,
    unit_cost,
    coalesce(discount_pct, 0) as discount_pct,
    tax_rate
from {{ source('raw', 'erp_order_lines') }}
