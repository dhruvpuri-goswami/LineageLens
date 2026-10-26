import io
import json
import zipfile

from lineagelens.extractors.dax import references, strip_comments
from lineagelens.extractors.dbt import load_dbt
from lineagelens.extractors.mquery import parse_m
from lineagelens.extractors.pbimodel import load_semantic_model, parse_tmdl
from lineagelens.extractors.reports import load_pbix, load_report
from lineagelens.extractors.snowflake import load_view_files, split_statements
from lineagelens.naming import NamingRules, best_match, normalise


# ---------------------------------------------------------------- DAX
def test_dax_references():
    r = references("""
        VAR x = CALCULATE ( SUM ( 'Sales Fact'[Net Amount] ), Store[Region] = "EMEA" ) -- comment [Ignored]
        RETURN DIVIDE ( x, [Total Orders] ) /* [AlsoIgnored] */
    """)
    assert ("Sales Fact", "Net Amount") in r.columns
    assert ("Store", "Region") in r.columns
    assert "Total Orders" in r.bare
    assert "Ignored" not in r.bare and "AlsoIgnored" not in r.bare
    assert "x" in [v.lower() for v in r.variables]


def test_dax_strings_are_not_refs():
    r = references('IF ( 1 = 1, "[NotAColumn]", Sales[Qty] )')
    assert r.columns == [("Sales", "Qty")]
    assert "NotAColumn" not in r.bare
    assert "--" not in strip_comments("1 // c\n+ 2")


# ---------------------------------------------------------------- M
def test_m_snowflake_navigation_with_renames():
    m = '''let
        Source = Snowflake.Databases("example.snowflakecomputing.com", "WH"),
        Db = Source{[Name="ANALYTICS",Kind="Database"]}[Data],
        Sc = Db{[Name="REPORTING",Kind="Schema"]}[Data],
        V = Sc{[Name="VW_SALES_SUMMARY",Kind="View"]}[Data],
        R = Table.RenameColumns(V, {{"TOTAL_NET_AMOUNT", "Total Net Amount"}})
    in R'''
    s = parse_m(m)
    assert s.connector == "snowflake"
    assert s.relation == "ANALYTICS.REPORTING.VW_SALES_SUMMARY"
    assert ("TOTAL_NET_AMOUNT", "Total Net Amount") in s.renames


def test_m_native_query_and_parameters():
    m = '''let
        Source = Value.NativeQuery(Snowflake.Databases(Server, Wh){[Name=DbName]}[Data],
                 "select ORDER_ID, NET_AMOUNT from GOLD.FCT_SALES", null, [EnableFolding=true])
    in Source'''
    s = parse_m(m, {"DbName": "ANALYTICS"})
    assert s.connector == "native_query"
    assert "FCT_SALES" in s.native_sql.upper()


# ---------------------------------------------------------------- TMDL / semantic model
def test_tmdl_parser_basic():
    nodes = parse_tmdl("""table Sales
\tmeasure 'Net Sales' = SUM(Sales[Net Amount])
\t\tformatString: #,0
\tcolumn 'Net Amount'
\t\tdataType: decimal
\t\tsourceColumn: NET_AMOUNT
""")
    t = nodes[0]
    assert t.keyword == "table" and t.name == "Sales"
    kinds = {(c.keyword, c.name) for c in t.children}
    assert ("measure", "Net Sales") in kinds and ("column", "Net Amount") in kinds


def test_sample_semantic_model(samples):
    sm = load_semantic_model(samples / "powerbi" / "RetailSales.SemanticModel")
    assert sm.name == "RetailSales"
    assert sm.format.lower().startswith("tmdl")
    names = set(sm.tables)
    assert {"Sales", "Customer", "Store"} <= names
    assert "EMEA Only" in sm.roles
    assert any(t.calc_items for t in sm.tables.values()), "calculation group expected"
    assert sum(len(t.measures) for t in sm.tables.values()) >= 10


# ---------------------------------------------------------------- reports
def test_pbir_report(samples):
    rep = load_report(samples / "powerbi" / "RetailSales.Report")
    assert rep.format == "pbir"
    assert rep.model_ref == "RetailSales"
    assert len(rep.pages) >= 3
    vis = [v for p in rep.pages for v in p.visuals]
    assert any(v.name == "Net Sales" for v in vis)
    assert any(p.filters for p in rep.pages) or rep.filters


def test_legacy_report_json(samples):
    rep = load_report(samples / "powerbi" / "RegionalScorecard.Report")
    assert rep.format == "pbir-legacy"
    assert rep.pages and any(p.visuals for p in rep.pages)


def test_pbix_layout(tmp_path):
    layout = {"sections": [{"name": "s1", "displayName": "Overview", "ordinal": 0, "visualContainers": [
        {"config": json.dumps({"name": "v1", "singleVisual": {"visualType": "card", "projections": {"Values": [{"queryRef": "Sales.Net Sales"}]},
            "prototypeQuery": {"From": [{"Name": "s", "Entity": "Sales"}],
                               "Select": [{"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Net Sales"}, "Name": "Sales.Net Sales"}]}}})}]}]}
    p = tmp_path / "Mini.pbix"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Report/Layout", json.dumps(layout).encode("utf-16-le"))
    rep = load_pbix(p)
    assert rep.format == "pbix"
    v = rep.pages[0].visuals[0]
    assert v.visual_type == "card"
    assert any(f.entity == "Sales" and f.property == "Net Sales" and f.kind == "measure" for f in v.fields)


# ---------------------------------------------------------------- dbt + snowflake files
def test_dbt_manifest(samples):
    proj = load_dbt(samples / "dbt" / "target" / "manifest.json", samples / "dbt" / "target" / "catalog.json", samples / "dbt")
    names = {n.name for n in proj.nodes.values()} if isinstance(proj.nodes, dict) else {n.name for n in proj.nodes}
    assert {"fct_sales", "dim_customer", "stg_orders"} <= names


def test_snowflake_view_files(samples):
    assert len(split_statements("create view a as select 1; -- x;\ncreate view b as select ';'")) == 2
    objs = load_view_files([samples / "snowflake_views"], "ANALYTICS", "REPORTING")
    assert any(v.relation.endswith("VW_SALES_SUMMARY") for v in objs.views)


# ---------------------------------------------------------------- naming
def test_naming_conventions():
    rules = NamingRules(strip_prefixes=["DIM_", "FCT_"])
    assert normalise("Net Amount") == normalise("NET_AMOUNT")
    assert normalise("netAmount") == normalise("NET_AMOUNT")
    m = best_match("Customer Name", ["CUSTOMER_NAME", "CUSTOMER_ID"], rules)
    assert m and m.candidate == "CUSTOMER_NAME"
