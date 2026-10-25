{{ config(materialized='incremental') }}
select
    ol.order_item_id as sales_key,
    ol.order_id,
    ol.customer_id as customer_key,
    ol.product_id as product_key,
    ol.store_id as store_key,
    ol.order_date,
    ol.quantity,
    ol.net_amount,
    ol.quantity * p.list_price as gross_amount,
    ol.discount_band,
    ol.order_status
from {{ ref('int_order_lines') }} ol
left join {{ ref('stg_products') }} p on ol.product_id = p.product_id
where ol.order_status <> 'cancelled'
