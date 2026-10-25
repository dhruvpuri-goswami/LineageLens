{{ config(materialized='view') }}
select
    product_id,
    product_name,
    category as product_category,
    subcategory as product_subcategory,
    list_price,
    is_active
from {{ source('raw', 'products') }}
