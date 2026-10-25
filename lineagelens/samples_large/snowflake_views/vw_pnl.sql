-- P&L lines by month (SYNTHETIC SAMPLE)
create or replace view HELIOS.REPORTING.VW_PNL as
select
    date_trunc('month', g.posting_date) as period_month,
    a.pl_line,
    g.cost_center_key,
    sum(g.amount_usd) as actual_amount
from HELIOS.GOLD.FCT_GL g
join HELIOS.GOLD.DIM_ACCOUNT a on a.account_key = g.account_key
group by date_trunc('month', g.posting_date), a.pl_line, g.cost_center_key;
