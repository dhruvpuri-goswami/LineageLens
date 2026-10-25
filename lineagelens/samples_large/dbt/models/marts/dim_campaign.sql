{{ config(materialized='table') }}
select
    c.campaign_id as campaign_key,
    c.campaign_name,
    c.marketing_channel,
    c.start_date as campaign_start,
    c.end_date as campaign_end,
    c.spend as campaign_spend
from {{ ref('stg_mkt_campaigns') }} c
