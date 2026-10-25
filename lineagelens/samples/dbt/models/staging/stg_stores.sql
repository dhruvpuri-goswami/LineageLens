{{ config(materialized='view') }}
select
    store_id,
    store_name,
    region as sales_region,
    country_code,
    manager_email
from {{ source('raw', 'stores') }}
