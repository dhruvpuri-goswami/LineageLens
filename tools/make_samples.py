"""Generate the bundled SAMPLE dbt project artefacts (manifest.json / catalog.json).

Everything here is synthetic demo data for a fictional retailer ("Northwind Outfitters").
Run:  python tools/make_samples.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "lineagelens" / "samples" / "dbt"
PROJECT = "retail_analytics"
DB = "ANALYTICS"

SOURCES = {
    "orders": ("RAW", "Raw order headers from the e-commerce platform", {
        "ORDER_ID": ("NUMBER", "Order identifier"), "CUSTOMER_ID": ("NUMBER", "Customer identifier"),
        "STORE_ID": ("NUMBER", "Fulfilling store"), "ORDER_TS": ("TIMESTAMP_NTZ", "Order timestamp"),
        "STATUS": ("VARCHAR", "Order status code"), "_LOADED_AT": ("TIMESTAMP_NTZ", "Load audit timestamp")}),
    "order_items": ("RAW", "Order line items", {
        "ORDER_ITEM_ID": ("NUMBER", "Line identifier"), "ORDER_ID": ("NUMBER", "Order identifier"),
        "PRODUCT_ID": ("NUMBER", "Product identifier"), "QUANTITY": ("NUMBER", "Units ordered"),
        "UNIT_PRICE": ("NUMBER(12,2)", "Unit selling price"), "DISCOUNT_PCT": ("NUMBER(5,4)", "Discount fraction 0-1")}),
    "customers": ("RAW", "CRM customer master", {
        "CUSTOMER_ID": ("NUMBER", "Customer identifier"), "FIRST_NAME": ("VARCHAR", "First name"),
        "LAST_NAME": ("VARCHAR", "Last name"), "EMAIL": ("VARCHAR", "Email address"),
        "COUNTRY_CODE": ("VARCHAR", "ISO country"), "SEGMENT": ("VARCHAR", "Commercial segment"),
        "CREATED_AT": ("TIMESTAMP_NTZ", "Record created")}),
    "products": ("RAW", "Product catalogue", {
        "PRODUCT_ID": ("NUMBER", "Product identifier"), "PRODUCT_NAME": ("VARCHAR", "Product name"),
        "CATEGORY": ("VARCHAR", "Category"), "SUBCATEGORY": ("VARCHAR", "Sub-category"),
        "LIST_PRICE": ("NUMBER(12,2)", "List price"), "IS_ACTIVE": ("BOOLEAN", "Active flag")}),
    "stores": ("RAW", "Store master", {
        "STORE_ID": ("NUMBER", "Store identifier"), "STORE_NAME": ("VARCHAR", "Store name"),
        "REGION": ("VARCHAR", "Sales region"), "COUNTRY_CODE": ("VARCHAR", "ISO country"),
        "MANAGER_EMAIL": ("VARCHAR", "Store manager e-mail (used for RLS)")}),
}

SEED = ("country_codes", "SEEDS", "Country lookup seed", {
    "COUNTRY_CODE": ("VARCHAR", "ISO-2 code"), "COUNTRY_NAME": ("VARCHAR", "Country name"),
    "REGION_GROUP": ("VARCHAR", "Region group")})

# name -> (schema, materialized, description, raw_sql, column descriptions)
MODELS: dict[str, tuple] = {
    "stg_orders": ("STAGING", "view", "Cleaned order headers", """
select
    order_id,
    customer_id,
    store_id,
    order_ts::date as order_date,
    lower(status) as order_status
from {{ source('raw', 'orders') }}
where status <> 'TEST'
""", {"ORDER_DATE": "Order date (from ORDER_TS)", "ORDER_STATUS": "Lower-cased status"}),
    "stg_order_items": ("STAGING", "view", "Order lines with net amount", """
select
    *,
    quantity * unit_price * (1 - discount_pct) as net_amount
from {{ source('raw', 'order_items') }}
""", {"NET_AMOUNT": "Quantity x price after discount"}),
    "stg_customers": ("STAGING", "view", "Cleaned customers", """
select
    customer_id,
    first_name || ' ' || last_name as customer_name,
    email,
    country_code,
    segment as customer_segment,
    created_at
from {{ source('raw', 'customers') }}
""", {"CUSTOMER_NAME": "First + last name"}),
    "stg_products": ("STAGING", "view", "Cleaned products", """
select
    product_id,
    product_name,
    category as product_category,
    subcategory as product_subcategory,
    list_price,
    is_active
