{{ config(materialized='view') }}
select
    *,
    quantity * unit_price * (1 - discount_pct) as net_amount
from {{ source('raw', 'order_items') }}
