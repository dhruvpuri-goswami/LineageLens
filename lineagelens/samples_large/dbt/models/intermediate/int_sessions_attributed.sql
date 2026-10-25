{{ config(materialized='table') }}
select
    s.session_id,
    s.customer_id,
    s.session_date,
    s.device,
    s.page_views,
    s.is_converted,
    c.campaign_id,
    c.marketing_channel
from {{ ref('stg_web_sessions') }} s
left join {{ ref('stg_mkt_campaigns') }} c on s.campaign_id = c.campaign_id
