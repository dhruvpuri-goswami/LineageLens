{{ config(materialized='view') }}
select
    snapshot_date,
    store_id,
    product_id,
    on_hand_qty,
    on_order_qty,
    safety_stock,
    unit_cost
from {{ source('raw', 'wms_inventory') }}
