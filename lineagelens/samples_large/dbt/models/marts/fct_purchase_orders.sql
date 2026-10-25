{{ config(materialized='table') }}
select
    r.po_id as po_key,
    r.supplier_id as supplier_key,
    r.product_id as product_key,
    r.po_date,
    r.ordered_qty,
    r.received_qty,
    r.po_cost,
    r.actual_lead_days,
    r.days_late,
    r.fill_rate
from {{ ref('int_po_receipts') }} r
