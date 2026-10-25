"""Generate the LARGE synthetic sample ("Helios Retail Group") used to test LineageLens at scale.

~45 dbt models / 400+ columns, 6 Snowflake views, 3 Power BI semantic models (TMDL) with 85+ measures in
chains, 4 RLS roles, a field parameter and a calculation group, 7 PBIR reports with 150+ visuals.
Everything is invented demo data - no real company, schema or report is reproduced.

Run:  python tools/make_large_sample.py
"""
from __future__ import annotations

import json
import random
import re
import shutil
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from make_report_samples import cat_filter, col, meas, agg, visual, write  # noqa: E402
from lineagelens.sqllineage import lineage_for_sql  # noqa: E402

OUT = HERE.parent / "lineagelens" / "samples_large"
PROJECT = "helios_analytics"
DB = "HELIOS"
RNG = random.Random(20261025)
_uuid_counter = [0]


def tag() -> str:
    _uuid_counter[0] += 1
    return str(uuid.UUID(int=0x5EED << 96 | _uuid_counter[0]))


# ----------------------------------------------------------------------------- sources (schema RAW)
SOURCES: dict[str, list[tuple[str, str]]] = {
    "erp_orders": [("ORDER_ID", "NUMBER"), ("CUSTOMER_ID", "NUMBER"), ("STORE_ID", "NUMBER"), ("CHANNEL_CODE", "VARCHAR"),
                   ("ORDER_TS", "TIMESTAMP_NTZ"), ("STATUS", "VARCHAR"), ("CURRENCY_CODE", "VARCHAR"), ("PROMO_CODE", "VARCHAR")],
    "erp_order_lines": [("LINE_ID", "NUMBER"), ("ORDER_ID", "NUMBER"), ("PRODUCT_ID", "NUMBER"), ("QTY", "NUMBER"),
                        ("UNIT_PRICE", "NUMBER(12,2)"), ("UNIT_COST", "NUMBER(12,2)"), ("DISCOUNT_PCT", "NUMBER(5,4)"), ("TAX_RATE", "NUMBER(5,4)")],
    "crm_customers": [("CUSTOMER_ID", "NUMBER"), ("FULL_NAME", "VARCHAR"), ("EMAIL", "VARCHAR"), ("COUNTRY_CODE", "VARCHAR"),
                      ("SEGMENT", "VARCHAR"), ("LOYALTY_TIER", "VARCHAR"), ("CREATED_AT", "TIMESTAMP_NTZ"), ("BIRTH_YEAR", "NUMBER")],
    "pim_products": [("PRODUCT_ID", "NUMBER"), ("SKU", "VARCHAR"), ("PRODUCT_NAME", "VARCHAR"), ("BRAND", "VARCHAR"),
                     ("CATEGORY", "VARCHAR"), ("SUBCATEGORY", "VARCHAR"), ("LIST_PRICE", "NUMBER(12,2)"), ("LAUNCH_DATE", "DATE")],
    "ops_stores": [("STORE_ID", "NUMBER"), ("STORE_NAME", "VARCHAR"), ("REGION", "VARCHAR"), ("COUNTRY_CODE", "VARCHAR"),
                   ("STORE_FORMAT", "VARCHAR"), ("OPENED_ON", "DATE"), ("MANAGER_EMAIL", "VARCHAR"), ("SQ_FT", "NUMBER")],
    "wms_inventory": [("SNAPSHOT_DATE", "DATE"), ("STORE_ID", "NUMBER"), ("PRODUCT_ID", "NUMBER"), ("ON_HAND_QTY", "NUMBER"),
                      ("ON_ORDER_QTY", "NUMBER"), ("SAFETY_STOCK", "NUMBER"), ("UNIT_COST", "NUMBER(12,2)")],
    "scm_purchase_orders": [("PO_ID", "NUMBER"), ("SUPPLIER_ID", "NUMBER"), ("PRODUCT_ID", "NUMBER"), ("ORDERED_QTY", "NUMBER"),
                            ("RECEIVED_QTY", "NUMBER"), ("PO_DATE", "DATE"), ("EXPECTED_DATE", "DATE"), ("RECEIVED_DATE", "DATE"), ("PO_COST", "NUMBER(14,2)")],
    "scm_suppliers": [("SUPPLIER_ID", "NUMBER"), ("SUPPLIER_NAME", "VARCHAR"), ("COUNTRY_CODE", "VARCHAR"), ("RATING", "NUMBER(3,1)"), ("LEAD_TIME_DAYS", "NUMBER")],
    "fin_gl_entries": [("ENTRY_ID", "NUMBER"), ("ACCOUNT_ID", "NUMBER"), ("COST_CENTER_ID", "NUMBER"), ("POSTING_DATE", "DATE"),
                       ("AMOUNT", "NUMBER(16,2)"), ("CURRENCY_CODE", "VARCHAR"), ("ENTRY_TYPE", "VARCHAR")],
    "fin_accounts": [("ACCOUNT_ID", "NUMBER"), ("ACCOUNT_NAME", "VARCHAR"), ("ACCOUNT_GROUP", "VARCHAR"), ("PL_LINE", "VARCHAR")],
    "fin_budgets": [("BUDGET_ID", "NUMBER"), ("COST_CENTER_ID", "NUMBER"), ("ACCOUNT_ID", "NUMBER"), ("PERIOD_MONTH", "DATE"), ("BUDGET_AMOUNT", "NUMBER(16,2)")],
    "mkt_campaigns": [("CAMPAIGN_ID", "NUMBER"), ("CAMPAIGN_NAME", "VARCHAR"), ("CHANNEL", "VARCHAR"), ("START_DATE", "DATE"),
                      ("END_DATE", "DATE"), ("SPEND", "NUMBER(14,2)")],
    "web_sessions": [("SESSION_ID", "VARCHAR"), ("CUSTOMER_ID", "NUMBER"), ("SESSION_TS", "TIMESTAMP_NTZ"), ("DEVICE", "VARCHAR"),
                     ("PAGE_VIEWS", "NUMBER"), ("CAMPAIGN_ID", "NUMBER"), ("CONVERTED", "BOOLEAN")],
    "hr_cost_centers": [("COST_CENTER_ID", "NUMBER"), ("COST_CENTER_NAME", "VARCHAR"), ("REGION", "VARCHAR"), ("OWNER_EMAIL", "VARCHAR")],
    "fx_rates": [("RATE_DATE", "DATE"), ("CURRENCY_CODE", "VARCHAR"), ("RATE_TO_USD", "NUMBER(18,8)")],
}

# ----------------------------------------------------------------------------- models
# name -> (folder, schema, materialized, description, sql with {{ ref() }} / {{ source() }})
MODELS: dict[str, tuple[str, str, str, str, str]] = {}


def model(name: str, desc: str, sql: str, folder: str | None = None, mat: str | None = None):
    folder = folder or ("staging" if name.startswith("stg_") else "intermediate" if name.startswith("int_") else "marts")
    schema = {"staging": "STAGING", "intermediate": "INTERMEDIATE", "marts": "GOLD"}[folder]
    mat = mat or ("view" if folder == "staging" else "ephemeral" if False else "table")
    MODELS[name] = (folder, schema, mat, desc, sql.strip() + "\n")


def sel(cols: list[tuple[str, str]]) -> str:
    return ",\n".join(f"    {e} as {o.lower()}" if e.lower() != o.lower() and not e.lower().endswith("." + o.lower()) else f"    {e}" for o, e in cols)


