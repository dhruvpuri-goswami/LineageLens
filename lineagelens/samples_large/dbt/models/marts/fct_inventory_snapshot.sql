{{ config(materialized='table') }}
select
    i.snapshot_date,
    i.store_id as store_key,
    i.product_id as product_key,
    i.on_hand_qty,
    i.on_order_qty,
    i.safety_stock,
    i.stock_value,
    i.is_below_safety
from {{ ref('int_inventory_daily') }} i
