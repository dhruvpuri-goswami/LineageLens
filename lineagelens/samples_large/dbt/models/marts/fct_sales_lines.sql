{{ config(materialized='table') }}
select
    l.line_id as sales_line_key,
    l.order_id,
    l.customer_id as customer_key,
    l.product_id as product_key,
    l.store_id as store_key,
    l.channel_code as channel_key,
    l.order_date,
    l.quantity,
    l.gross_revenue,
    l.net_revenue,
    l.cost_amount,
    l.net_revenue - l.cost_amount as margin_amount,
    l.discount_amount,
    l.tax_amount,
    case when l.discount_amount > 0.2 * l.gross_revenue then 'High' when l.discount_amount > 0 then 'Low' else 'None' end as discount_band,
    l.has_promo as is_promo
from {{ ref('int_order_lines_enriched') }} l
