{{ config(materialized='table') }}
select
    i.snapshot_date,
    i.store_id,
    i.product_id,
    i.on_hand_qty,
    i.on_order_qty,
    i.safety_stock,
    i.on_hand_qty * i.unit_cost as stock_value,
    case when i.on_hand_qty < i.safety_stock then 1 else 0 end as is_below_safety
from {{ ref('stg_wms_inventory') }} i
