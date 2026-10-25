{{ config(materialized='view') }}
select
    order_id,
    customer_id,
    store_id,
    order_ts::date as order_date,
    lower(status) as order_status
from {{ source('raw', 'orders') }}
where status <> 'TEST'
