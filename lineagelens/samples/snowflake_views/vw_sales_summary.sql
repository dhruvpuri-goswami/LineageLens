-- Owned by the BI team and deployed outside dbt (SAMPLE DATA).
-- Daily sales by region, consumed by the "Sales Summary" table in Power BI via a native query.
create or replace secure view ANALYTICS.REPORTING.VW_SALES_SUMMARY
    comment = 'Daily sales by region for the regional scorecard'
as
select
    s.order_date,
    st.sales_region,
    sum(s.net_amount)          as total_net_amount,
    count(distinct s.order_id) as order_count,
    sum(s.quantity)            as total_units
from ANALYTICS.GOLD.FCT_SALES s
join ANALYTICS.GOLD.DIM_STORE st
  on s.store_key = st.store_key
group by s.order_date, st.sales_region;