from {{ source('raw', 'products') }}
""", {}),
    "stg_stores": ("STAGING", "view", "Cleaned stores", """
select
    store_id,
    store_name,
    region as sales_region,
    country_code,
    manager_email
from {{ source('raw', 'stores') }}
""", {}),
    "int_order_lines": ("INTERMEDIATE", "ephemeral_view", "Order lines joined to headers", """
with items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select * from {{ ref('stg_orders') }}
)
select
    i.order_item_id,
    i.order_id,
    o.customer_id,
    o.store_id,
    i.product_id,
    o.order_date,
    o.order_status,
    i.quantity,
    i.unit_price,
    i.discount_pct,
    i.net_amount,
    case
        when i.discount_pct >= 0.20 then 'High'
        when i.discount_pct > 0 then 'Low'
        else 'None'
    end as discount_band
from items i
inner join orders o on i.order_id = o.order_id
""", {"DISCOUNT_BAND": "High (>=20%), Low, None"}),
    "dim_customer": ("GOLD", "table", "Customer dimension (gold)", """
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
""", {"CUSTOMER_KEY": "Surrogate key = CRM customer id", "CUSTOMER_TIER": "Tier derived from segment"}),
    "dim_product": ("GOLD", "table", "Product dimension (gold)", """
select
    product_id as product_key,
    product_name,
    product_category,
    product_subcategory,
    list_price,
    case when list_price >= 500 then 'Premium' else 'Standard' end as price_band
from {{ ref('stg_products') }}
where is_active
""", {"PRICE_BAND": "Premium when list price >= 500"}),
    "dim_store": ("GOLD", "table", "Store dimension (gold)", """
select
    store_id as store_key,
    store_name,
    sales_region,
    country_code,
    manager_email
from {{ ref('stg_stores') }}
""", {"MANAGER_EMAIL": "Used by Power BI RLS"}),
    "fct_sales": ("GOLD", "incremental", "Sales fact at order-line grain (gold)", """
select
    ol.order_item_id as sales_key,
    ol.order_id,
    ol.customer_id as customer_key,
    ol.product_id as product_key,
    ol.store_id as store_key,
    ol.order_date,
    ol.quantity,
    ol.net_amount,
    ol.quantity * p.list_price as gross_amount,
    ol.discount_band,
    ol.order_status
