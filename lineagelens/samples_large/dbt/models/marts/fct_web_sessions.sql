{{ config(materialized='table') }}
select
    s.session_id as session_key,
    s.customer_id as customer_key,
    s.campaign_id as campaign_key,
    s.session_date,
    s.device,
    s.page_views,
    case when s.is_converted then 1 else 0 end as conversions
from {{ ref('int_sessions_attributed') }} s
