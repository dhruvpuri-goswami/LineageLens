{{ config(materialized='view') }}
select
    session_id,
    customer_id,
    session_ts::date as session_date,
    lower(device) as device,
    page_views,
    campaign_id,
    converted as is_converted
from {{ source('raw', 'web_sessions') }}
