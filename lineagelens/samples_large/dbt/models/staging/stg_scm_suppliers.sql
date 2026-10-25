{{ config(materialized='view') }}
select
    supplier_id,
    supplier_name,
    country_code,
    rating,
    lead_time_days
from {{ source('raw', 'scm_suppliers') }}