STG = {
    "erp_orders": [("ORDER_ID", "order_id"), ("CUSTOMER_ID", "customer_id"), ("STORE_ID", "store_id"), ("CHANNEL_CODE", "upper(channel_code)"),
                   ("ORDER_DATE", "order_ts::date"), ("ORDER_STATUS", "lower(status)"), ("CURRENCY_CODE", "currency_code"),
                   ("HAS_PROMO", "promo_code is not null")],
    "erp_order_lines": [("LINE_ID", "line_id"), ("ORDER_ID", "order_id"), ("PRODUCT_ID", "product_id"), ("QUANTITY", "qty"),
                        ("UNIT_PRICE", "unit_price"), ("UNIT_COST", "unit_cost"), ("DISCOUNT_PCT", "coalesce(discount_pct, 0)"), ("TAX_RATE", "tax_rate")],
    "crm_customers": [("CUSTOMER_ID", "customer_id"), ("CUSTOMER_NAME", "initcap(full_name)"), ("EMAIL", "lower(email)"), ("COUNTRY_CODE", "country_code"),
                      ("CUSTOMER_SEGMENT", "segment"), ("LOYALTY_TIER", "coalesce(loyalty_tier, 'None')"), ("CREATED_AT", "created_at"), ("BIRTH_YEAR", "birth_year")],
    "pim_products": [("PRODUCT_ID", "product_id"), ("SKU", "sku"), ("PRODUCT_NAME", "product_name"), ("BRAND", "brand"), ("CATEGORY", "category"),
                     ("SUBCATEGORY", "subcategory"), ("LIST_PRICE", "list_price"), ("LAUNCH_DATE", "launch_date")],
    "ops_stores": [("STORE_ID", "store_id"), ("STORE_NAME", "store_name"), ("SALES_REGION", "region"), ("COUNTRY_CODE", "country_code"),
                   ("STORE_FORMAT", "store_format"), ("OPENED_ON", "opened_on"), ("MANAGER_EMAIL", "lower(manager_email)"), ("SQ_FT", "sq_ft")],
    "wms_inventory": [("SNAPSHOT_DATE", "snapshot_date"), ("STORE_ID", "store_id"), ("PRODUCT_ID", "product_id"), ("ON_HAND_QTY", "on_hand_qty"),
                      ("ON_ORDER_QTY", "on_order_qty"), ("SAFETY_STOCK", "safety_stock"), ("UNIT_COST", "unit_cost")],
    "scm_purchase_orders": [("PO_ID", "po_id"), ("SUPPLIER_ID", "supplier_id"), ("PRODUCT_ID", "product_id"), ("ORDERED_QTY", "ordered_qty"),
                            ("RECEIVED_QTY", "coalesce(received_qty, 0)"), ("PO_DATE", "po_date"), ("EXPECTED_DATE", "expected_date"),
                            ("RECEIVED_DATE", "received_date"), ("PO_COST", "po_cost")],
    "scm_suppliers": [("SUPPLIER_ID", "supplier_id"), ("SUPPLIER_NAME", "supplier_name"), ("COUNTRY_CODE", "country_code"), ("RATING", "rating"),
                      ("LEAD_TIME_DAYS", "lead_time_days")],
    "fin_gl_entries": [("ENTRY_ID", "entry_id"), ("ACCOUNT_ID", "account_id"), ("COST_CENTER_ID", "cost_center_id"), ("POSTING_DATE", "posting_date"),
                       ("AMOUNT_LOCAL", "amount"), ("CURRENCY_CODE", "currency_code"), ("ENTRY_TYPE", "entry_type")],
    "fin_accounts": [("ACCOUNT_ID", "account_id"), ("ACCOUNT_NAME", "account_name"), ("ACCOUNT_GROUP", "account_group"), ("PL_LINE", "pl_line")],
    "fin_budgets": [("BUDGET_ID", "budget_id"), ("COST_CENTER_ID", "cost_center_id"), ("ACCOUNT_ID", "account_id"), ("PERIOD_MONTH", "period_month"),
                    ("BUDGET_AMOUNT", "budget_amount")],
    "mkt_campaigns": [("CAMPAIGN_ID", "campaign_id"), ("CAMPAIGN_NAME", "campaign_name"), ("MARKETING_CHANNEL", "channel"), ("START_DATE", "start_date"),
                      ("END_DATE", "end_date"), ("SPEND", "spend")],
    "web_sessions": [("SESSION_ID", "session_id"), ("CUSTOMER_ID", "customer_id"), ("SESSION_DATE", "session_ts::date"), ("DEVICE", "lower(device)"),
                     ("PAGE_VIEWS", "page_views"), ("CAMPAIGN_ID", "campaign_id"), ("IS_CONVERTED", "converted")],
    "hr_cost_centers": [("COST_CENTER_ID", "cost_center_id"), ("COST_CENTER_NAME", "cost_center_name"), ("REGION", "region"), ("OWNER_EMAIL", "lower(owner_email)")],
    "fx_rates": [("RATE_DATE", "rate_date"), ("CURRENCY_CODE", "currency_code"), ("RATE_TO_USD", "rate_to_usd")],
}
for src, cols in STG.items():
    model(f"stg_{src}", f"Staged {src.replace('_', ' ')}", f"select\n{sel(cols)}\nfrom {{{{ source('raw', '{src}') }}}}")

model("int_order_lines_enriched", "Order lines joined to headers, converted to USD", """
select
    l.line_id,
    l.order_id,
    o.customer_id,
    o.store_id,
    l.product_id,
    o.channel_code,
    o.order_date,
    o.order_status,
    o.has_promo,
    l.quantity,
    l.quantity * l.unit_price * fx.rate_to_usd as gross_revenue,
    l.quantity * l.unit_price * (1 - l.discount_pct) * fx.rate_to_usd as net_revenue,
    l.quantity * l.unit_cost * fx.rate_to_usd as cost_amount,
    l.quantity * l.unit_price * l.discount_pct * fx.rate_to_usd as discount_amount,
    l.quantity * l.unit_price * (1 - l.discount_pct) * l.tax_rate * fx.rate_to_usd as tax_amount
from {{ ref('stg_erp_order_lines') }} l
join {{ ref('stg_erp_orders') }} o on l.order_id = o.order_id
join {{ ref('stg_fx_rates') }} fx on fx.currency_code = o.currency_code and fx.rate_date = o.order_date
where o.order_status <> 'cancelled'
""")
model("int_customer_orders", "Per-customer order history", """
select
    customer_id,
    min(order_date) as first_order_date,
    max(order_date) as last_order_date,
    count(distinct order_id) as lifetime_orders,
    sum(net_revenue) as lifetime_revenue,
    sum(net_revenue - cost_amount) as lifetime_margin
from {{ ref('int_order_lines_enriched') }}
group by customer_id
""")
model("int_inventory_daily", "Daily inventory with stock value", """
select
    i.snapshot_date,
    i.store_id,
    i.product_id,
    i.on_hand_qty,
    i.on_order_qty,
    i.safety_stock,
    i.on_hand_qty * i.unit_cost as stock_value,
    case when i.on_hand_qty < i.safety_stock then 1 else 0 end as is_below_safety
from {{ ref('stg_wms_inventory') }} i
""")
model("int_po_receipts", "Purchase orders with lead-time and fill-rate", """
select
    po.po_id,
    po.supplier_id,
    po.product_id,
    po.po_date,
    po.ordered_qty,
    po.received_qty,
    po.po_cost,
    datediff('day', po.po_date, po.received_date) as actual_lead_days,
    datediff('day', po.expected_date, po.received_date) as days_late,
    po.received_qty / nullif(po.ordered_qty, 0) as fill_rate
from {{ ref('stg_scm_purchase_orders') }} po
""")
model("int_gl_usd", "GL entries converted to USD", """
select
    g.entry_id,
    g.account_id,
    g.cost_center_id,
    g.posting_date,
    g.entry_type,
    g.amount_local * fx.rate_to_usd as amount_usd
from {{ ref('stg_fin_gl_entries') }} g
join {{ ref('stg_fx_rates') }} fx on fx.currency_code = g.currency_code and fx.rate_date = g.posting_date
""")
model("int_budget_monthly", "Monthly budget by account and cost centre", """
select
    b.period_month,
    b.cost_center_id,
    b.account_id,
    sum(b.budget_amount) as budget_amount
from {{ ref('stg_fin_budgets') }} b
group by b.period_month, b.cost_center_id, b.account_id
""")
model("int_sessions_attributed", "Web sessions with campaign attribution", """
select
    s.session_id,
    s.customer_id,
    s.session_date,
    s.device,
    s.page_views,
    s.is_converted,
    c.campaign_id,
    c.marketing_channel
from {{ ref('stg_web_sessions') }} s
left join {{ ref('stg_mkt_campaigns') }} c on s.campaign_id = c.campaign_id
""")
model("int_product_margin", "Product level revenue and margin", """
select
    product_id,
    sum(quantity) as units_sold,
    sum(net_revenue) as net_revenue,
    sum(net_revenue - cost_amount) as margin_amount
from {{ ref('int_order_lines_enriched') }}
group by product_id
""")

