from lineagelens.sqllineage import lineage_for_sql, referenced_relations, view_name_and_columns

SCHEMA = {"ANALYTICS": {"GOLD": {
    "FCT_SALES": {"ORDER_ID": "NUMBER", "NET_AMOUNT": "NUMBER", "STORE_ID": "NUMBER", "ORDER_DATE": "DATE"},
    "DIM_STORE": {"STORE_ID": "NUMBER", "SALES_REGION": "VARCHAR"},
}}}


def test_passthrough_rename_and_derived():
    sql = """
    select f.order_id, f.net_amount as net_sales, s.sales_region as region,
           f.net_amount * 1.2 as gross_est, 'x' as lit
    from analytics.gold.fct_sales f join analytics.gold.dim_store s on f.store_id = s.store_id
    where f.order_date >= '2024-01-01'
    """
    q = lineage_for_sql(sql, SCHEMA, "ANALYTICS", "GOLD")
    assert q.column("ORDER_ID").transform == "passthrough"
    ns = q.column("NET_SALES")
    assert ns.transform == "renamed"
    assert [(s.relation, s.column) for s in ns.sources] == [("ANALYTICS.GOLD.FCT_SALES", "NET_AMOUNT")]
    assert q.column("GROSS_EST").transform == "derived"
    assert q.column("LIT").transform == "constant"
    filt = {(s.relation, s.column) for s in q.filter_sources}
    assert ("ANALYTICS.GOLD.FCT_SALES", "ORDER_DATE") in filt
    assert ("ANALYTICS.GOLD.DIM_STORE", "STORE_ID") in filt


def test_cte_and_star_expansion():
    sql = """
    with s as (select * from analytics.gold.dim_store)
    select store_id, upper(sales_region) as region_upper from s
    """
    q = lineage_for_sql(sql, SCHEMA, "ANALYTICS", "GOLD")
    r = q.column("REGION_UPPER")
    assert [(x.relation, x.column) for x in r.sources] == [("ANALYTICS.GOLD.DIM_STORE", "SALES_REGION")]


def test_create_view_with_column_list():
    sql = "create or replace view analytics.reporting.vw_x (a, b) as select order_id, net_amount from analytics.gold.fct_sales"
    name, cols, query, kind = view_name_and_columns(sql, "ANALYTICS", "GOLD")
    assert name == "ANALYTICS.REPORTING.VW_X"
    assert [c.upper() for c in cols] == ["A", "B"]
    assert kind == "VIEW" and "FCT_SALES" in query.upper()
    assert referenced_relations(sql, "ANALYTICS", "GOLD") == ["ANALYTICS.GOLD.FCT_SALES"]


def test_lateral_flatten_and_qualify():
    schema = {"DB": {"S": {"ORDERS": {"ID": "NUMBER", "TAGS": "VARIANT", "CUST": "NUMBER", "TS": "TIMESTAMP"}}}}
    q = lineage_for_sql("""select o.id, f.value::string as tag,
                                  row_number() over (partition by o.cust order by o.ts) rn
                           from db.s.orders o, lateral flatten(input => o.tags) f qualify rn = 1""", schema)
    assert [(s.relation, s.column) for s in q.column("TAG").sources] == [("DB.S.ORDERS", "TAGS")]
    assert {s.column for s in q.column("RN").sources} == {"CUST", "TS"}
    assert not q.warnings
