-- Calendar view maintained by the platform team (SAMPLE DATA).
create or replace view analytics.reporting.vw_dim_date
    (date_day, year_num, quarter_label, month_num, month_name, is_weekend)
as
select
    d.calendar_date,
    year(d.calendar_date),
    'Q' || quarter(d.calendar_date),
    month(d.calendar_date),
    monthname(d.calendar_date),
    dayofweekiso(d.calendar_date) in (6, 7)
from analytics.reference.calendar d
where d.calendar_date between '2020-01-01' and '2030-12-31';
