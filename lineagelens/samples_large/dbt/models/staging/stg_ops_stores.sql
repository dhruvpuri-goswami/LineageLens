{{ config(materialized='view') }}
select
    store_id,
    store_name,
    region as sales_region,
    country_code,
    store_format,
    opened_on,
    lower(manager_email) as manager_email,
    sq_ft
from {{ source('raw', 'ops_stores') }}
