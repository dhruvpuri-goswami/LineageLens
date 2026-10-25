{{ config(materialized='table') }}
select
    product_id as product_key,
    product_name,
    product_category,
    product_subcategory,
    list_price,
    case when list_price >= 500 then 'Premium' else 'Standard' end as price_band
from {{ ref('stg_products') }}
where is_active
