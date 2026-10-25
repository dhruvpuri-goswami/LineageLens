{{ config(materialized='table') }}
select
    l.line_id,
    l.order_id,
    o.customer_id,
    o.store_id,
    l.product_id,
    o.channel_code,
    o.order_date,
    o.order_status,
    o.has_promo,
    l.quantity,
    l.quantity * l.unit_price * fx.rate_to_usd as gross_revenue,
    l.quantity * l.unit_price * (1 - l.discount_pct) * fx.rate_to_usd as net_revenue,
    l.quantity * l.unit_cost * fx.rate_to_usd as cost_amount,
    l.quantity * l.unit_price * l.discount_pct * fx.rate_to_usd as discount_amount,
    l.quantity * l.unit_price * (1 - l.discount_pct) * l.tax_rate * fx.rate_to_usd as tax_amount
from {{ ref('stg_erp_order_lines') }} l
join {{ ref('stg_erp_orders') }} o on l.order_id = o.order_id
join {{ ref('stg_fx_rates') }} fx on fx.currency_code = o.currency_code and fx.rate_date = o.order_date
where o.order_status <> 'cancelled'
