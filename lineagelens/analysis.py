"""Impact (downstream) and upstream analysis over the lineage graph."""
from __future__ import annotations

import heapq
from collections import defaultdict
from typing import Iterable

from .graph import BREAKS, CONFIDENCE_RANK, MAY_CHANGE, NODE_TYPE_LABELS, LineageGraph, Node, min_conf

WAREHOUSE_TYPES = {"dbt_source_column", "dbt_model_column", "snowflake_view_column", "snowflake_table_column"}
CHANGE_TYPES = {
    "drop": "Drop column",
    "rename": "Rename column",
    "type": "Change data type",
    "logic": "Change logic / values",
}


# ------------------------------------------------------------------ lookup
def display_name(n: Node) -> str:
    if n.type in WAREHOUSE_TYPES:
        return f"{n.parent}.{n.name}"
    if n.type in ("pbi_model_column", "calc_column", "measure"):
        return f"{n.parent}[{n.name}]"
    if n.type == "calc_group_item":
        return f"{n.parent} › {n.name}"
    if n.type == "visual":
        return f"{n.container} › {n.parent} › {n.name}"
    if n.type == "page":
        return f"{n.container} › {n.name}"
    return n.name


def search_keys(n: Node) -> list[str]:
    keys = [n.id, display_name(n), n.name]
    rel = n.data.get("relation")
    if rel:
        keys += [f"{rel}.{n.name}", f"{rel.split('.')[-1]}.{n.name}"]
    if n.type in ("pbi_model_column", "calc_column", "measure"):
        keys += [f"'{n.parent}'[{n.name}]", f"[{n.name}]"]
    return keys


def find_nodes(g: LineageGraph, query: str, types: Iterable[str] | None = None, limit: int = 20) -> list[Node]:
    q = query.strip()
    if q in g:
        return [g.node(q)]
    ql = q.lower()
    tset = set(types) if types else None
    qn = "".join(ch for ch in ql if ch.isalnum())
    exact, suffix, contains, loose = [], [], [], []
    for n in g.nodes():
        if tset and n.type not in tset:
            continue
        keys = [k.lower() for k in search_keys(n)]
        if ql in keys:
            exact.append(n)
        elif any(k.endswith("." + ql) or k.endswith(ql) for k in keys):
            suffix.append(n)
        elif any(ql in k for k in keys):
            contains.append(n)
        elif qn and any(qn in "".join(ch for ch in k if ch.isalnum()) for k in keys):
            loose.append(n)  # ignores spaces / underscores / brackets: "net amount" ~ NET_AMOUNT
    out = exact or suffix or contains or loose
    return out[:limit]


# ------------------------------------------------------------------ impact
def impact(g: LineageGraph, start_ids: list[str], change: str = "drop", max_depth: int = 50) -> dict:
    """Downstream traversal. Best path per node: breaks over may-change, then confidence, then depth."""
    change = change if change in CHANGE_TYPES else "drop"
    best: dict[str, dict] = {}
    heap: list = []
    counter = 0
    for sid in start_ids:
        if sid in g:
            best[sid] = {"impact": BREAKS if change in ("drop", "rename") else MAY_CHANGE, "confidence": "high",
                         "depth": 0, "via": None, "reason": "selected", "start": sid}
            heapq.heappush(heap, (0, 0, 0, counter, sid))
            counter += 1

    def rank(st):
        return (0 if st["impact"] == BREAKS else 1, -CONFIDENCE_RANK[st["confidence"]], st["depth"])

    while heap:
        _, _, _, _, nid = heapq.heappop(heap)
        cur = best[nid]
        if cur["depth"] >= max_depth:
            continue
        for succ, ed in g.flow_successors(nid):
            imp = BREAKS if (cur["impact"] == BREAKS and ed["impact"] == BREAKS and change in ("drop", "rename")) else MAY_CHANGE
            st = {"impact": imp, "confidence": min_conf(cur["confidence"], ed["confidence"]), "depth": cur["depth"] + 1,
                  "via": nid, "reason": ed.get("reason", ""), "start": cur["start"]}
            if succ in start_ids:
                continue
            if succ not in best or rank(st) < rank(best[succ]):
                best[succ] = st
                r = rank(st)
                heapq.heappush(heap, (r[0], r[1], r[2], counter, succ))
                counter += 1
    return _package(g, best, start_ids, change)