# gold / marts ---------------------------------------------------------------
model("dim_customer", "Customer dimension", """
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
""")
model("dim_product", "Product dimension", """
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
""")
model("dim_store", "Store dimension", """
select
    s.store_id as store_key,
    s.store_name,
    s.sales_region,
    s.country_code,
    s.store_format,
    s.opened_on,
    s.manager_email,
    s.sq_ft
from {{ ref('stg_ops_stores') }} s
""")
model("dim_date", "Calendar", """
select distinct
    f.rate_date as date_day,
    year(f.rate_date) as calendar_year,
    quarter(f.rate_date) as calendar_quarter,
    month(f.rate_date) as calendar_month,
    to_char(f.rate_date, 'MON') as month_name,
    dayofweek(f.rate_date) as day_of_week
from {{ ref('stg_fx_rates') }} f
""")
model("dim_supplier", "Supplier dimension", """
select
    s.supplier_id as supplier_key,
    s.supplier_name,
    s.country_code as supplier_country,
    s.rating as supplier_rating,
    s.lead_time_days as contracted_lead_days
from {{ ref('stg_scm_suppliers') }} s
""")
model("dim_account", "Chart of accounts", """
select
    a.account_id as account_key,
    a.account_name,
    a.account_group,
    a.pl_line
from {{ ref('stg_fin_accounts') }} a
""")
model("dim_cost_center", "Cost centres", """
select
    c.cost_center_id as cost_center_key,
    c.cost_center_name,
    c.region as cost_center_region,
    c.owner_email
from {{ ref('stg_hr_cost_centers') }} c
""")
model("dim_campaign", "Marketing campaigns", """
select
    c.campaign_id as campaign_key,
    c.campaign_name,
    c.marketing_channel,
    c.start_date as campaign_start,
    c.end_date as campaign_end,
    c.spend as campaign_spend
from {{ ref('stg_mkt_campaigns') }} c
""")
model("dim_channel", "Sales channels", """
select distinct
    o.channel_code as channel_key,
    case o.channel_code when 'WEB' then 'Online' when 'APP' then 'Mobile app' else 'Store' end as channel_name
from {{ ref('stg_erp_orders') }} o
""")
model("fct_sales_lines", "Sales at order-line grain (gold)", """
select
    l.line_id as sales_line_key,
    l.order_id,
    l.customer_id as customer_key,
    l.product_id as product_key,
    l.store_id as store_key,
    l.channel_code as channel_key,
    l.order_date,
    l.quantity,
    l.gross_revenue,
    l.net_revenue,
    l.cost_amount,
    l.net_revenue - l.cost_amount as margin_amount,
    l.discount_amount,
    l.tax_amount,
    case when l.discount_amount > 0.2 * l.gross_revenue then 'High' when l.discount_amount > 0 then 'Low' else 'None' end as discount_band,
    l.has_promo as is_promo
from {{ ref('int_order_lines_enriched') }} l
""")
model("fct_orders", "Order header facts", """
select
    l.order_id as order_key,
    l.customer_id as customer_key,
    l.store_id as store_key,
    l.channel_code as channel_key,
    l.order_date,
    count(*) as line_count,
    sum(l.quantity) as units,
    sum(l.net_revenue) as order_revenue,
    sum(l.net_revenue - l.cost_amount) as order_margin
from {{ ref('int_order_lines_enriched') }} l
group by l.order_id, l.customer_id, l.store_id, l.channel_code, l.order_date
""")
model("fct_daily_sales", "Daily sales by store", """
select
    s.order_date,
    s.store_key,
    sum(s.net_revenue) as net_revenue,
    sum(s.margin_amount) as margin_amount,
    sum(s.quantity) as units,
    count(distinct s.order_id) as order_count
from {{ ref('fct_sales_lines') }} s
group by s.order_date, s.store_key
""")
model("fct_inventory_snapshot", "Inventory snapshot (gold)", """
select
    i.snapshot_date,
    i.store_id as store_key,
    i.product_id as product_key,
    i.on_hand_qty,
    i.on_order_qty,
    i.safety_stock,
    i.stock_value,
    i.is_below_safety
from {{ ref('int_inventory_daily') }} i
""")
model("fct_purchase_orders", "Purchase order facts", """
select
    r.po_id as po_key,
    r.supplier_id as supplier_key,
    r.product_id as product_key,
    r.po_date,
    r.ordered_qty,
    r.received_qty,
    r.po_cost,
    r.actual_lead_days,
    r.days_late,
    r.fill_rate
from {{ ref('int_po_receipts') }} r
""")
model("fct_gl", "General ledger facts (USD)", """
select
    g.entry_id as gl_key,
    g.account_id as account_key,
    g.cost_center_id as cost_center_key,
    g.posting_date,
    g.entry_type,
    g.amount_usd
from {{ ref('int_gl_usd') }} g
""")
model("fct_budget", "Budget facts", """
select
    b.period_month,
    b.cost_center_id as cost_center_key,
    b.account_id as account_key,
    b.budget_amount
from {{ ref('int_budget_monthly') }} b
""")
model("fct_web_sessions", "Web sessions (gold)", """
select
    s.session_id as session_key,
    s.customer_id as customer_key,
    s.campaign_id as campaign_key,
    s.session_date,
    s.device,
    s.page_views,
    case when s.is_converted then 1 else 0 end as conversions
from {{ ref('int_sessions_attributed') }} s
""")
model("fct_campaign_performance", "Campaign spend vs. attributed revenue", """
select
    c.campaign_key,
    c.campaign_spend,
    count(distinct w.session_key) as sessions,
    sum(w.conversions) as conversions,
    sum(o.order_revenue) as attributed_revenue
from {{ ref('dim_campaign') }} c
left join {{ ref('fct_web_sessions') }} w on w.campaign_key = c.campaign_key
left join {{ ref('fct_orders') }} o on o.customer_key = w.customer_key and o.order_date = w.session_date
group by c.campaign_key, c.campaign_spend
""")
model("fct_customer_ltv", "Customer lifetime value", """
select
    co.customer_id as customer_key,
    co.first_order_date,
    co.last_order_date,
    co.lifetime_orders,
    co.lifetime_revenue,
    co.lifetime_margin,
    co.lifetime_revenue / nullif(co.lifetime_orders, 0) as avg_order_value,
    datediff('day', co.last_order_date, current_date) as days_since_last_order
from {{ ref('int_customer_orders') }} co
""")
model("fct_product_performance", "Product performance", """
select
    pm.product_id as product_key,
    pm.units_sold,
    pm.net_revenue,
    pm.margin_amount,
    pm.margin_amount / nullif(pm.net_revenue, 0) as margin_pct
from {{ ref('int_product_margin') }} pm
""")
model("fct_store_performance", "Store performance", """
select
    d.store_key,
    sum(d.net_revenue) as net_revenue,
    sum(d.margin_amount) as margin_amount,
    sum(d.order_count) as order_count,
    sum(d.net_revenue) / nullif(max(st.sq_ft), 0) as revenue_per_sq_ft
from {{ ref('fct_daily_sales') }} d
join {{ ref('dim_store') }} st on st.store_key = d.store_key
group by d.store_key
""")
model("fct_margin_bridge", "Revenue to margin bridge", """
select
    s.order_date,
    sum(s.gross_revenue) as gross_revenue,
    sum(s.discount_amount) as discount_amount,
    sum(s.net_revenue) as net_revenue,
    sum(s.cost_amount) as cost_amount,
    sum(s.margin_amount) as margin_amount
from {{ ref('fct_sales_lines') }} s
group by s.order_date
""")
model("fct_returns", "Returns (orders in returned status)", """
select
    l.line_id as return_key,
    l.product_id as product_key,
    l.store_id as store_key,
    l.order_date as return_date,
    l.quantity as returned_units,
    l.net_revenue as refund_amount
from {{ ref('int_order_lines_enriched') }} l
where l.order_status = 'returned'
""")

# ----------------------------------------------------------------------------- Snowflake views (REPORTING)
VIEWS = {
    "VW_SALES_KPI": ("Daily KPI feed for the commercial scorecard", """
select
    d.order_date,
    st.sales_region,
    sum(d.net_revenue) as net_revenue,
    sum(d.margin_amount) as margin_amount,
    sum(d.order_count) as order_count
from HELIOS.GOLD.FCT_DAILY_SALES d
join HELIOS.GOLD.DIM_STORE st on st.store_key = d.store_key
group by d.order_date, st.sales_region"""),
    "VW_INVENTORY_HEALTH": ("Stock cover by store and product", """
select
    i.snapshot_date,
    i.store_key,
    i.product_key,
    i.on_hand_qty,
    i.stock_value,
    i.on_hand_qty / nullif(i.safety_stock, 0) as cover_ratio
from HELIOS.GOLD.FCT_INVENTORY_SNAPSHOT i"""),
    "VW_SUPPLIER_SCORECARD": ("Supplier OTIF scorecard", """
select
    s.supplier_key,
    s.supplier_name,
    avg(p.fill_rate) as avg_fill_rate,
    avg(p.days_late) as avg_days_late,
    sum(p.po_cost) as total_spend
from HELIOS.GOLD.FCT_PURCHASE_ORDERS p
join HELIOS.GOLD.DIM_SUPPLIER s on s.supplier_key = p.supplier_key
group by s.supplier_key, s.supplier_name"""),
    "VW_PNL": ("P&L lines by month", """
select
    date_trunc('month', g.posting_date) as period_month,
    a.pl_line,
    g.cost_center_key,
    sum(g.amount_usd) as actual_amount
from HELIOS.GOLD.FCT_GL g
join HELIOS.GOLD.DIM_ACCOUNT a on a.account_key = g.account_key
group by date_trunc('month', g.posting_date), a.pl_line, g.cost_center_key"""),
    "VW_CAMPAIGN_ROI": ("Campaign ROI", """
select
    c.campaign_key,
    dc.campaign_name,
    dc.marketing_channel,
    c.campaign_spend,
    c.attributed_revenue,
    c.attributed_revenue / nullif(c.campaign_spend, 0) as roas
from HELIOS.GOLD.FCT_CAMPAIGN_PERFORMANCE c
join HELIOS.GOLD.DIM_CAMPAIGN dc on dc.campaign_key = c.campaign_key"""),
    "VW_STORE_LEAGUE": ("Store league table", """
select
    sp.store_key,
    st.store_name,
    st.sales_region,
    sp.net_revenue,
    sp.revenue_per_sq_ft,
    rank() over (partition by st.sales_region order by sp.net_revenue desc) as region_rank
from HELIOS.GOLD.FCT_STORE_PERFORMANCE sp
join HELIOS.GOLD.DIM_STORE st on st.store_key = sp.store_key"""),
}


