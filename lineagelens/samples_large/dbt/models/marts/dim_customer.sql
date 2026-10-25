{{ config(materialized='table') }}
select
    c.customer_id as customer_key,
    c.customer_name,
    c.email as customer_email,
    c.country_code,
    c.customer_segment,
    c.loyalty_tier,
    c.created_at as customer_since,
    year(current_date) - c.birth_year as customer_age,
    case when co.lifetime_revenue > 5000 then 'Gold' when co.lifetime_revenue > 1000 then 'Silver' else 'Bronze' end as value_tier,
    co.first_order_date
from {{ ref('stg_crm_customers') }} c
left join {{ ref('int_customer_orders') }} co on c.customer_id = co.customer_id
