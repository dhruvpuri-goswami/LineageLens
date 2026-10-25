"""Compare two versions (scans, dbt manifests or configs) and compute the downstream impact of the changes."""
from __future__ import annotations

import re
from pathlib import Path

from . import store
from .analysis import WAREHOUSE_TYPES, display_name, impact
from .builder import build
from .config import Config, DbtSource, load_config
from .graph import BREAKS, LineageGraph

TRACKED = WAREHOUSE_TYPES | {"pbi_model_column", "calc_column", "measure", "calc_group_item", "field_parameter", "rls_role"}
PBI_IMPACT_TYPES = {"pbi_model_column", "calc_column", "measure", "calc_group_item", "field_parameter", "rls_role", "visual", "page", "report"}


def load_any(path: str | Path, base_cfg: Config | None = None) -> LineageGraph:
    """Load a graph from: lineage .db, LineageLens config .yml, dbt manifest.json, or a dbt project folder."""
    p = Path(path)
    if p.suffix.lower() in (".db", ".sqlite"):
        return store.load(p)[0]
    if p.suffix.lower() in (".yml", ".yaml"):
        return build(load_config(p)).graph
    manifest = None
    if p.is_file() and p.suffix.lower() == ".json":
        manifest = p
    elif p.is_dir() and (p / "target" / "manifest.json").exists():
        manifest = p / "target" / "manifest.json"
    elif p.is_dir() and (p / "manifest.json").exists():
        manifest = p / "manifest.json"
    if manifest is None:
        raise ValueError(f"don't know how to load {path}: expected .db, .yml, manifest.json or a dbt project folder")
    catalog = manifest.parent / "catalog.json"
    proj_dir = manifest.parent.parent if (manifest.parent.parent / "dbt_project.yml").exists() else None
    cfg = Config(path=None, base_dir=manifest.parent, project_name="diff")
    cfg.dbt = [DbtSource(manifest, catalog if catalog.exists() else None, proj_dir)]
    if base_cfg is not None:  # keep views so view lineage is comparable
        cfg.view_dirs = base_cfg.view_dirs
        cfg.default_database, cfg.default_schema = base_cfg.default_database, base_cfg.default_schema
    return build(cfg).graph


def _norm(code: str) -> str:
    return re.sub(r"\s+", " ", (code or "").strip()).lower()


def _signature(g: LineageGraph, nid: str) -> str:
    n = g.node(nid)
    if n.type in WAREHOUSE_TYPES:
        return _norm(n.data.get("expression", ""))
    return _norm(n.code)


def _preds(g: LineageGraph, nid: str) -> set[str]:
    return {s for s, _ in g.flow_predecessors(nid)}


def compare(old: LineageGraph, new: LineageGraph) -> list[dict]:
    changes: list[dict] = []
    old_ids = {n.id for n in old.nodes() if n.type in TRACKED and not n.data.get("external")}
    new_ids = {n.id for n in new.nodes() if n.type in TRACKED and not n.data.get("external")}
    added = new_ids - old_ids
    removed = old_ids - new_ids
    # rename detection: same parent relation, same upstream sources
    added_by_parent: dict[tuple, list[str]] = {}
    for a in added:
        n = new.node(a)
        added_by_parent.setdefault((n.type, n.container, n.parent), []).append(a)
    used_added = set()
    for r in sorted(removed):
        n = old.node(r)
        cands = [a for a in added_by_parent.get((n.type, n.container, n.parent), []) if a not in used_added]
        rp = _preds(old, r)
        match = None
        for a in cands:
            ap = _preds(new, a)
            if (rp and rp == ap) or (_signature(old, r) and _signature(old, r).split(" as ")[0] == _signature(new, a).split(" as ")[0]):
                match = a
                break
        if match is None and len(cands) == 1 and len([x for x in removed if (old.node(x).type, old.node(x).container, old.node(x).parent) == (n.type, n.container, n.parent)]) == 1:
            match = cands[0]
        if match:
            used_added.add(match)
            changes.append({"id": r, "display": display_name(n), "type": n.type, "change": "rename",
                            "detail": f"renamed to {new.node(match).name}", "new_id": match})
        else:
            changes.append({"id": r, "display": display_name(n), "type": n.type, "change": "drop", "detail": "removed"})
    for nid in sorted(old_ids & new_ids):
        o, nn = old.node(nid), new.node(nid)
        ot, nt = (o.data.get("data_type") or "").upper(), (nn.data.get("data_type") or "").upper()
        if ot and nt and ot != nt:
            changes.append({"id": nid, "display": display_name(o), "type": o.type, "change": "type", "detail": f"type {ot} → {nt}"})
            continue
        so, sn = _signature(old, nid), _signature(new, nid)
        if so != sn and (so or sn):
            changes.append({"id": nid, "display": display_name(o), "type": o.type, "change": "logic",
                            "detail": "expression changed", "old": o.data.get("expression") or o.code, "new": nn.data.get("expression") or nn.code})
    for a in sorted(added - used_added):
        n = new.node(a)
        changes.append({"id": a, "display": display_name(n), "type": n.type, "change": "add", "detail": "new column/object"})
    return changes


