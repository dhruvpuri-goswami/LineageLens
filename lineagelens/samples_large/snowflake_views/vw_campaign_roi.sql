-- Campaign ROI (SYNTHETIC SAMPLE)
create or replace view HELIOS.REPORTING.VW_CAMPAIGN_ROI as
select
    c.campaign_key,
    dc.campaign_name,
    dc.marketing_channel,
    c.campaign_spend,
    c.attributed_revenue,
    c.attributed_revenue / nullif(c.campaign_spend, 0) as roas
from HELIOS.GOLD.FCT_CAMPAIGN_PERFORMANCE c
join HELIOS.GOLD.DIM_CAMPAIGN dc on dc.campaign_key = c.campaign_key;