def ctype(c: str) -> str:
    c = c.upper()
    if c.endswith(("_ID", "_KEY")) and c not in ("SESSION_ID", "SESSION_KEY", "CHANNEL_KEY"):
        return "NUMBER"
    if c.endswith(("_DATE", "_ON", "_DAY", "_MONTH", "_START", "_END")) or c in ("FIRST_ORDER_DATE",):
        return "DATE"
    if c.endswith(("_AT", "_TS", "_SINCE")):
        return "TIMESTAMP_NTZ"
    if any(k in c for k in ("REVENUE", "AMOUNT", "COST", "VALUE", "SPEND", "PRICE", "MARGIN", "RATE", "PCT", "RATIO", "ROAS", "SQ_FT")):
        return "NUMBER(38,4)"
    if any(k in c for k in ("QTY", "QUANTITY", "UNITS", "COUNT", "ORDERS", "DAYS", "VIEWS", "CONVERSIONS", "SESSIONS", "RANK", "YEAR", "QUARTER", "MONTH", "AGE", "STOCK", "IS_BELOW")):
        return "NUMBER"
    if c.startswith(("IS_", "HAS_")):
        return "BOOLEAN"
    return "VARCHAR"


def rel(schema: str, name: str) -> str:
    return f"{DB}.{schema}.{name.upper()}"


def compile_sql(raw: str) -> tuple[str, list[str]]:
    deps: list[str] = []

    def src(m):
        deps.append(f"source.{PROJECT}.raw.{m.group(2)}")
        return rel("RAW", m.group(2)).lower()

    def ref(m):
        deps.append(f"model.{PROJECT}.{m.group(1)}")
        return rel(MODELS[m.group(1)][1], m.group(1)).lower()

    out = re.sub(r"\{\{\s*source\('(\w+)',\s*'(\w+)'\)\s*\}\}", src, raw)
    out = re.sub(r"\{\{\s*ref\('(\w+)'\)\s*\}\}", ref, out)
    return out, list(dict.fromkeys(deps))


def dbt_project(root: Path) -> dict[str, list[str]]:
    """Write manifest/catalog. Returns {relation: [columns]} for gold models and views."""
    t = root / "target"
    t.mkdir(parents=True, exist_ok=True)
    schema: dict = {DB: {"RAW": {}, "STAGING": {}, "INTERMEDIATE": {}, "GOLD": {}}}
    nodes, sources, cat_nodes, cat_sources, parent_map = {}, {}, {}, {}, {}
    for s, cols in SOURCES.items():
        uid = f"source.{PROJECT}.raw.{s}"
        schema[DB]["RAW"][s.upper()] = {c: ty for c, ty in cols}
        sources[uid] = {"resource_type": "source", "unique_id": uid, "package_name": PROJECT, "source_name": "raw", "name": s,
                        "identifier": s.upper(), "database": DB, "schema": "RAW", "path": "models/staging/_sources.yml",
                        "original_file_path": "models/staging/_sources.yml", "fqn": [PROJECT, "staging", "raw", s],
                        "description": f"Raw {s.replace('_', ' ')} (synthetic)", "relation_name": rel("RAW", s),
                        "columns": {c.lower(): {"name": c.lower(), "description": "", "data_type": ty} for c, ty in cols}, "meta": {}, "tags": []}
        cat_sources[uid] = {"metadata": {"type": "BASE TABLE", "schema": "RAW", "name": s.upper(), "database": DB},
                            "columns": {c: {"type": ty, "index": i + 1, "name": c} for i, (c, ty) in enumerate(cols)}, "stats": {}, "unique_id": uid}
        parent_map[uid] = []
    out_cols: dict[str, list[str]] = {}
    for name, (folder, sch, mat, desc, raw) in MODELS.items():
        uid = f"model.{PROJECT}.{name}"
        compiled, deps = compile_sql(raw)
        ql = lineage_for_sql(compiled, schema, default_db=DB, default_schema=sch)
        cols = [c.name for c in ql.columns]
        assert cols, name
        bad = [c.name for c in ql.columns if not c.sources and c.transform != "constant"]
        if bad:
            print(f"  note: {name} unresolved {bad}")
        schema[DB][sch][name.upper()] = {c: ctype(c) for c in cols}
        out_cols[rel(sch, name)] = cols
        (root / "models" / folder).mkdir(parents=True, exist_ok=True)
        (root / "models" / folder / f"{name}.sql").write_text(f"{{{{ config(materialized='{mat}') }}}}\n" + raw, encoding="utf-8")
        nodes[uid] = {"resource_type": "model", "unique_id": uid, "name": name, "package_name": PROJECT, "alias": name, "database": DB,
                      "schema": sch, "path": f"{folder}/{name}.sql", "original_file_path": f"models/{folder}/{name}.sql",
                      "fqn": [PROJECT, folder, name], "config": {"materialized": mat, "enabled": True, "tags": [folder]}, "tags": [folder],
                      "description": desc, "columns": {}, "depends_on": {"nodes": deps, "macros": []}, "raw_code": raw,
                      "compiled_code": compiled, "compiled": True, "relation_name": rel(sch, name), "language": "sql"}
        cat_nodes[uid] = {"metadata": {"type": "VIEW" if mat == "view" else "BASE TABLE", "schema": sch, "name": name.upper(), "database": DB},
                          "columns": {c: {"type": ctype(c), "index": i + 1, "name": c} for i, c in enumerate(cols)}, "stats": {}, "unique_id": uid}
        parent_map[uid] = deps
    child_map: dict = {k: [] for k in parent_map}
    for c, ps in parent_map.items():
        for p in ps:
            child_map.setdefault(p, []).append(c)
    meta = {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "dbt_version": "1.9.4",
            "generated_at": "2026-10-24T08:00:00.000Z", "invocation_id": "helios-large-sample", "project_name": PROJECT, "adapter_type": "snowflake"}
    manifest = {"metadata": meta, "nodes": nodes, "sources": sources, "macros": {}, "docs": {}, "exposures": {}, "metrics": {},
                "groups": {}, "selectors": {}, "disabled": {}, "parent_map": parent_map, "child_map": child_map}
    (t / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (t / "catalog.json").write_text(json.dumps({"metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/catalog/v1.json",
                                                             "dbt_version": "1.9.4", "generated_at": meta["generated_at"]},
                                                "nodes": cat_nodes, "sources": cat_sources, "errors": None}, indent=1), encoding="utf-8")
    (root / "dbt_project.yml").write_text(f"name: {PROJECT}\nversion: '1.0.0'\nprofile: {PROJECT}\nmodel-paths: [\"models\"]\n", encoding="utf-8")
    # views
    vd = root.parent / "snowflake_views"
    vd.mkdir(parents=True, exist_ok=True)
    for v, (desc, sql) in VIEWS.items():
        (vd / f"{v.lower()}.sql").write_text(f"-- {desc} (SYNTHETIC SAMPLE)\ncreate or replace view {DB}.REPORTING.{v} as{sql};\n", encoding="utf-8")
        ql = lineage_for_sql(sql, schema, default_db=DB, default_schema="GOLD")
        out_cols[rel("REPORTING", v)] = [c.name for c in ql.columns]
    return out_cols


# ----------------------------------------------------------------------------- Power BI
def pretty(c: str) -> str:
    words = c.lower().split("_")
    fix = {"id": "ID", "usd": "USD", "sku": "SKU", "po": "PO", "pct": "%", "sq": "Sq", "ft": "Ft", "roas": "ROAS", "pl": "P&L"}
    return " ".join(fix.get(w, w.capitalize()) for w in words)