def run_diff(old_path: str | Path, new_path: str | Path, base: LineageGraph | None = None, base_cfg: Config | None = None) -> dict:
    old = load_any(old_path, base_cfg)
    new = load_any(new_path, base_cfg)
    return diff_graphs(old, new, base)


def diff_graphs(old: LineageGraph, new: LineageGraph, base: LineageGraph | None = None) -> dict:
    changes = compare(old, new)
    base = base or old
    impacted_visuals: dict[str, dict] = {}
    impacted_objects: dict[str, dict] = {}
    breaking = False
    for ch in changes:
        if ch["change"] == "add" or ch["id"] not in base:
            ch["impact"] = None
            continue
        res = impact(base, [ch["id"]], ch["change"])
        s = res["summary"]
        ch["impact"] = {"summary": s, "reports": res["reports"]}
        pbi_hits = [e for t, lst in res["groups"].items() if t in PBI_IMPACT_TYPES for e in lst]
        ch["breaking"] = any(e["impact"] == BREAKS for e in pbi_hits)
        ch["pbi_objects"] = len(pbi_hits)
        breaking = breaking or ch["breaking"]
        for e in pbi_hits:
            key = e["id"]
            tgt = impacted_visuals if e["type"] == "visual" else impacted_objects
            prev = tgt.get(key)
            if prev is None or (e["impact"] == BREAKS and prev["impact"] != BREAKS):
                tgt[key] = {**e, "cause": ch["display"], "cause_change": ch["change"]}
    return {
        "changes": changes,
        "breaking": breaking,
        "summary": {
            "changes": len([c for c in changes if c["change"] != "add"]), "added": len([c for c in changes if c["change"] == "add"]),
            "visuals": len(impacted_visuals), "visuals_breaking": sum(1 for v in impacted_visuals.values() if v["impact"] == BREAKS),
            "objects": len(impacted_objects), "objects_breaking": sum(1 for v in impacted_objects.values() if v["impact"] == BREAKS),
        },
        "visuals": sorted(impacted_visuals.values(), key=lambda v: (v["impact"] != BREAKS, v["display"])),
        "objects": sorted(impacted_objects.values(), key=lambda v: (v["impact"] != BREAKS, v["type"], v["display"])),
    }


ICON = {"drop": "🗑️ drop", "rename": "✏️ rename", "type": "🔤 type", "logic": "🧮 logic", "add": "➕ add"}


def to_markdown(result: dict, title: str = "LineageLens impact report", max_rows: int = 40) -> str:
    s = result["summary"]
    lines = [f"## {'🔴' if result['breaking'] else '🟢'} {title}", ""]
    if result["breaking"]:
        lines.append(f"**Breaking change detected:** {s['visuals_breaking']} visual(s) and {s['objects_breaking']} model object(s) will break.")
    else:
        lines.append("No breaking downstream impact on Power BI detected.")
    lines += ["", f"| Changes | Visuals affected | Visuals breaking | Model objects affected |", "|---:|---:|---:|---:|",
              f"| {s['changes']} | {s['visuals']} | {s['visuals_breaking']} | {s['objects']} |", ""]
    changes = [c for c in result["changes"] if c["change"] != "add"]
    if changes:
        lines += ["### Column changes", "", "| Change | Column | Detail | Power BI objects | Breaking |", "|---|---|---|---:|:---:|"]
        for c in changes[:max_rows]:
            lines.append(f"| {ICON.get(c['change'], c['change'])} | `{c['display']}` | {c['detail']} | {c.get('pbi_objects', 0)} | {'❌' if c.get('breaking') else '—'} |")
        lines.append("")
    if result["visuals"]:
        lines += ["### Affected visuals", "", "| Report › Page › Visual | Impact | Confidence | Caused by |", "|---|---|---|---|"]
        for v in result["visuals"][:max_rows]:
            lines.append(f"| {v['display']} | {'breaks' if v['impact'] == BREAKS else 'values may change'} | {v['confidence']} | `{v['cause']}` ({v['cause_change']}) |")
        if len(result["visuals"]) > max_rows:
            lines.append(f"| … {len(result['visuals']) - max_rows} more | | | |")
        lines.append("")
    rls = [o for o in result["objects"] if o["type"] == "rls_role"]
    if rls:
        lines += ["### ⚠️ Row-level security roles affected", ""] + [f"- **{o['display']}** ({'breaks' if o['impact'] == BREAKS else 'values may change'}) ← `{o['cause']}`" for o in rls] + [""]
    meas = [o for o in result["objects"] if o["type"] == "measure"]
    if meas:
        lines += ["<details><summary>Measures affected (" + str(len(meas)) + ")</summary>", ""]
        lines += [f"- {o['display']} — {'breaks' if o['impact'] == BREAKS else 'values may change'}" for o in meas[:max_rows * 2]]
        lines += ["", "</details>", ""]
    lines.append("_Generated offline by LineageLens — deterministic parsing, no data leaves your machine._")
    return "\n".join(lines)
