{{ config(materialized='view') }}
select
    po_id,
    supplier_id,
    product_id,
    ordered_qty,
    coalesce(received_qty, 0) as received_qty,
    po_date,
    expected_date,
    received_date,
    po_cost
from {{ source('raw', 'scm_purchase_orders') }}
