{{ config(materialized='table') }}
select distinct
    o.channel_code as channel_key,
    case o.channel_code when 'WEB' then 'Online' when 'APP' then 'Mobile app' else 'Store' end as channel_name
from {{ ref('stg_erp_orders') }} o