def _node_entry(g: LineageGraph, nid: str, st: dict) -> dict:
    n = g.node(nid)
    return {"id": nid, "type": n.type, "type_label": NODE_TYPE_LABELS.get(n.type, n.type), "name": n.name,
            "parent": n.parent, "container": n.container, "display": display_name(n),
            "impact": st["impact"], "confidence": st["confidence"], "depth": st["depth"], "via": st["via"],
            "reason": st["reason"]}


def path_to(best: dict, nid: str) -> list[str]:
    out = []
    cur = nid
    seen = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = best[cur]["via"]
    return list(reversed(out))


def _package(g: LineageGraph, best: dict, start_ids: list[str], change: str) -> dict:
    entries = {nid: _node_entry(g, nid, st) for nid, st in best.items()}
    for nid, e in entries.items():
        e["path"] = [display_name(g.node(p)) for p in path_to(best, nid)]
    impacted = [e for nid, e in entries.items() if nid not in start_ids]
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in impacted:
        by_type[e["type"]].append(e)
    for lst in by_type.values():
        lst.sort(key=lambda e: (e["impact"] != BREAKS, -CONFIDENCE_RANK[e["confidence"]], e["display"]))

    # reports > pages > visuals (+ page / report filters)
    reports: dict[str, dict] = {}

    def rep_entry(rname: str) -> dict:
        if rname not in reports:
            rn = g.node(f"rpt:{rname}")
            reports[rname] = {"id": f"rpt:{rname}", "name": rname, "model": rn.data.get("model") if rn else "",
                              "report_filter": None, "pages": {}, "impact": MAY_CHANGE, "confidence": "low"}
        return reports[rname]

    def page_entry(rep: dict, pid: str) -> dict:
        if pid not in rep["pages"]:
            pn = g.node(pid)
            rep["pages"][pid] = {"id": pid, "name": pn.name if pn else pid, "ordinal": pn.data.get("ordinal", 0) if pn else 0,
                                 "page_filter": None, "visuals": [], "total_visuals": pn.data.get("visuals", 0) if pn else 0}
        return rep["pages"][pid]

    def bump(rep: dict, e: dict) -> None:
        if e["impact"] == BREAKS:
            rep["impact"] = BREAKS
        if CONFIDENCE_RANK[e["confidence"]] > CONFIDENCE_RANK[rep["confidence"]]:
            rep["confidence"] = e["confidence"]

    for e in by_type.get("visual", []):
        n = g.node(e["id"])
        rep = rep_entry(n.container)
        pg = page_entry(rep, n.data.get("page_id", ""))
        fields = n.data.get("fields", [])
        via = g.node(e["via"]) if e["via"] else None
        usage = e["reason"]
        pg["visuals"].append({**e, "visual_type": n.data.get("visual_type", ""), "usage": usage,
                              "via_display": display_name(via) if via else "", "field_count": len(fields)})
        bump(rep, e)
    for e in by_type.get("page", []):
        n = g.node(e["id"])
        rep = rep_entry(n.container)
        pg = page_entry(rep, e["id"])
        pg["page_filter"] = e
        bump(rep, e)
    for e in by_type.get("report", []):
        rep = rep_entry(g.node(e["id"]).name)
        rep["report_filter"] = e
        bump(rep, e)
    report_list = []
    for rep in reports.values():
        pages = sorted(rep["pages"].values(), key=lambda p: p["ordinal"])
        for p in pages:
            p["visuals"].sort(key=lambda v: (v["impact"] != BREAKS, v["display"]))
        rep["pages"] = pages
        rep["visual_count"] = sum(len(p["visuals"]) for p in pages)
        report_list.append(rep)
    report_list.sort(key=lambda r: (r["impact"] != BREAKS, r["name"]))

    breaks = sum(1 for e in impacted if e["impact"] == BREAKS)
    summary = {
        "total": len(impacted), "breaks": breaks, "values_may_change": len(impacted) - breaks,
        "visuals": len(by_type.get("visual", [])),
        "visuals_breaking": sum(1 for e in by_type.get("visual", []) if e["impact"] == BREAKS),
        "measures": len(by_type.get("measure", [])), "rls_roles": len(by_type.get("rls_role", [])),
        "reports": len(report_list), "pages": sum(len(r["pages"]) for r in report_list),
        "calc_columns": len(by_type.get("calc_column", [])), "calc_group_items": len(by_type.get("calc_group_item", [])),
        "field_parameters": len(by_type.get("field_parameter", [])),
        "pbi_columns": len(by_type.get("pbi_model_column", [])),
        "warehouse_columns": sum(len(by_type.get(t, [])) for t in WAREHOUSE_TYPES),
        "low_confidence": sum(1 for e in impacted if e["confidence"] == "low"),
        "medium_confidence": sum(1 for e in impacted if e["confidence"] == "medium"),
    }
    starts = [{**entries[s], "path": [entries[s]["display"]]} for s in start_ids if s in entries]
    return {
        "change": change, "change_label": CHANGE_TYPES[change], "start": starts, "summary": summary,
        "reports": report_list, "groups": {k: v for k, v in by_type.items()},
        "graph": subgraph(g, list(best.keys()), best),
    }


