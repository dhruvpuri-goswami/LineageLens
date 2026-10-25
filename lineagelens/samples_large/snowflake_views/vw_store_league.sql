-- Store league table (SYNTHETIC SAMPLE)
create or replace view HELIOS.REPORTING.VW_STORE_LEAGUE as
select
    sp.store_key,
    st.store_name,
    st.sales_region,
    sp.net_revenue,
    sp.revenue_per_sq_ft,
    rank() over (partition by st.sales_region order by sp.net_revenue desc) as region_rank
from HELIOS.GOLD.FCT_STORE_PERFORMANCE sp
join HELIOS.GOLD.DIM_STORE st on st.store_key = sp.store_key;
