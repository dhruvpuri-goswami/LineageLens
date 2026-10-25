{{ config(materialized='view') }}
select
    order_id,
    customer_id,
    store_id,
    upper(channel_code) as channel_code,
    order_ts::date as order_date,
    lower(status) as order_status,
    currency_code,
    promo_code is not null as has_promo
from {{ source('raw', 'erp_orders') }}
