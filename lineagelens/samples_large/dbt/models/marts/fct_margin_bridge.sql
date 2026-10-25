{{ config(materialized='table') }}
select
    s.order_date,
    sum(s.gross_revenue) as gross_revenue,
    sum(s.discount_amount) as discount_amount,
    sum(s.net_revenue) as net_revenue,
    sum(s.cost_amount) as cost_amount,
    sum(s.margin_amount) as margin_amount
from {{ ref('fct_sales_lines') }} s
group by s.order_date
