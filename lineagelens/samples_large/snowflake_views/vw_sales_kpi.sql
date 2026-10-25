-- Daily KPI feed for the commercial scorecard (SYNTHETIC SAMPLE)
create or replace view HELIOS.REPORTING.VW_SALES_KPI as
select
    d.order_date,
    st.sales_region,
    sum(d.net_revenue) as net_revenue,
    sum(d.margin_amount) as margin_amount,
    sum(d.order_count) as order_count
from HELIOS.GOLD.FCT_DAILY_SALES d
join HELIOS.GOLD.DIM_STORE st on st.store_key = d.store_key
group by d.order_date, st.sales_region;
