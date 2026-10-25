-- Stock cover by store and product (SYNTHETIC SAMPLE)
create or replace view HELIOS.REPORTING.VW_INVENTORY_HEALTH as
select
    i.snapshot_date,
    i.store_key,
    i.product_key,
    i.on_hand_qty,
    i.stock_value,
    i.on_hand_qty / nullif(i.safety_stock, 0) as cover_ratio
from HELIOS.GOLD.FCT_INVENTORY_SNAPSHOT i;
