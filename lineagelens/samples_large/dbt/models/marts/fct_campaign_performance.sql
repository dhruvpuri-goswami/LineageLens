{{ config(materialized='table') }}
select
    c.campaign_key,
    c.campaign_spend,
    count(distinct w.session_key) as sessions,
    sum(w.conversions) as conversions,
    sum(o.order_revenue) as attributed_revenue
from {{ ref('dim_campaign') }} c
left join {{ ref('fct_web_sessions') }} w on w.campaign_key = c.campaign_key
left join {{ ref('fct_orders') }} o on o.customer_key = w.customer_key and o.order_date = w.session_date
group by c.campaign_key, c.campaign_spend
