{{ config(materialized='view') }}
with items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select * from {{ ref('stg_orders') }}
)
select
    i.order_item_id,
    i.order_id,
    o.customer_id,
    o.store_id,
    i.product_id,
    o.order_date,
    o.order_status,
    i.quantity,
    i.unit_price,
    i.discount_pct,
    i.net_amount,
    case
        when i.discount_pct >= 0.20 then 'High'
        when i.discount_pct > 0 then 'Low'
        else 'None'
    end as discount_band
from items i
inner join orders o on i.order_id = o.order_id
