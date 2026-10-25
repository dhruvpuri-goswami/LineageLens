{{ config(materialized='table') }}
with customers as (
    select * from {{ ref('stg_customers') }}
),
countries as (
    select country_code, country_name from {{ ref('country_codes') }}
)
select
    c.customer_id as customer_key,
    c.customer_name,
    c.email as customer_email,
    c.customer_segment,
    case
        when c.customer_segment = 'Enterprise' then 'Tier 1'
        when c.customer_segment = 'SMB' then 'Tier 2'
        else 'Tier 3'
    end as customer_tier,
    co.country_name,
    c.created_at as customer_since
from customers c
left join countries co on c.country_code = co.country_code
qualify row_number() over (partition by c.customer_id order by c.created_at desc) = 1
