"""Lane / sub-level / group annotation of lineage graphs + the large synthetic sample."""
import time
from collections import Counter

import pytest
from conftest import NET_AMOUNT
from fastapi.testclient import TestClient

from lineagelens import analysis
from lineagelens.builder import build
from lineagelens.config import LARGE_SAMPLE_CONFIG, SAMPLES, load_config, sample_name
from lineagelens.graphview import LANES, MAX_SUBLEVEL, annotate
from lineagelens.server import create_app

NET_REVENUE = "dbt:model.helios_analytics.fct_sales_lines.NET_REVENUE"


@pytest.fixture(scope="module")
def large():
    return build(load_config(LARGE_SAMPLE_CONFIG)).graph


def _by_id(sub):
    return {n["id"]: n for n in sub["nodes"]}


def test_every_node_has_lane_and_group(graph):
    sub = analysis.impact(graph, [NET_AMOUNT])["graph"]
    assert sub["lanes"] == [{"index": i, "key": k, "label": lbl} for i, (k, lbl) in enumerate(LANES)]
    for n in sub["nodes"]:
        assert 0 <= n["lane"] < len(LANES)
        assert n["group"] and n["group_label"] and n["group_kind"]
        assert 0 <= n["sublevel"] <= MAX_SUBLEVEL


def test_lane_order_follows_flow(graph):
    """Lineage only ever moves left-to-right (or down a sub-level inside a lane)."""
    sub = analysis.impact(graph, [NET_AMOUNT])["graph"]
    ids = _by_id(sub)
    for e in sub["edges"]:
        s, t = ids[e["source"]], ids[e["target"]]
        assert (s["lane"], s["sublevel"]) < (t["lane"], t["sublevel"]) or s["lane"] == t["lane"] == 7 or \
            (s["lane"] == t["lane"] and s["sublevel"] == t["sublevel"] == MAX_SUBLEVEL), (e, s, t)


def test_lanes_for_types(graph):
    sub = analysis.impact(graph, [NET_AMOUNT])["graph"]
    lanes = {n["type"]: n["lane_key"] for n in sub["nodes"]}
    assert lanes["measure"] == "pbi_logic"
    assert lanes["visual"] == "reports"
    assert lanes["pbi_model_column"] == "pbi_column"
    assert lanes["dbt_model_column"] == "dbt_marts"  # fct_sales lives in marts


def test_staging_lane_and_visual_page_metadata(graph):
    up = analysis.upstream(graph, "pbi:RetailSales:Sales[Net Amount]")["graph"]
    kinds = Counter(n["lane_key"] for n in up["nodes"])
    assert kinds["dbt_staging"] >= 1 and kinds["source"] >= 1
    imp = analysis.impact(graph, [NET_AMOUNT])["graph"]
    vis = [n for n in imp["nodes"] if n["type"] == "visual"]
    assert vis and all(v["page_id"].startswith("rpt:") and v["page_name"] and v["report_name"] for v in vis)
    assert all(v["group"] == f"page:{v['page_id']}" for v in vis)
    assert all(v["page_visuals_total"] >= 1 for v in vis)


def test_measure_chain_sublevels(graph):
    sub = analysis.impact(graph, [NET_AMOUNT])["graph"]
    ids = _by_id(sub)
    # a measure that references another measure sits at least one sub-column to the right
    for e in sub["edges"]:
        s, t = ids[e["source"]], ids[e["target"]]
        if s["type"] == t["type"] == "measure" and t["sublevel"] < MAX_SUBLEVEL:
            assert t["sublevel"] > s["sublevel"]
    assert max(n["sublevel"] for n in sub["nodes"] if n["type"] == "measure") >= 1


def test_annotate_handles_cycles(graph):
    sub = {"nodes": [{"id": NET_AMOUNT}, {"id": "pbi:RetailSales:Sales[Net Amount]"}],
           "edges": [{"source": NET_AMOUNT, "target": NET_AMOUNT}]}
    out = annotate(graph, sub)
    assert [n["sublevel"] for n in out["nodes"]] == [0, 0]


def test_large_sample_scale(large):
    s = analysis.summary(large)
    c = s["counts"]
    assert c["dbt_model_column"] >= 300 and c["measure"] >= 80 and c["visual"] >= 150
    assert c["rls_role"] == 4 and c["report"] >= 6 and len(s["models"]) == 3
    assert s["pbi_column_coverage"]["matched"] == s["pbi_column_coverage"]["total"]
    models = {n.data.get("dbt_unique_id") for n in large.nodes("dbt_model_column")}
    assert len(models) >= 40


def test_large_high_fanout_graph(large):
    t0 = time.time()
    res = analysis.impact(large, [NET_REVENUE])
    assert time.time() - t0 < 5
    sub = res["graph"]
    assert not sub["truncated"]
    assert res["summary"]["visuals"] >= 30
    lanes = Counter(n["lane_key"] for n in sub["nodes"])
    assert lanes["reports"] >= 30 and lanes["pbi_logic"] >= 20
    pages = {n["page_id"] for n in sub["nodes"] if n["type"] == "visual"}
    reports = {n["report_name"] for n in sub["nodes"] if n["type"] == "visual"}
    assert len(pages) >= 8 and len(reports) >= 3


def test_sample_selection_api():
    assert sample_name(None) == "standard" and sample_name(LARGE_SAMPLE_CONFIG) == "large"
    assert set(SAMPLES) == {"standard", "large"}
    c = TestClient(create_app(None, scan_on_start=False))
    cfg = c.get("/api/config").json()
    assert {s["name"] for s in cfg["samples"]} == {"standard", "large"}
    assert c.post("/api/config/sample", json={"name": "nope"}).status_code == 400
    assert c.post("/api/config/sample", json={"name": "large"}).status_code == 200
    for _ in range(100):
        st = c.get("/api/scan/status").json()
        if not st["running"]:
            break
        time.sleep(0.1)
    assert c.get("/api/summary").json()["sample_name"] == "large"
    assert c.get("/api/health").json()["nodes"] > 800
    # bundled sample configs are read-only
    assert c.put("/api/config", json={"path": str(LARGE_SAMPLE_CONFIG), "yaml": "project_name: x"}).status_code == 400
    assert c.post("/api/config/sample", json={}).status_code == 200
