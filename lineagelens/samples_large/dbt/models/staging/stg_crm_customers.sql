{{ config(materialized='view') }}
select
    customer_id,
    initcap(full_name) as customer_name,
    lower(email) as email,
    country_code,
    segment as customer_segment,
    coalesce(loyalty_tier, 'None') as loyalty_tier,
    created_at,
    birth_year
from {{ source('raw', 'crm_customers') }}