from {{ ref('int_order_lines') }} ol
left join {{ ref('stg_products') }} p on ol.product_id = p.product_id
where ol.order_status <> 'cancelled'
""", {"NET_AMOUNT": "Net sales amount after discount", "GROSS_AMOUNT": "Quantity x list price"}),
}

SNAPSHOT = ("snap_customers", "SNAPSHOTS", "SCD2 snapshot of customers", """
{% snapshot snap_customers %}
{{ config(unique_key='customer_id', strategy='timestamp', updated_at='created_at') }}
select * from {{ source('raw', 'customers') }}
{% endsnapshot %}
""")


def rel(schema: str, name: str) -> str:
    return f"{DB.lower()}.{schema.lower()}.{name}"


def uid_for_ref(name: str) -> str:
    if name == SEED[0]:
        return f"seed.{PROJECT}.{name}"
    return f"model.{PROJECT}.{name}"


def compile_sql(raw: str) -> tuple[str, list[str]]:
    deps: list[str] = []

    def src(m):
        s, t = m.group(1), m.group(2)
        deps.append(f"source.{PROJECT}.{s}.{t}")
        return rel(SOURCES[t][0], t)

    def ref(m):
        n = m.group(1)
        deps.append(uid_for_ref(n))
        if n == SEED[0]:
            return rel(SEED[1], n)
        return rel(MODELS[n][0], n)

    out = re.sub(r"\{\{\s*source\('(\w+)',\s*'(\w+)'\)\s*\}\}", src, raw)
    out = re.sub(r"\{\{\s*ref\('(\w+)'\)\s*\}\}", ref, out)
    out = re.sub(r"\{%.*?%\}\n?", "", out)
    out = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}\n?", "", out)
    return out.strip() + "\n", list(dict.fromkeys(deps))


def output_columns() -> dict[str, dict[str, str]]:
    """Expected Snowflake columns per model (what `dbt docs generate` would put in catalog.json)."""
    src_cols = {t: {c: ty for c, (ty, _) in v[2].items()} for t, v in SOURCES.items()}
    cols: dict[str, dict[str, str]] = {}
    so, oi, cu, pr, st = (src_cols[k] for k in ("orders", "order_items", "customers", "products", "stores"))
    cols["stg_orders"] = {"ORDER_ID": so["ORDER_ID"], "CUSTOMER_ID": "NUMBER", "STORE_ID": "NUMBER", "ORDER_DATE": "DATE", "ORDER_STATUS": "VARCHAR"}
    cols["stg_order_items"] = dict(oi, NET_AMOUNT="NUMBER(38,6)")
    cols["stg_customers"] = {"CUSTOMER_ID": "NUMBER", "CUSTOMER_NAME": "VARCHAR", "EMAIL": "VARCHAR", "COUNTRY_CODE": "VARCHAR", "CUSTOMER_SEGMENT": "VARCHAR", "CREATED_AT": "TIMESTAMP_NTZ"}
    cols["stg_products"] = {"PRODUCT_ID": "NUMBER", "PRODUCT_NAME": "VARCHAR", "PRODUCT_CATEGORY": "VARCHAR", "PRODUCT_SUBCATEGORY": "VARCHAR", "LIST_PRICE": "NUMBER(12,2)", "IS_ACTIVE": "BOOLEAN"}
    cols["stg_stores"] = {"STORE_ID": "NUMBER", "STORE_NAME": "VARCHAR", "SALES_REGION": "VARCHAR", "COUNTRY_CODE": "VARCHAR", "MANAGER_EMAIL": "VARCHAR"}
    cols["int_order_lines"] = {"ORDER_ITEM_ID": "NUMBER", "ORDER_ID": "NUMBER", "CUSTOMER_ID": "NUMBER", "STORE_ID": "NUMBER", "PRODUCT_ID": "NUMBER", "ORDER_DATE": "DATE", "ORDER_STATUS": "VARCHAR", "QUANTITY": "NUMBER", "UNIT_PRICE": "NUMBER(12,2)", "DISCOUNT_PCT": "NUMBER(5,4)", "NET_AMOUNT": "NUMBER(38,6)", "DISCOUNT_BAND": "VARCHAR"}
    cols["dim_customer"] = {"CUSTOMER_KEY": "NUMBER", "CUSTOMER_NAME": "VARCHAR", "CUSTOMER_EMAIL": "VARCHAR", "CUSTOMER_SEGMENT": "VARCHAR", "CUSTOMER_TIER": "VARCHAR", "COUNTRY_NAME": "VARCHAR", "CUSTOMER_SINCE": "TIMESTAMP_NTZ"}
    cols["dim_product"] = {"PRODUCT_KEY": "NUMBER", "PRODUCT_NAME": "VARCHAR", "PRODUCT_CATEGORY": "VARCHAR", "PRODUCT_SUBCATEGORY": "VARCHAR", "LIST_PRICE": "NUMBER(12,2)", "PRICE_BAND": "VARCHAR"}
    cols["dim_store"] = {"STORE_KEY": "NUMBER", "STORE_NAME": "VARCHAR", "SALES_REGION": "VARCHAR", "COUNTRY_CODE": "VARCHAR", "MANAGER_EMAIL": "VARCHAR"}
    cols["fct_sales"] = {"SALES_KEY": "NUMBER", "ORDER_ID": "NUMBER", "CUSTOMER_KEY": "NUMBER", "PRODUCT_KEY": "NUMBER", "STORE_KEY": "NUMBER", "ORDER_DATE": "DATE", "QUANTITY": "NUMBER", "NET_AMOUNT": "NUMBER(38,6)", "GROSS_AMOUNT": "NUMBER(38,2)", "DISCOUNT_BAND": "VARCHAR", "ORDER_STATUS": "VARCHAR"}
    return cols


def main() -> None:
    (ROOT / "target").mkdir(parents=True, exist_ok=True)
    (ROOT / "models" / "staging").mkdir(parents=True, exist_ok=True)
    (ROOT / "models" / "intermediate").mkdir(parents=True, exist_ok=True)
    (ROOT / "models" / "marts").mkdir(parents=True, exist_ok=True)
    (ROOT / "seeds").mkdir(parents=True, exist_ok=True)
    (ROOT / "snapshots").mkdir(parents=True, exist_ok=True)

    nodes: dict = {}
    sources: dict = {}
    catalog_nodes: dict = {}
    catalog_sources: dict = {}
    parent_map: dict = {}
    model_cols = output_columns()

    for t, (schema, desc, cols) in SOURCES.items():
        uid = f"source.{PROJECT}.raw.{t}"
        sources[uid] = {
            "resource_type": "source", "unique_id": uid, "package_name": PROJECT, "source_name": "raw",
            "name": t, "identifier": t.upper(), "database": DB, "schema": schema,
            "path": "models/staging/_sources.yml", "original_file_path": "models/staging/_sources.yml",
            "fqn": [PROJECT, "staging", "raw", t], "description": desc, "source_description": "Raw landing zone (Fivetran)",
            "loader": "fivetran", "relation_name": f"{DB}.{schema}.{t.upper()}",
            "columns": {c.lower(): {"name": c.lower(), "description": d, "data_type": ty, "meta": {}, "tags": []} for c, (ty, d) in cols.items()},
            "meta": {}, "tags": [],
        }
        catalog_sources[uid] = {
            "metadata": {"type": "BASE TABLE", "schema": schema, "name": t.upper(), "database": DB, "comment": None, "owner": "LOADER"},
            "columns": {c: {"type": ty, "index": i + 1, "name": c, "comment": None} for i, (c, (ty, _)) in enumerate(cols.items())},
            "stats": {}, "unique_id": uid,
        }
        parent_map[uid] = []

    # seed
    sname, sschema, sdesc, scols = SEED
    suid = f"seed.{PROJECT}.{sname}"
    nodes[suid] = {
        "resource_type": "seed", "unique_id": suid, "name": sname, "package_name": PROJECT, "alias": sname,
        "database": DB, "schema": sschema, "path": f"{sname}.csv", "original_file_path": f"seeds/{sname}.csv",
        "fqn": [PROJECT, sname], "config": {"materialized": "seed", "enabled": True}, "description": sdesc,
        "columns": {c.lower(): {"name": c.lower(), "description": d, "data_type": ty, "meta": {}, "tags": []} for c, (ty, d) in scols.items()},
        "depends_on": {"nodes": [], "macros": []}, "relation_name": f"{DB}.{sschema}.{sname.upper()}", "raw_code": "", "tags": [],
    }
    catalog_nodes[suid] = {"metadata": {"type": "BASE TABLE", "schema": sschema, "name": sname.upper(), "database": DB},
                           "columns": {c: {"type": ty, "index": i + 1, "name": c} for i, (c, (ty, _)) in enumerate(scols.items())}, "stats": {}, "unique_id": suid}
    (ROOT / "seeds" / f"{sname}.csv").write_text("country_code,country_name,region_group\nGB,United Kingdom,EMEA\nDE,Germany,EMEA\nUS,United States,AMER\nIN,India,APAC\n", encoding="utf-8")
    parent_map[suid] = []

    # models
    for name, (schema, mat, desc, raw, coldesc) in MODELS.items():
        uid = f"model.{PROJECT}.{name}"
        compiled, deps = compile_sql(raw)
        folder = "staging" if name.startswith("stg_") else "intermediate" if name.startswith("int_") else "marts"
        (ROOT / "models" / folder / f"{name}.sql").write_text(
            ("{{ config(materialized='%s') }}\n" % ("view" if mat == "ephemeral_view" else mat)) + raw.lstrip(), encoding="utf-8")
        materialized = "view" if mat == "ephemeral_view" else mat
        nodes[uid] = {
            "resource_type": "model", "unique_id": uid, "name": name, "package_name": PROJECT, "alias": name,
            "database": DB, "schema": schema, "path": f"{folder}/{name}.sql", "original_file_path": f"models/{folder}/{name}.sql",
            "fqn": [PROJECT, folder, name], "config": {"materialized": materialized, "enabled": True, "tags": [folder]},
            "description": desc, "tags": [folder],
            "columns": {c.lower(): {"name": c.lower(), "description": d, "data_type": None, "meta": {}, "tags": []} for c, d in coldesc.items()},
            "depends_on": {"nodes": deps, "macros": []}, "raw_code": raw.strip() + "\n", "compiled_code": compiled,
            "compiled": True, "relation_name": f"{DB}.{schema}.{name.upper()}", "language": "sql",
        }
        catalog_nodes[uid] = {
            "metadata": {"type": "VIEW" if materialized == "view" else "BASE TABLE", "schema": schema, "name": name.upper(), "database": DB, "owner": "TRANSFORMER"},
            "columns": {c: {"type": ty, "index": i + 1, "name": c, "comment": None} for i, (c, ty) in enumerate(model_cols[name].items())},
            "stats": {}, "unique_id": uid,
        }
        parent_map[uid] = deps

    # snapshot
    snm, sns, snd, snraw = SNAPSHOT
    snuid = f"snapshot.{PROJECT}.{snm}"
    compiled, deps = compile_sql(snraw)
    nodes[snuid] = {
        "resource_type": "snapshot", "unique_id": snuid, "name": snm, "package_name": PROJECT, "alias": snm,
        "database": DB, "schema": sns, "path": f"{snm}.sql", "original_file_path": f"snapshots/{snm}.sql",
        "fqn": [PROJECT, snm, snm], "config": {"materialized": "snapshot", "strategy": "timestamp", "unique_key": "customer_id"},
        "description": snd, "columns": {}, "depends_on": {"nodes": deps, "macros": []}, "raw_code": snraw.strip() + "\n",
        "compiled_code": compiled, "relation_name": f"{DB}.{sns}.{snm.upper()}", "tags": [],
    }
    cu = SOURCES["customers"][2]
    sncols = {c: ty for c, (ty, _) in cu.items()}
    sncols.update({"DBT_SCD_ID": "VARCHAR", "DBT_UPDATED_AT": "TIMESTAMP_NTZ", "DBT_VALID_FROM": "TIMESTAMP_NTZ", "DBT_VALID_TO": "TIMESTAMP_NTZ"})
    catalog_nodes[snuid] = {"metadata": {"type": "BASE TABLE", "schema": sns, "name": snm.upper(), "database": DB},
                            "columns": {c: {"type": ty, "index": i + 1, "name": c} for i, (c, ty) in enumerate(sncols.items())}, "stats": {}, "unique_id": snuid}
    (ROOT / "snapshots" / f"{snm}.sql").write_text(snraw.lstrip(), encoding="utf-8")
    parent_map[snuid] = deps

    child_map: dict = {k: [] for k in parent_map}
    for child, parents in parent_map.items():
        for p in parents:
            child_map.setdefault(p, []).append(child)

    meta = {"dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json", "dbt_version": "1.9.4",
            "generated_at": "2026-10-20T09:12:44.512Z", "invocation_id": "5d1c0f7e-sample", "env": {},
            "project_name": PROJECT, "project_id": "sample", "adapter_type": "snowflake", "send_anonymous_usage_stats": False}
    manifest = {"metadata": meta, "nodes": nodes, "sources": sources, "macros": {}, "docs": {}, "exposures": {},
                "metrics": {}, "groups": {}, "selectors": {}, "disabled": {}, "parent_map": parent_map, "child_map": child_map,
                "group_map": {}, "saved_queries": {}, "semantic_models": {}, "unit_tests": {}}
    catalog = {"metadata": {"dbt_schema_version": "https://schemas.getdbt.com/dbt/catalog/v1.json", "dbt_version": "1.9.4",
                            "generated_at": "2026-10-20T09:13:02.101Z", "invocation_id": "5d1c0f7e-sample", "env": {}},
               "nodes": catalog_nodes, "sources": catalog_sources, "errors": None}
    (ROOT / "target" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (ROOT / "target" / "catalog.json").write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    # dbt_project.yml + schema.yml for realism
    (ROOT / "dbt_project.yml").write_text(f"""name: {PROJECT}
version: '1.0.0'
profile: retail_analytics
model-paths: ["models"]
seed-paths: ["seeds"]
snapshot-paths: ["snapshots"]
models:
  {PROJECT}:
    staging:
      +schema: staging
      +materialized: view
    intermediate:
      +schema: intermediate
    marts:
      +schema: gold
""", encoding="utf-8")
    lines = ["version: 2", "", "models:"]
    for name, (schema, mat, desc, raw, coldesc) in MODELS.items():
        if not name.startswith(("dim_", "fct_")):
            continue
        lines += [f"  - name: {name}", f"    description: \"{desc}\"", "    columns:"]
        for c, d in coldesc.items():
            lines += [f"      - name: {c.lower()}", f"        description: \"{d}\""]
    (ROOT / "models" / "marts" / "schema.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    src_lines = ["version: 2", "", "sources:", "  - name: raw", f"    database: {DB.lower()}", "    schema: raw", "    tables:"]
    for t in SOURCES:
        src_lines.append(f"      - name: {t}")
    (ROOT / "models" / "staging" / "_sources.yml").write_text("\n".join(src_lines) + "\n", encoding="utf-8")
    print(f"wrote samples to {ROOT}")


if __name__ == "__main__":
    main()
