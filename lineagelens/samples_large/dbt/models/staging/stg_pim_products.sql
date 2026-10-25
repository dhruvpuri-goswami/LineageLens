{{ config(materialized='view') }}
select
    product_id,
    sku,
    product_name,
    brand,
    category,
    subcategory,
    list_price,
    launch_date
from {{ source('raw', 'pim_products') }}
