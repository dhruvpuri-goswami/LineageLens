{{ config(materialized='table') }}
select
    po.po_id,
    po.supplier_id,
    po.product_id,
    po.po_date,
    po.ordered_qty,
    po.received_qty,
    po.po_cost,
    datediff('day', po.po_date, po.received_date) as actual_lead_days,
    datediff('day', po.expected_date, po.received_date) as days_late,
    po.received_qty / nullif(po.ordered_qty, 0) as fill_rate
from {{ ref('stg_scm_purchase_orders') }} po
