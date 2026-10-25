{{ config(materialized='table') }}
select
    c.cost_center_id as cost_center_key,
    c.cost_center_name,
    c.region as cost_center_region,
    c.owner_email
from {{ ref('stg_hr_cost_centers') }} c
