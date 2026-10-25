{{ config(materialized='view') }}
select
    cost_center_id,
    cost_center_name,
    region,
    lower(owner_email) as owner_email
from {{ source('raw', 'hr_cost_centers') }}
