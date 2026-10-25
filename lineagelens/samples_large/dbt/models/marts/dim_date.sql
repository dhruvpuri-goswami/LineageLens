{{ config(materialized='table') }}
select distinct
    f.rate_date as date_day,
    year(f.rate_date) as calendar_year,
    quarter(f.rate_date) as calendar_quarter,
    month(f.rate_date) as calendar_month,
    to_char(f.rate_date, 'MON') as month_name,
    dayofweek(f.rate_date) as day_of_week
from {{ ref('stg_fx_rates') }} f
