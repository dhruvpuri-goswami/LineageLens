{{ config(materialized='table') }}
select
    l.line_id as return_key,
    l.product_id as product_key,
    l.store_id as store_key,
    l.order_date as return_date,
    l.quantity as returned_units,
    l.net_revenue as refund_amount
from {{ ref('int_order_lines_enriched') }} l
where l.order_status = 'returned'
