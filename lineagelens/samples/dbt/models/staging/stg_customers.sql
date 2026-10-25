{{ config(materialized='view') }}
select
    customer_id,
    first_name || ' ' || last_name as customer_name,
    email,
    country_code,
    segment as customer_segment,
    created_at
from {{ source('raw', 'customers') }}
