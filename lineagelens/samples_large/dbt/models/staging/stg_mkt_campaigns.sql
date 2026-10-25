{{ config(materialized='view') }}
select
    campaign_id,
    campaign_name,
    channel as marketing_channel,
    start_date,
    end_date,
    spend
from {{ source('raw', 'mkt_campaigns') }}
