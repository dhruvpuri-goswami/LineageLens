{% snapshot snap_customers %}
{{ config(unique_key='customer_id', strategy='timestamp', updated_at='created_at') }}
select * from {{ source('raw', 'customers') }}
{% endsnapshot %}