def subgraph(g: LineageGraph, ids: list[str], state: dict | None = None, limit: int = 2500) -> dict:
    from .graphview import annotate
    if len(ids) > limit:  # keep the closest objects (smallest depth) when truncating
        ids = sorted(ids, key=lambda i: (state or {}).get(i, {}).get("depth", 0))
    idset = set(ids[:limit])
    nodes = []
    for nid in idset:
        n = g.node(nid)
        st = (state or {}).get(nid, {})
        nodes.append({"id": nid, "type": n.type, "name": n.name, "parent": n.parent, "container": n.container,
                      "display": display_name(n), "impact": st.get("impact"), "confidence": st.get("confidence"),
                      "depth": st.get("depth", 0), "start": st.get("depth", 1) == 0})
    edges = []
    for s, t, d in g.edges("flow"):
        if s in idset and t in idset:
            edges.append({"source": s, "target": t, "confidence": d["confidence"], "impact": d["impact"], "reason": d.get("reason", "")})
    return annotate(g, {"nodes": nodes, "edges": edges, "truncated": len(ids) > limit, "total": len(ids)})


# ------------------------------------------------------------------ upstream
def upstream(g: LineageGraph, start_id: str, max_depth: int = 50) -> dict:
    starts = [start_id]
    n0 = g.node(start_id)
    if n0 and n0.type in ("page", "report"):
        starts = [start_id] + [c for c in _descendants_contains(g, start_id)]
    best: dict[str, dict] = {}
    queue = []
    for s in starts:
        best[s] = {"impact": BREAKS, "confidence": "high", "depth": 0, "via": None, "reason": "selected", "start": s}
        queue.append(s)
    while queue:
        nid = queue.pop(0)
        cur = best[nid]
        if cur["depth"] >= max_depth:
            continue
        for pred, ed in g.flow_predecessors(nid):
            st = {"impact": BREAKS if cur["impact"] == BREAKS and ed["impact"] == BREAKS else MAY_CHANGE,
                  "confidence": min_conf(cur["confidence"], ed["confidence"]), "depth": cur["depth"] + 1,
                  "via": nid, "reason": ed.get("reason", ""), "start": cur["start"]}
            if pred not in best or (st["impact"] == BREAKS and best[pred]["impact"] != BREAKS) or \
                    (st["impact"] == best[pred]["impact"] and CONFIDENCE_RANK[st["confidence"]] > CONFIDENCE_RANK[best[pred]["confidence"]]):
                best[pred] = st
                queue.append(pred)
    entries = {nid: _node_entry(g, nid, st) for nid, st in best.items()}
    for nid, e in entries.items():
        e["path"] = [display_name(g.node(p)) for p in path_to(best, nid)]
        e["direct"] = st_direct(best, nid)
    found = [e for nid, e in entries.items() if nid not in starts]
    groups: dict[str, list[dict]] = defaultdict(list)
    for e in found:
        e["role"] = "direct dependency" if e["impact"] == BREAKS else "filter / join dependency"
        groups[e["type"]].append(e)
    for lst in groups.values():
        lst.sort(key=lambda e: (e["impact"] != BREAKS, e["depth"], e["display"]))
    roots = [e for e in found if not any(True for _ in g.flow_predecessors(e["id"]))]
    return {"start": entries[start_id] if start_id in entries else None, "groups": dict(groups),
            "roots": sorted(roots, key=lambda e: e["display"]),
            "summary": {"total": len(found), "source_columns": len([e for e in found if e["type"] in ("dbt_source_column", "snowflake_table_column")]),
                        "dbt_columns": len(groups.get("dbt_model_column", [])), "view_columns": len(groups.get("snowflake_view_column", [])),
                        "pbi_columns": len(groups.get("pbi_model_column", [])), "measures": len(groups.get("measure", []))},
            "graph": subgraph(g, list(best.keys()), best)}


