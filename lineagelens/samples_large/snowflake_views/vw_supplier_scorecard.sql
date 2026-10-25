-- Supplier OTIF scorecard (SYNTHETIC SAMPLE)
create or replace view HELIOS.REPORTING.VW_SUPPLIER_SCORECARD as
select
    s.supplier_key,
    s.supplier_name,
    avg(p.fill_rate) as avg_fill_rate,
    avg(p.days_late) as avg_days_late,
    sum(p.po_cost) as total_spend
from HELIOS.GOLD.FCT_PURCHASE_ORDERS p
join HELIOS.GOLD.DIM_SUPPLIER s on s.supplier_key = p.supplier_key
group by s.supplier_key, s.supplier_name;
