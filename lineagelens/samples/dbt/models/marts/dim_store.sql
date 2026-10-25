{{ config(materialized='table') }}
select
    store_id as store_key,
    store_name,
    sales_region,
    country_code,
    manager_email
from {{ ref('stg_stores') }}