def st_direct(best: dict, nid: str) -> bool:
    return best[nid]["depth"] == 1


def _descendants_contains(g: LineageGraph, nid: str) -> list[str]:
    out, stack = [], [nid]
    while stack:
        cur = stack.pop()
        for c in g.children(cur):
            out.append(c)
            stack.append(c)
    return out


# ------------------------------------------------------------------ catalog / summary
def downstream_counts(g: LineageGraph) -> dict[str, dict]:
    """For every node: number of downstream visuals / measures (memoised DFS on the DAG)."""
    import networkx as nx
    flow = nx.DiGraph()
    flow.add_nodes_from(g.g.nodes)
    flow.add_edges_from((s, t) for s, t, d in g.edges("flow"))
    out: dict[str, dict] = {}
    try:
        order = list(reversed(list(nx.topological_sort(flow))))
    except nx.NetworkXUnfeasible:
        order = list(flow.nodes)
    vis: dict[str, set] = {}
    meas: dict[str, set] = {}
    for nid in order:
        v, m = set(), set()
        for s in flow.successors(nid):
            v |= vis.get(s, set())
            m |= meas.get(s, set())
            t = g.g.nodes[s]["type"]
            if t == "visual":
                v.add(s)
            elif t == "measure":
                m.add(s)
        vis[nid], meas[nid] = v, m
        out[nid] = {"visuals": len(v), "measures": len(m)}
    return out


def catalog(g: LineageGraph, kind: str | None = None, counts: dict | None = None) -> list[dict]:
    counts = counts or downstream_counts(g)
    rows = []
    for n in g.nodes(kind):
        if n.type in ("semantic_model",):
            continue
        c = counts.get(n.id, {})
        rows.append({"id": n.id, "type": n.type, "type_label": NODE_TYPE_LABELS.get(n.type, n.type), "name": n.name,
                     "parent": n.parent, "container": n.container, "display": display_name(n),
                     "description": n.description, "data_type": n.data.get("data_type", ""),
                     "transform": n.data.get("transform", ""), "match_method": n.data.get("match_method", ""),
                     "unmatched": bool(n.data.get("unmatched")), "visual_type": n.data.get("visual_type", ""),
                     "downstream_visuals": c.get("visuals", 0), "downstream_measures": c.get("measures", 0),
                     "upstream": sum(1 for _ in g.flow_predecessors(n.id)), "downstream": sum(1 for _ in g.flow_successors(n.id))})
    rows.sort(key=lambda r: (r["type"], r["container"], r["parent"], r["name"]))
    return rows