def q(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


class Table:
    def __init__(self, name: str, relation: str, cols: list[str], desc: str = "", hidden_keys: bool = True, native: bool = False):
        self.name, self.relation, self.desc, self.native = name, relation, desc, native
        self.cols = [(c, pretty(c)) for c in cols]
        self.measures: list[tuple[str, str, str, str]] = []  # name, expr, fmt, folder
        self.calc_cols: list[tuple[str, str, str]] = []
        self.hidden_keys = hidden_keys

    def col(self, src: str) -> str:
        return dict(self.cols)[src.upper()]

    def m(self, name: str, expr: str, fmt: str = "#,0", folder: str = "") -> str:
        self.measures.append((name, expr, fmt, folder))
        return name

    def tmdl(self) -> str:
        db, schema, obj = self.relation.split(".")
        kind = "View" if schema == "REPORTING" else "Table"
        out = []
        if self.desc:
            out.append(f"/// {self.desc}")
        out += [f"table {q(self.name)}", f"\tlineageTag: {tag()}", ""]
        for n, e, fmt, folder in self.measures:
            out += [f"\tmeasure {q(n)} = {e}", f"\t\tformatString: {fmt}"]
            if folder:
                out.append(f"\t\tdisplayFolder: {folder}")
            out += [f"\t\tlineageTag: {tag()}", ""]
        for src, pc in self.cols:
            t = ctype(src)
            dt = "int64" if t == "NUMBER" else "decimal" if t.startswith("NUMBER(") else "dateTime" if t in ("DATE", "TIMESTAMP_NTZ") else "boolean" if t == "BOOLEAN" else "string"
            out += [f"\tcolumn {q(pc)}", f"\t\tdataType: {dt}"]
            if self.hidden_keys and src.endswith("_KEY"):
                out.append("\t\tisHidden")
            out += [f"\t\tlineageTag: {tag()}", f"\t\tsummarizeBy: {'sum' if dt == 'decimal' else 'none'}", f"\t\tsourceColumn: {src if self.native else pc}", ""]
        for n, e, dt in self.calc_cols:
            out += [f"\tcolumn {q(n)} = {e}", f"\t\tdataType: {dt}", f"\t\tlineageTag: {tag()}", "\t\tsummarizeBy: none", ""]
        if self.native:
            sql = "select " + ", ".join(f"v.{c.lower()}" for c, _ in self.cols) + f"#(lf)from {self.relation} v"
            out += [f"\tpartition {q(self.name)} = m", "\t\tmode: directQuery", "\t\tsource =", "\t\t\t\tlet",
                    '\t\t\t\t    Source = Snowflake.Databases(SnowflakeAccount, Warehouse, [Implementation="2.0"]),',
                    f'\t\t\t\t    DB = Source{{[Name="{db}", Kind="Database"]}}[Data],',
                    f'\t\t\t\t    Query = Value.NativeQuery(DB, "{sql}", null, [EnableFolding=true])',
                    "\t\t\t\tin", "\t\t\t\t    Query", "", "\tannotation PBI_ResultType = Table", ""]
            return "\n".join(out)
        sel_cols = ", ".join(f'"{c}"' for c, _ in self.cols)
        ren = ", ".join(f'{{"{c}", "{p}"}}' for c, p in self.cols)
        out += [f"\tpartition {q(self.name)} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
                '\t\t\t\t    Source = Snowflake.Databases(SnowflakeAccount, Warehouse, [Implementation="2.0"]),',
                f'\t\t\t\t    DB = Source{{[Name="{db}", Kind="Database"]}}[Data],',
                f'\t\t\t\t    Sch = DB{{[Name="{schema}", Kind="Schema"]}}[Data],',
                f'\t\t\t\t    Obj = Sch{{[Name="{obj}", Kind="{kind}"]}}[Data],',
                f'\t\t\t\t    #"Selected Columns" = Table.SelectColumns(Obj, {{{sel_cols}}}),',
                f'\t\t\t\t    #"Renamed Columns" = Table.RenameColumns(#"Selected Columns", {{{ren}}})',
                "\t\t\t\tin", '\t\t\t\t    #"Renamed Columns"', "", "\tannotation PBI_ResultType = Table", ""]
        return "\n".join(out)


def time_intel(t: Table, base: str, date_ref: str, folder: str = "Time Intelligence", fmt: str = "\\$#,0") -> list[str]:
    py = t.m(f"{base} PY", f"CALCULATE([{base}], SAMEPERIODLASTYEAR({date_ref}))", fmt, folder)
    yoy = t.m(f"{base} YoY %", f"DIVIDE([{base}] - [{py}], [{py}])", "0.0%", folder)
    ytd = t.m(f"{base} YTD", f"TOTALYTD([{base}], {date_ref})", fmt, folder)
    lbl = t.m(f"{base} YoY Label", f'FORMAT([{yoy}], "+0.0%;-0.0%") & " vs PY"', "", "Labels")
    return [py, yoy, ytd, lbl]


def write_model(root: Path, name: str, tables: list[Table], roles: dict[str, list[tuple[str, str]]], extra_tables: list[str], rels: list[tuple[str, str]]):
    d = root / f"{name}.SemanticModel"
    if d.exists():
        shutil.rmtree(d)
    (d / "definition" / "tables").mkdir(parents=True)
    (d / "definition" / "roles").mkdir(parents=True)
    (d / "definition.pbism").write_text(json.dumps({"version": "4.2", "settings": {}}, indent=2), encoding="utf-8")
    (d / "definition" / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1601\n", encoding="utf-8")
    (d / "definition" / "expressions.tmdl").write_text(
        'expression SnowflakeAccount = "helios-demo.example.snowflakecomputing.com" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag()}\n\n"
        'expression Warehouse = "BI_WH" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
        f"\tlineageTag: {tag()}\n", encoding="utf-8")
    names = [t.name for t in tables] + extra_tables
    model_tmdl = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tdiscourageImplicitMeasures", ""]
    model_tmdl += [f"ref table {q(n)}" for n in names] + [""] + [f"ref role {q(r)}" for r in roles] + ["", "ref culture en-US", ""]
    (d / "definition" / "model.tmdl").write_text("\n".join(model_tmdl), encoding="utf-8")
    for t in tables:
        (d / "definition" / "tables" / f"{t.name}.tmdl").write_text(t.tmdl(), encoding="utf-8")
    for r, perms in roles.items():
        body = [f"role {q(r)}", "\tmodelPermission: read", ""] + [f"\ttablePermission {q(tb)} = {expr}" for tb, expr in perms] + [""]
        (d / "definition" / "roles" / f"{r}.tmdl").write_text("\n".join(body), encoding="utf-8")
    rl = []
    for a, b in rels:
        ta, ca = a.split("|")
        tb, cb = b.split("|")
        rl += [f"relationship {tag()}", f"\tfromColumn: {q(ta)}.{q(ca)}", f"\ttoColumn: {q(tb)}.{q(cb)}", ""]
    (d / "definition" / "relationships.tmdl").write_text("\n".join(rl), encoding="utf-8")
    return d


def field_parameter(d: Path, name: str, items: list[tuple[str, str, str]]):
    rows = ",\n".join(f'\t\t\t\t    ("{lbl}", NAMEOF({q(t)}[{m}]), {i})' for i, (lbl, t, m) in enumerate(items))
    text = f"""/// Field parameter (synthetic)
table {q(name)}
\tlineageTag: {tag()}

\tcolumn {q(name)}
\t\tdataType: string
\t\tlineageTag: {tag()}
\t\tsummarizeBy: none
\t\tsourceColumn: [Value1]
\t\tsortByColumn: {q(name + ' Order')}

\t\trelatedColumnDetails
\t\t\tgroupByColumn: {q(name + ' Fields')}

\tcolumn {q(name + ' Fields')}
\t\tdataType: string
\t\tisHidden
\t\tlineageTag: {tag()}
\t\tsummarizeBy: none
\t\tsourceColumn: [Value2]

\t\textendedProperty ParameterMetadata =
\t\t\t\t{{
\t\t\t\t  "version": 3,
\t\t\t\t  "kind": 2
\t\t\t\t}}

\tcolumn {q(name + ' Order')}
\t\tdataType: int64
\t\tisHidden
\t\tlineageTag: {tag()}
\t\tsummarizeBy: sum
\t\tsourceColumn: [Value3]

\tpartition {q(name)} = calculated
\t\tmode: import
\t\tsource =
\t\t\t\t{{
{rows}
\t\t\t\t}}
"""
    (d / "definition" / "tables" / f"{name}.tmdl").write_text(text, encoding="utf-8")


def calc_group(d: Path, name: str, date_ref: str):
    text = f"""table {q(name)}
\tlineageTag: {tag()}

\tcalculationGroup
\t\tprecedence: 10

\t\tcalculationItem Current = SELECTEDMEASURE()

\t\tcalculationItem MTD = CALCULATE ( SELECTEDMEASURE(), DATESMTD ( {date_ref} ) )

\t\tcalculationItem YTD = CALCULATE ( SELECTEDMEASURE(), DATESYTD ( {date_ref} ) )

\t\tcalculationItem PY = CALCULATE ( SELECTEDMEASURE(), SAMEPERIODLASTYEAR ( {date_ref} ) )

\tcolumn {q(name + ' Item')}
\t\tdataType: string
\t\tlineageTag: {tag()}
\t\tsummarizeBy: none
\t\tsourceColumn: Name
\t\tsortByColumn: Ordinal

\tcolumn Ordinal
\t\tdataType: int64
\t\tisHidden
\t\tlineageTag: {tag()}
\t\tsummarizeBy: sum
\t\tsourceColumn: Ordinal
"""
    (d / "definition" / "tables" / f"{name}.tmdl").write_text(text, encoding="utf-8")


def gold(cols: dict[str, list[str]], m: str) -> tuple[str, list[str]]:
    r = rel("GOLD", m)
    return r, cols[r]


def view(cols: dict[str, list[str]], v: str) -> tuple[str, list[str]]:
    r = rel("REPORTING", v)
    return r, cols[r]


def build_models(pbi: Path, cols: dict[str, list[str]]) -> dict[str, dict]:
    """Returns per model: {table: {'measures': [...], 'columns': [...]}} for report generation."""
    out: dict[str, dict] = {}

    def T(name, src, desc=""):
        r, c = src
        return Table(name, r, c, desc)

    # ---------------------------------------------------------------- Commercial
    sales = T("Sales", gold(cols, "fct_sales_lines"), "Sales lines from HELIOS.GOLD.FCT_SALES_LINES")
    dref = "'Date'[Date Day]"
    nr = sales.m("Net Revenue", "SUM(Sales[Net Revenue])", "\\$#,0", "Revenue")
    gr = sales.m("Gross Revenue", "SUM(Sales[Gross Revenue])", "\\$#,0", "Revenue")
    sales.m("Total Cost", "SUM(Sales[Cost Amount])", "\\$#,0", "Cost")
    mg = sales.m("Margin", "[Net Revenue] - [Total Cost]", "\\$#,0", "Margin")
    sales.m("Margin %", "DIVIDE([Margin], [Net Revenue])", "0.0%", "Margin")
    sales.m("Discount Value", "SUM(Sales[Discount Amount])", "\\$#,0", "Revenue")
    sales.m("Discount %", "DIVIDE([Discount Value], [Gross Revenue])", "0.0%", "Revenue")
    sales.m("Units", "SUM(Sales[Quantity])", "#,0", "Volume")
    sales.m("Order Count", "DISTINCTCOUNT(Sales[Order ID])", "#,0", "Volume")
    sales.m("Avg Order Value", "DIVIDE([Net Revenue], [Order Count])", "\\$#,0.00", "Volume")
    sales.m("Avg Selling Price", "DIVIDE([Net Revenue], [Units])", "\\$#,0.00", "Volume")
    sales.m("Promo Revenue", "CALCULATE([Net Revenue], Sales[Is Promo] = TRUE())", "\\$#,0", "Revenue")
    sales.m("Promo Share", "DIVIDE([Promo Revenue], [Net Revenue])", "0.0%", "Revenue")
    sales.m("Premium Revenue", "CALCULATE([Net Revenue], 'Product'[Price Band] = \"Premium\")", "\\$#,0", "Revenue")
    sales.m("Tax Collected", "SUM(Sales[Tax Amount])", "\\$#,0", "Cost")
    time_intel(sales, nr, dref)
    time_intel(sales, mg, dref)
    sales.m("Revenue Target", "[Net Revenue PY] * 1.08", "\\$#,0", "Targets")
    sales.m("Revenue vs Target", "DIVIDE([Net Revenue], [Revenue Target]) - 1", "0.0%", "Targets")
    sales.m("Target Status", 'IF([Revenue vs Target] >= 0, "On track", "Behind")', "", "Targets")
    sales.m("Target Colour", 'IF([Revenue vs Target] >= 0, "#16A34A", "#DC2626")', "", "Formatting")
    sales.calc_cols.append(("Margin Line", "Sales[Net Revenue] - Sales[Cost Amount]", "decimal"))
    orders = T("Orders", gold(cols, "fct_orders"), "Order headers")
    orders.m("Orders", "COUNTROWS(Orders)", "#,0")
    orders.m("Lines per Order", "DIVIDE(SUM(Orders[Line Count]), [Orders])", "0.0")
    orders.m("Order Margin", "SUM(Orders[Order Margin])", "\\$#,0")
    cust = T("Customer", gold(cols, "dim_customer"))
    cust.m("Customers", "DISTINCTCOUNT(Customer[Customer Key])", "#,0")
    cust.m("Gold Customers", 'CALCULATE([Customers], Customer[Value Tier] = "Gold")', "#,0")
    cust.m("Gold Share", "DIVIDE([Gold Customers], [Customers])", "0.0%")
    prod = T("Product", gold(cols, "dim_product"))
    prod.m("Active Products", "COUNTROWS(Product)", "#,0")
    store = T("Store", gold(cols, "dim_store"))
    store.m("Stores", "COUNTROWS(Store)", "#,0")
    store.m("Revenue per Store", "DIVIDE([Net Revenue], [Stores])", "\\$#,0")
    date = T("Date", gold(cols, "dim_date"))
    chan = T("Channel", gold(cols, "dim_channel"))
    ltv = T("Customer LTV", gold(cols, "fct_customer_ltv"))
    ltv.m("Avg LTV", "AVERAGE('Customer LTV'[Lifetime Revenue])", "\\$#,0")
    ltv.m("Avg Lifetime Margin", "AVERAGE('Customer LTV'[Lifetime Margin])", "\\$#,0")
    ltv.m("Churn Risk Customers", "CALCULATE(COUNTROWS('Customer LTV'), 'Customer LTV'[Days Since Last Order] > 180)", "#,0")
    ltv.m("Churn Risk %", "DIVIDE([Churn Risk Customers], [Customers])", "0.0%")
    web = T("Web Sessions", gold(cols, "fct_web_sessions"))
    web.m("Sessions", "COUNTROWS('Web Sessions')", "#,0")
    web.m("Conversions", "SUM('Web Sessions'[Conversions])", "#,0")
    web.m("Conversion Rate", "DIVIDE([Conversions], [Sessions])", "0.00%")
    web.m("Pages per Session", "DIVIDE(SUM('Web Sessions'[Page Views]), [Sessions])", "0.0")
    camp = T("Campaign ROI", view(cols, "VW_CAMPAIGN_ROI"), "Campaign ROI view")
    camp.m("Campaign Spend", "SUM('Campaign ROI'[Campaign Spend])", "\\$#,0")
    camp.m("Attributed Revenue", "SUM('Campaign ROI'[Attributed Revenue])", "\\$#,0")
    camp.m("ROAS", "DIVIDE([Attributed Revenue], [Campaign Spend])", "0.00x")
    camp.m("Cost per Conversion", "DIVIDE([Campaign Spend], [Conversions])", "\\$#,0.00")
    kpi = T("Store KPI", view(cols, "VW_SALES_KPI"), "Daily KPI view")
    kpi.m("KPI Revenue", "SUM('Store KPI'[Net Revenue])", "\\$#,0")
    kpi.m("KPI Margin %", "DIVIDE(SUM('Store KPI'[Margin Amount]), [KPI Revenue])", "0.0%")
    league = Table("Store League", *view(cols, "VW_STORE_LEAGUE"), "Store ranking via native SQL", native=True)
    league.m("Best Rank", "MIN('Store League'[Region Rank])", "0")
    ctables = [sales, orders, cust, prod, store, date, chan, ltv, web, camp, kpi, league]
    d = write_model(pbi, "CommercialAnalytics", ctables,
                    {"Regional Manager": [("Store", "'Store'[Manager Email] = USERPRINCIPALNAME()")],
                     "EMEA Sales": [("Store", "Store[Sales Region] = \"EMEA\""), ("Customer", "Customer[Country Code] IN {\"GB\", \"DE\", \"FR\"}")]},
                    ["KPI Selector", "Time Calc"],
                    [("Sales|Customer Key", "Customer|Customer Key"), ("Sales|Product Key", "Product|Product Key"),
                     ("Sales|Store Key", "Store|Store Key"), ("Sales|Order Date", "Date|Date Day"), ("Sales|Channel Key", "Channel|Channel Key")])
    field_parameter(d, "KPI Selector", [("Net Revenue", "Sales", "Net Revenue"), ("Margin", "Sales", "Margin"), ("Margin %", "Sales", "Margin %"),
                                        ("Orders", "Sales", "Order Count"), ("AOV", "Sales", "Avg Order Value"), ("Conversion", "Web Sessions", "Conversion Rate")])
    calc_group(d, "Time Calc", dref)
    out["CommercialAnalytics"] = {t.name: {"measures": [m[0] for m in t.measures], "columns": [p for _, p in t.cols if not p.endswith("Key")]} for t in ctables}
    out["CommercialAnalytics"]["KPI Selector"] = {"measures": [], "columns": ["KPI Selector"]}
    out["CommercialAnalytics"]["Time Calc"] = {"measures": [], "columns": ["Time Calc Item"]}

    # ---------------------------------------------------------------- Supply chain
    inv = T("Inventory", gold(cols, "fct_inventory_snapshot"))
    sref = "'Calendar'[Date Day]"
    inv.m("On Hand Units", "SUM(Inventory[On Hand Qty])", "#,0", "Stock")
    inv.m("On Order Units", "SUM(Inventory[On Order Qty])", "#,0", "Stock")
    inv.m("Stock Value", "SUM(Inventory[Stock Value])", "\\$#,0", "Stock")
    inv.m("Stock Value PY", f"CALCULATE([Stock Value], SAMEPERIODLASTYEAR({sref}))", "\\$#,0", "Stock")
    inv.m("Stock Value Change %", "DIVIDE([Stock Value] - [Stock Value PY], [Stock Value PY])", "0.0%", "Stock")
    inv.m("Below Safety Lines", "SUM(Inventory[Is Below Safety])", "#,0", "Risk")
    inv.m("Stockout Risk %", "DIVIDE([Below Safety Lines], COUNTROWS(Inventory))", "0.0%", "Risk")
    inv.m("Stock Risk Flag", 'IF([Stockout Risk %] > 0.1, "At risk", "Healthy")', "", "Risk")
    po = T("Purchase Orders", gold(cols, "fct_purchase_orders"))
    po.m("PO Spend", "SUM('Purchase Orders'[PO Cost])", "\\$#,0", "Spend")
    po.m("Ordered Units", "SUM('Purchase Orders'[Ordered Qty])", "#,0", "Volume")
    po.m("Received Units", "SUM('Purchase Orders'[Received Qty])", "#,0", "Volume")
    po.m("Fill Rate", "DIVIDE([Received Units], [Ordered Units])", "0.0%", "Service")
    po.m("Avg Lead Days", "AVERAGE('Purchase Orders'[Actual Lead Days])", "0.0", "Service")
    po.m("Late POs", "CALCULATE(COUNTROWS('Purchase Orders'), 'Purchase Orders'[Days Late] > 0)", "#,0", "Service")
    po.m("On Time %", "1 - DIVIDE([Late POs], COUNTROWS('Purchase Orders'))", "0.0%", "Service")
    po.m("OTIF %", "[On Time %] * [Fill Rate]", "0.0%", "Service")
    po.m("OTIF Status", 'IF([OTIF %] >= 0.95, "Good", IF([OTIF %] >= 0.85, "Watch", "Poor"))', "", "Service")
    po.m("PO Spend PY", f"CALCULATE([PO Spend], SAMEPERIODLASTYEAR({sref}))", "\\$#,0", "Spend")
    po.m("PO Spend YoY %", "DIVIDE([PO Spend] - [PO Spend PY], [PO Spend PY])", "0.0%", "Spend")
    po.m("Inventory Turns", "DIVIDE([PO Spend], [Stock Value])", "0.0", "Stock")
    sup = T("Supplier", gold(cols, "dim_supplier"))
    sup.m("Suppliers", "COUNTROWS(Supplier)", "#,0")
    sup.m("Avg Supplier Rating", "AVERAGE(Supplier[Supplier Rating])", "0.0")
    ssc = T("Supplier Scorecard", view(cols, "VW_SUPPLIER_SCORECARD"))
    ssc.m("Scorecard Fill Rate", "AVERAGE('Supplier Scorecard'[Avg Fill Rate])", "0.0%")
    ssc.m("Scorecard Days Late", "AVERAGE('Supplier Scorecard'[Avg Days Late])", "0.0")
    ih = T("Inventory Health", view(cols, "VW_INVENTORY_HEALTH"))
    ih.m("Avg Cover Ratio", "AVERAGE('Inventory Health'[Cover Ratio])", "0.00")
    ih.m("Cover Status", 'IF([Avg Cover Ratio] < 1, "Under", "OK")', "")
    sprod = T("Product", gold(cols, "dim_product"))
    sstore = T("Store", gold(cols, "dim_store"))
    scal = T("Calendar", gold(cols, "dim_date"))
    ret = T("Returns", gold(cols, "fct_returns"))
    ret.m("Returned Units", "SUM(Returns[Returned Units])", "#,0")
    ret.m("Refund Value", "SUM(Returns[Refund Amount])", "\\$#,0")
    ret.m("Return Rate", "DIVIDE([Returned Units], [On Hand Units])", "0.0%")
    stables = [inv, po, sup, ssc, ih, sprod, sstore, scal, ret]
    write_model(pbi, "SupplyChain", stables, {"Store Operations": [("Store", "Store[Sales Region] = \"AMER\"")]}, [],
                [("Inventory|Product Key", "Product|Product Key"), ("Inventory|Store Key", "Store|Store Key"),
                 ("Purchase Orders|Supplier Key", "Supplier|Supplier Key"), ("Inventory|Snapshot Date", "Calendar|Date Day")])
    out["SupplyChain"] = {t.name: {"measures": [m[0] for m in t.measures], "columns": [p for _, p in t.cols if not p.endswith("Key")]} for t in stables}

    # ---------------------------------------------------------------- Finance
    gl = T("GL", gold(cols, "fct_gl"), "General ledger in USD")
    fref = "'Fiscal Date'[Date Day]"
    gl.m("Actuals", "SUM(GL[Amount USD])", "\\$#,0", "Actuals")
    gl.m("Revenue Actuals", 'CALCULATE([Actuals], Account[P&L Line] = "Revenue")', "\\$#,0", "Actuals")
    gl.m("COGS Actuals", 'CALCULATE([Actuals], Account[P&L Line] = "COGS")', "\\$#,0", "Actuals")
    gl.m("Opex Actuals", 'CALCULATE([Actuals], Account[Account Group] = "Opex")', "\\$#,0", "Actuals")
    gl.m("Gross Profit", "[Revenue Actuals] - [COGS Actuals]", "\\$#,0", "Profit")
    gl.m("Gross Profit %", "DIVIDE([Gross Profit], [Revenue Actuals])", "0.0%", "Profit")
    gl.m("EBITDA", "[Gross Profit] - [Opex Actuals]", "\\$#,0", "Profit")
    gl.m("EBITDA %", "DIVIDE([EBITDA], [Revenue Actuals])", "0.0%", "Profit")
    gl.m("Actuals PY", f"CALCULATE([Actuals], SAMEPERIODLASTYEAR({fref}))", "\\$#,0", "Time Intelligence")
    gl.m("Actuals YoY %", "DIVIDE([Actuals] - [Actuals PY], [Actuals PY])", "0.0%", "Time Intelligence")
    gl.m("Actuals YTD", f"TOTALYTD([Actuals], {fref})", "\\$#,0", "Time Intelligence")
    gl.m("EBITDA YTD", f"TOTALYTD([EBITDA], {fref})", "\\$#,0", "Time Intelligence")
    gl.m("EBITDA PY", f"CALCULATE([EBITDA], SAMEPERIODLASTYEAR({fref}))", "\\$#,0", "Time Intelligence")
    gl.m("EBITDA YoY %", "DIVIDE([EBITDA] - [EBITDA PY], [EBITDA PY])", "0.0%", "Time Intelligence")
    bud = T("Budget", gold(cols, "fct_budget"))
    bud.m("Budget", "SUM(Budget[Budget Amount])", "\\$#,0", "Budget")
    bud.m("Variance", "[Actuals] - [Budget]", "\\$#,0", "Budget")
    bud.m("Variance %", "DIVIDE([Variance], [Budget])", "0.0%", "Budget")
    bud.m("Budget YTD", f"TOTALYTD([Budget], {fref})", "\\$#,0", "Budget")
    bud.m("Variance YTD", "[Actuals YTD] - [Budget YTD]", "\\$#,0", "Budget")
    bud.m("Variance Flag", 'IF([Variance %] > 0.05, "Over", IF([Variance %] < -0.05, "Under", "On budget"))', "", "Budget")
    bud.m("Variance Colour", 'SWITCH([Variance Flag], "Over", "#DC2626", "Under", "#2563EB", "#16A34A")', "", "Formatting")
    acc = T("Account", gold(cols, "dim_account"))
    cc = T("Cost Center", gold(cols, "dim_cost_center"))
    cc.m("Cost Centers", "COUNTROWS('Cost Center')", "#,0")
    fdate = T("Fiscal Date", gold(cols, "dim_date"))
    pnl = T("PnL", view(cols, "VW_PNL"), "P&L view (non-dbt, REPORTING schema)")
    pnl.m("PnL Actual", "SUM(PnL[Actual Amount])", "\\$#,0")
    pnl.m("PnL Actual PY", f"CALCULATE([PnL Actual], SAMEPERIODLASTYEAR({fref}))", "\\$#,0")
    pnl.m("PnL Growth %", "DIVIDE([PnL Actual] - [PnL Actual PY], [PnL Actual PY])", "0.0%")
    mb = T("Margin Bridge", gold(cols, "fct_margin_bridge"))
    mb.m("Bridge Gross", "SUM('Margin Bridge'[Gross Revenue])", "\\$#,0")
    mb.m("Bridge Discounts", "-SUM('Margin Bridge'[Discount Amount])", "\\$#,0")
    mb.m("Bridge Net", "SUM('Margin Bridge'[Net Revenue])", "\\$#,0")
    mb.m("Bridge Cost", "-SUM('Margin Bridge'[Cost Amount])", "\\$#,0")
    mb.m("Bridge Margin", "SUM('Margin Bridge'[Margin Amount])", "\\$#,0")
    mb.m("Bridge Margin %", "DIVIDE([Bridge Margin], [Bridge Net])", "0.0%")
    ftables = [gl, bud, acc, cc, fdate, pnl, mb]
    write_model(pbi, "FinanceInsights", ftables, {"Cost Center Owner": [("Cost Center", "'Cost Center'[Owner Email] = USERPRINCIPALNAME()")]}, [],
                [("GL|Account Key", "Account|Account Key"), ("GL|Cost Center Key", "Cost Center|Cost Center Key"), ("GL|Posting Date", "Fiscal Date|Date Day")])
    out["FinanceInsights"] = {t.name: {"measures": [m[0] for m in t.measures], "columns": [p for _, p in t.cols if not p.endswith("Key")]} for t in ftables}
    return out


VTYPES = [("card", ["Values"]), ("kpi", ["Indicator"]), ("lineChart", ["Category", "Y"]), ("clusteredColumnChart", ["Category", "Y"]),
          ("clusteredBarChart", ["Category", "Y"]), ("tableEx", ["Values"]), ("pivotTable", ["Rows", "Values"]), ("donutChart", ["Category", "Y"]),
          ("slicer", ["Values"]), ("waterfallChart", ["Category", "Y"]), ("multiRowCard", ["Values"]), ("scatterChart", ["X", "Y"])]

REPORTS = {
    "CommercialAnalytics": {
        "Sales Executive": ["Overview", "Regions", "Channels", "Targets", "Trends"],
        "Customer 360": ["Customer Overview", "Lifetime Value", "Segments", "Churn Watch"],
        "Digital Marketing": ["Traffic", "Campaigns", "Conversion"],
    },
    "SupplyChain": {
        "Inventory Control": ["Stock Position", "Stockout Risk", "Returns"],
        "Supplier Performance": ["OTIF", "Lead Times", "Spend"],
    },
    "FinanceInsights": {
        "P&L Review": ["P&L Summary", "Margin Bridge", "Cost Centres"],
        "Budget vs Actual": ["Variance", "YTD Tracking"],
    },
}

FOCUS = {  # tables visuals should draw from per report (first = primary)
    "Sales Executive": ["Sales", "Store", "Date", "Channel", "Store KPI", "Store League"],
    "Customer 360": ["Customer", "Customer LTV", "Sales", "Orders"],
    "Digital Marketing": ["Web Sessions", "Campaign ROI", "Sales", "Customer"],
    "Inventory Control": ["Inventory", "Inventory Health", "Returns", "Product", "Store"],
    "Supplier Performance": ["Purchase Orders", "Supplier", "Supplier Scorecard", "Product"],
    "P&L Review": ["GL", "PnL", "Margin Bridge", "Account", "Cost Center"],
    "Budget vs Actual": ["Budget", "GL", "Cost Center", "Account", "Fiscal Date"],
}


def build_reports(pbi: Path, models: dict[str, dict]) -> int:
    n_vis = 0
    for mname, reps in REPORTS.items():
        md = models[mname]
        for rname, pages in reps.items():
            root = pbi / f"{rname.replace('&', 'n')}.Report"
            if root.exists():
                shutil.rmtree(root)
            write(root / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{mname}.SemanticModel"}}})
            d = root / "definition"
            write(d / "version.json", {"version": "2.0.0"})
            write(d / "report.json", {"themeCollection": {"baseTheme": {"name": "CY24SU10", "type": "SharedResources"}}, "displayName": rname})
            tables = [t for t in FOCUS[rname] if t in md]
            page_ids = []
            for pi, pname in enumerate(pages):
                pid = f"{abs(hash((rname, pname))) % 16**16:016x}"
                pid = f"{RNG.getrandbits(64):016x}"
                page_ids.append(pid)
                page = {"name": pid, "displayName": pname, "displayOption": "FitToPage", "height": 720, "width": 1280}
                if pi % 2 == 0:
                    dim = next((t for t in tables if md[t]["columns"] and not md[t]["measures"]), tables[-1])
                    page["filterConfig"] = {"filters": [cat_filter(f"pf{pi}", col(dim, RNG.choice(md[dim]["columns"])))]}
                write(d / "pages" / pid / "page.json", page)
                nv = RNG.randint(5, 9)
                for vi in range(nv):
                    vtype, roles = RNG.choice(VTYPES)
                    prim = tables[0] if RNG.random() < 0.6 else RNG.choice(tables)
                    measures = [(prim, m) for m in md[prim]["measures"]] or [(t, m) for t in tables for m in md[t]["measures"]]
                    dims = [(t, c) for t in tables for c in md[t]["columns"]]
                    rmap = {}
                    for role in roles:
                        if role in ("Category", "Rows", "X") or vtype == "slicer":
                            t, c = RNG.choice(dims)
                            rmap[role] = [col(t, c)]
                        elif vtype in ("tableEx", "multiRowCard"):
                            picks = RNG.sample(measures, min(len(measures), RNG.randint(2, 4)))
                            t, c = RNG.choice(dims)
                            rmap[role] = [col(t, c)] + [meas(t2, m) for t2, m in picks]
                        else:
                            t, m = RNG.choice(measures)
                            rmap[role] = [meas(t, m)]
                    title = f"{pname} {vi + 1}"
                    first = next(iter(rmap.values()))[0]
                    k = next(iter(first))
                    title = first[k]["Property"] + (" by " + next(iter(rmap[roles[0]][0].values()))["Property"] if len(roles) > 1 and roles[0] in ("Category", "Rows") else "")
                    if len(roles) > 1:
                        y = rmap[roles[1]][0]
                        title = next(iter(y.values()))["Property"] + " by " + next(iter(rmap[roles[0]][0].values()))["Property"]
                    vid = f"{RNG.getrandbits(72):018x}"
                    v = visual(vid, vtype, rmap, 20 + (vi % 3) * 420, 20 + (vi // 3) * 230, 400, 210, title, z=vi * 1000)
                    if vtype in ("card", "kpi") and mname == "CommercialAnalytics" and RNG.random() < 0.5:
                        v["visual"]["objects"] = {"labels": [{"properties": {"color": {"solid": {"color": {"expr": meas("Sales", "Target Colour")}}}}}]}
                    if RNG.random() < 0.15 and dims:
                        t, c = RNG.choice(dims)
                        v["filterConfig"] = {"filters": [cat_filter(f"vf{vi}", col(t, c))]}
                    write(d / "pages" / pid / "visuals" / vid / "visual.json", v)
                    n_vis += 1
            write(d / "pages" / "pages.json", {"pageOrder": page_ids, "activePageName": page_ids[0]})
    return n_vis


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "dbt").mkdir(parents=True)
    cols = dbt_project(OUT / "dbt")
    pbi = OUT / "powerbi"
    models = build_models(pbi, cols)
    nv = build_reports(pbi, models)
    sm = sorted(p.name for p in pbi.glob("*.SemanticModel"))
    rp = sorted(p.name for p in pbi.glob("*.Report"))
    cfg = ["# LARGE synthetic sample bundled with LineageLens (fictional \"Helios Retail Group\").",
           "# Used to test readability / performance at scale. Generated by tools/make_large_sample.py.",
           "project_name: Helios Retail Group (large sample)", "", "dbt:", "  - project_dir: dbt", "", "snowflake:",
           "  view_dirs: [snowflake_views]", f"  default_database: {DB}", "  default_schema: REPORTING", "", "powerbi:",
           "  semantic_models: [" + ", ".join(f"powerbi/{s}" for s in sm) + "]",
           "  reports: [" + ", ".join(f"powerbi/{r}" for r in rp) + "]", "  report_model_map: {}", "",
           "naming:", "  case_insensitive: true", "  enable_fuzzy: true", "  fuzzy_threshold: 90", ""]
    (OUT / "lineagelens.sample.yml").write_text("\n".join(cfg), encoding="utf-8")
    n_cols = sum(len(v) for k, v in cols.items())
    n_meas = sum(len(t["measures"]) for m in models.values() for t in m.values())
    print(f"wrote {OUT}: {len(MODELS)} dbt models, {n_cols} model/view columns, {n_meas} measures, {len(rp)} reports, {nv} visuals")


if __name__ == "__main__":
    main()
