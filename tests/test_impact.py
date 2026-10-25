from conftest import NET_AMOUNT, NET_SALES_CARD

from lineagelens import analysis, store


def test_scan_sources_and_no_errors(scan):
    assert len(scan.graph) > 150
    assert len(scan.sources["semantic_models"]) == 1
    assert len(scan.sources["reports"]) == 2
    assert not [w for w in scan.warnings if w.get("level") == "error"]


def test_net_amount_impact(graph):
    res = analysis.impact(graph, [NET_AMOUNT], "drop")
    s = res["summary"]
    assert s["total"] == 28
    assert s["visuals"] == 12 and s["visuals_breaking"] == 12
    assert s["measures"] == 11
    assert s["reports"] == 2
    assert s["field_parameters"] == 1
    vis_ids = {v["id"] for r in res["reports"] for p in r["pages"] for v in p["visuals"]}
    assert NET_SALES_CARD in vis_ids
    # every visual entry explains the path back to the column
    for r in res["reports"]:
        for p in r["pages"]:
            for v in p["visuals"]:
                assert v["path"][0] == "fct_sales.NET_AMOUNT"


def test_change_type_changes_severity(graph):
    drop = analysis.impact(graph, [NET_AMOUNT], "drop")["summary"]
    logic = analysis.impact(graph, [NET_AMOUNT], "logic")["summary"]
    assert logic["total"] == drop["total"]
    assert logic["breaks"] < drop["breaks"]
    assert logic["values_may_change"] > 0


def test_region_reaches_rls(graph):
    res = analysis.impact(graph, ["dbt:model.retail_analytics.dim_store.SALES_REGION"])
    roles = [e["name"] for e in res["groups"].get("rls_role", [])]
    assert res["summary"]["rls_roles"] == 1
    assert any("EMEA" in r or "Regional" in r for r in roles)


def test_upstream_of_visual(graph):
    res = analysis.upstream(graph, NET_SALES_CARD)
    root_ids = {r["id"] for r in res["roots"]}
    assert "dbt:source.retail_analytics.raw.order_items.UNIT_PRICE" in root_ids
    assert res["summary"]["measures"] >= 1
    assert res["summary"]["dbt_columns"] >= 5


def test_upstream_of_rls_role(graph):
    res = analysis.upstream(graph, "pbi:RetailSales:rls:Regional Manager")
    assert any(r["id"].endswith("raw.stores.MANAGER_EMAIL") for r in res["roots"])


def test_search_and_catalog(graph):
    assert analysis.find_nodes(graph, "fct_sales.NET_AMOUNT")[0].id == NET_AMOUNT
    assert analysis.find_nodes(graph, "net amount")[0].id == "pbi:RetailSales:Sales[Net Amount]"
    assert any(h.id == NET_AMOUNT for h in analysis.find_nodes(graph, "fctsales net_amount", limit=50))
    rows = analysis.catalog(graph, "measure")
    assert rows and all(r["type"] == "measure" for r in rows)


def test_summary_top_columns(graph, scan):
    s = analysis.summary(graph, scan.warnings)
    assert s["top_columns"][0]["id"] == NET_AMOUNT


def test_store_roundtrip(graph, tmp_path):
    db = store.save(tmp_path / "x.db", graph, {"hello": "world"})
    g2, meta = store.load(db)
    assert len(g2) == len(graph) and meta["hello"] == "world"
    assert analysis.impact(g2, [NET_AMOUNT])["summary"]["total"] == 28