def summary(g: LineageGraph, warnings: list[dict] | None = None, counts: dict | None = None) -> dict:
    counts = counts or downstream_counts(g)
    by_type: dict[str, int] = defaultdict(int)
    for n in g.nodes():
        by_type[n.type] += 1
    pbi_cols = list(g.nodes("pbi_model_column"))
    matched = [n for n in pbi_cols if any(True for p, _ in g.flow_predecessors(n.id) if g.g.nodes[p]["type"] in WAREHOUSE_TYPES)]
    unmatched = [n for n in pbi_cols if n.data.get("unmatched")]
    conf = defaultdict(int)
    for s, t, d in g.edges("flow"):
        conf[d["confidence"]] += 1
    gold = [n for n in g.nodes() if n.type in WAREHOUSE_TYPES]
    unused_gold = [n for n in gold if g.g.nodes[n.id]["type"] != "dbt_source_column" and counts.get(n.id, {}).get("visuals", 0) == 0
                   and _is_leaf_layer(g, n)]
    unused_pbi = [n for n in pbi_cols + list(g.nodes("calc_column")) + list(g.nodes("measure"))
                  if counts.get(n.id, {}).get("visuals", 0) == 0 and not any(g.g.nodes[s]["type"] == "rls_role" for s, _ in g.flow_successors(n.id))]
    top = sorted((n for n in gold if _is_leaf_layer(g, n)), key=lambda n: -counts.get(n.id, {}).get("visuals", 0))[:10]
    reports = []
    for r in g.nodes("report"):
        reports.append({"id": r.id, "name": r.name, "format": r.data.get("format"), "model": r.data.get("model"),
                        "pages": r.data.get("pages", 0), "visuals": r.data.get("visuals", 0), "model_resolved": r.data.get("model_resolved")})
    models = [{"id": m.id, "name": m.name, "format": m.data.get("format"), "tables": m.data.get("tables"), "roles": m.data.get("roles")}
              for m in g.nodes("semantic_model")]
    return {
        "counts": dict(by_type),
        "edges": sum(1 for _ in g.edges("flow")),
        "confidence": dict(conf),
        "pbi_column_coverage": {"total": len(pbi_cols), "matched": len(matched), "unmatched": len(unmatched),
                                "unmatched_list": [{"id": n.id, "display": display_name(n), "source_column": n.data.get("source_column", "")} for n in unmatched]},
        "top_columns": [{"id": n.id, "display": display_name(n), "type": n.type, "visuals": counts.get(n.id, {}).get("visuals", 0),
                         "measures": counts.get(n.id, {}).get("measures", 0)} for n in top if counts.get(n.id, {}).get("visuals", 0)],
        "unused_gold_columns": [{"id": n.id, "display": display_name(n)} for n in unused_gold][:200],
        "unused_pbi_objects": [{"id": n.id, "display": display_name(n), "type": n.type} for n in unused_pbi][:200],
        "reports": reports, "models": models,
        "warnings": warnings or [],
    }


def _is_leaf_layer(g: LineageGraph, n: Node) -> bool:
    """Gold-ish columns: warehouse columns that feed Power BI directly or have no warehouse consumers."""
    succ_types = {g.g.nodes[s]["type"] for s, _ in g.flow_successors(n.id)}
    feeds_pbi = any(t not in WAREHOUSE_TYPES for t in succ_types)
    return feeds_pbi or not (succ_types & WAREHOUSE_TYPES)
