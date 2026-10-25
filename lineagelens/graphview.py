"""Presentation metadata for lineage sub-graphs (deterministic, no layout engine needed server-side).

Every node in an impact / upstream graph gets:

* ``lane`` / ``lane_label`` - fixed swim-lane, left to right:
  0 Sources -> 1 dbt staging & intermediate -> 2 dbt marts (gold) -> 3 Snowflake views -> 4 Power BI columns
  -> 5 Measures & calc columns -> 6 Row-level security -> 7 Reports, pages & visuals
* ``sublevel`` - longest path from another node *in the same lane* (e.g. measure chains: base -> ratio -> YoY -> label)
* ``group`` / ``group_label`` / ``group_kind`` - the container the UI uses for grouping & collapsing
  (dbt model, source table, view, Power BI table, RLS roles of a model, report page)
* visuals also get ``report_id``, ``report_name``, ``page_id``, ``page_name``, ``visual_type``
"""
from __future__ import annotations

from collections import defaultdict

from .graph import LineageGraph

LANES = [
    ("source", "Sources"),
    ("dbt_staging", "dbt staging & intermediate"),
    ("dbt_marts", "dbt marts (gold)"),
    ("snowflake_view", "Snowflake views"),
    ("pbi_column", "Power BI columns"),
    ("pbi_logic", "Measures & calc columns"),
    ("rls", "Row-level security"),
    ("reports", "Reports, pages & visuals"),
]
LANE_INDEX = {k: i for i, (k, _) in enumerate(LANES)}
MAX_SUBLEVEL = 4  # deeper chains are merged into the last sub-column
STAGING_PREFIXES = ("stg_", "staging_", "int_", "base_", "src_", "raw_", "prep_", "tmp_")


def _is_staging(data: dict, name: str, file: str) -> bool:
    if data.get("resource_type") in ("seed", "snapshot"):
        return True
    low = (name or "").lower()
    if low.startswith(STAGING_PREFIXES):
        return True
    f = (file or "").replace("\\", "/").lower()
    if any(seg in f for seg in ("/staging/", "/intermediate/", "/base/")) or f.startswith(("models/staging", "models/intermediate", "staging/", "intermediate/")):
        return True
    sch = str(data.get("schema", "")).upper()
    return any(k in sch for k in ("STAGING", "INTERMEDIATE", "STG"))


def lane_of(g: LineageGraph, nid: str) -> str:
    n = g.node(nid)
    t = n.type
    if t in ("dbt_source_column", "snowflake_table_column"):
        return "source"
    if t == "dbt_model_column":
        model = (n.data.get("dbt_unique_id") or "").split(".")[-1] or n.parent
        return "dbt_staging" if _is_staging(n.data, model, n.file) else "dbt_marts"
    if t == "snowflake_view_column":
        return "snowflake_view"
    if t == "pbi_model_column":
        return "pbi_column"
    if t in ("calc_column", "measure", "calc_group_item", "field_parameter"):
        return "pbi_logic"
    if t == "rls_role":
        return "rls"
    return "reports"


def _group(g: LineageGraph, nid: str) -> tuple[str, str, str]:
    """(group key, label, kind)"""
    n = g.node(nid)
    t, d = n.type, n.data
    if t == "dbt_source_column":
        return f"src:{d.get('relation') or n.parent}", n.parent, "source table"
    if t == "snowflake_table_column":
        return f"sft:{d.get('relation') or n.parent}", n.parent, "table"
    if t == "dbt_model_column":
        return f"dbt:{d.get('dbt_unique_id') or n.parent}", n.parent, "dbt model"
    if t == "snowflake_view_column":
        return f"view:{d.get('relation') or n.parent}", n.parent, "view"
    if t in ("pbi_model_column", "calc_column"):
        tbl = d.get("table") or n.parent
        return f"tbl:{n.container}:{tbl}", tbl, "table"
    if t in ("measure", "calc_group_item", "field_parameter"):
        tbl = d.get("table") or n.parent
        model = d.get("model") or n.container
        return f"meas:{model}:{tbl}", tbl, "measures"
    if t == "rls_role":
        return f"rls:{n.container}", n.container, "roles"
    if t == "visual":
        return f"page:{d.get('page_id')}", d.get("page") or n.parent, "page"
    if t == "page":
        return f"report:rpt:{n.container}", n.container, "report"
    if t == "report":
        return f"report:{nid}", n.name, "report"
    return f"other:{t}", t, "other"


def annotate(g: LineageGraph, sub: dict) -> dict:
    """Add lane / sublevel / group metadata to a ``subgraph()`` payload in place and return it."""
    nodes = sub["nodes"]
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        lane = lane_of(g, n["id"])
        n["lane"] = LANE_INDEX[lane]
        n["lane_key"] = lane
        n["lane_label"] = LANES[LANE_INDEX[lane]][1]
        key, label, kind = _group(g, n["id"])
        n["group"], n["group_label"], n["group_kind"] = key, label, kind
        gn = g.node(n["id"])
        if gn.type == "visual":
            n["visual_type"] = gn.data.get("visual_type", "")
            n["page_id"] = gn.data.get("page_id", "")
            n["page_name"] = gn.data.get("page") or gn.parent
            n["report_name"] = gn.data.get("report") or gn.container
            n["report_id"] = f"rpt:{n['report_name']}"
            pg = g.node(n["page_id"]) if n["page_id"] else None
            n["page_ordinal"] = pg.data.get("ordinal", 0) if pg else 0
            n["page_visuals_total"] = pg.data.get("visuals", 0) if pg else 0
        elif gn.type == "page":
            n["page_id"], n["page_name"] = n["id"], gn.name
            n["report_name"] = gn.container
            n["report_id"] = f"rpt:{gn.container}"
            n["page_ordinal"] = gn.data.get("ordinal", 0)
            n["page_visuals_total"] = gn.data.get("visuals", 0)
        elif gn.type == "report":
            n["report_name"], n["report_id"] = gn.name, n["id"]
    # sub-levels: longest path inside the same lane (DAG; cycles are broken by visiting order)
    succ: dict[str, list[str]] = defaultdict(list)
    indeg: dict[str, int] = defaultdict(int)
    for e in sub["edges"]:
        s, t = e["source"], e["target"]
        if s in by_id and t in by_id and by_id[s]["lane"] == by_id[t]["lane"] and s != t:
            succ[s].append(t)
            indeg[t] += 1
    level = {n["id"]: 0 for n in nodes}
    queue = [nid for nid in by_id if indeg[nid] == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for nxt in succ[cur]:
            level[nxt] = max(level[nxt], level[cur] + 1)
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    for n in nodes:
        n["sublevel"] = 0 if n["lane_key"] == "reports" else min(level[n["id"]], MAX_SUBLEVEL)
    sub["lanes"] = [{"index": i, "key": k, "label": lbl} for i, (k, lbl) in enumerate(LANES)]
    return sub
