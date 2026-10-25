{{ config(materialized='table') }}
select
    p.product_id as product_key,
    p.sku,
    p.product_name,
    p.brand,
    p.category as product_category,
    p.subcategory as product_subcategory,
    p.list_price,
    case when p.list_price >= 200 then 'Premium' when p.list_price >= 50 then 'Core' else 'Value' end as price_band,
    p.launch_date
from {{ ref('stg_pim_products') }} p
