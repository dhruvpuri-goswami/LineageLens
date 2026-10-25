{{ config(materialized='table') }}
select
    s.supplier_id as supplier_key,
    s.supplier_name,
    s.country_code as supplier_country,
    s.rating as supplier_rating,
    s.lead_time_days as contracted_lead_days
from {{ ref('stg_scm_suppliers') }} s
