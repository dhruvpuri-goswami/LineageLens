{{ config(materialized='table') }}
select
    s.store_id as store_key,
    s.store_name,
    s.sales_region,
    s.country_code,
    s.store_format,
    s.opened_on,
    s.manager_email,
    s.sq_ft
from {{ ref('stg_ops_stores') }} s
