"""Scan all configured sources and build the typed lineage graph."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from graphlib import TopologicalSorter, CycleError
from pathlib import Path
from typing import Callable

from . import __version__
from .config import Config
from .extractors import dax as daxmod
from .extractors.dbt import DbtProject, load_dbt
from .extractors.mquery import parse_m
from .extractors.pbimodel import SemanticModel, PTable, load_semantic_model
from .extractors.reports import Report, FieldRef, load_report
from .extractors.snowflake import SnowflakeObjects, ViewDef, load_view_files, load_live
from .graph import BREAKS, MAY_CHANGE, LineageGraph, Node, min_conf
from .naming import NamingRules, best_match
from .sqllineage import lineage_for_sql, referenced_relations

Progress = Callable[[str, int, str], None]


@dataclass
class ScanResult:
    graph: LineageGraph
    warnings: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    started: float = 0.0
    finished: float = 0.0
    sources: dict = field(default_factory=dict)


def _noop(step: str, pct: int, msg: str) -> None:
    pass


class Builder:
    def __init__(self, cfg: Config, progress: Progress | None = None):
        self.cfg = cfg
        self.g = LineageGraph()
        self.progress = progress or _noop
        self.rules = NamingRules.from_dict(cfg.naming)
        self.warnings: list[dict] = []
        self.rel_index: dict[str, dict[str, str]] = {}      # REL -> {COL: node_id}
        self.rel_meta: dict[str, dict] = {}
        self.schema: dict = {}                               # sqlglot schema {DB:{SCH:{TBL:{COL:TYPE}}}}
        self.models: dict[str, SemanticModel] = {}
        self.sources: dict = {"dbt": [], "views": [], "semantic_models": [], "reports": []}

    # ------------------------------------------------------------------ helpers
    def warn(self, source: str, message: str, level: str = "warning") -> None:
        self.warnings.append({"level": level, "source": source, "message": message})

    def _schema_put(self, rel: str, cols: dict[str, str]) -> None:
        parts = rel.split(".")
        if len(parts) != 3:
            return
        db, sch, tbl = parts
        self.schema.setdefault(db, {}).setdefault(sch, {})[tbl] = {c: (t or "VARCHAR") for c, t in cols.items()}

    def _register(self, rel: str, col: str, node_id: str, meta: dict) -> None:
        self.rel_index.setdefault(rel, {})[col] = node_id
        self.rel_meta.setdefault(rel, meta)

    def find_relation(self, rel: str) -> str | None:
        rel = rel.upper()
        if rel in self.rel_index:
            return rel
        parts = rel.split(".")
        suffix = "." + ".".join(parts[-2:]) if len(parts) >= 2 else "." + parts[-1]
        cands = [k for k in self.rel_index if k.endswith(suffix) or k == suffix[1:]]
        if len(cands) == 1:
            return cands[0]
        if len(parts) >= 1:
            cands = [k for k in self.rel_index if k.split(".")[-1] == parts[-1]]
            if len(cands) == 1:
                return cands[0]
        return None

    def upstream_col(self, rel: str, col: str, create_external: bool = True) -> str | None:
        rel = rel.upper()
        col = col.upper()
        found = self.find_relation(rel)
        if found and col in self.rel_index[found]:
            return self.rel_index[found][col]
        if not create_external:
            return None
        key = found or rel
        nid = f"sf:{key}.{col}"
        if nid not in self.g:
            self.g.add_node(Node(nid, "snowflake_table_column", col, parent=key.split(".")[-1], container="Snowflake",
                                 data={"relation": key, "external": True, "layer": "warehouse"},
                                 description="Referenced in SQL but not defined in the scanned dbt project or view scripts"))
            self._register(key, col, nid, {"layer": "table", "name": key.split(".")[-1], "external": True})
        return nid

    # ------------------------------------------------------------------ dbt
    def scan_dbt(self) -> None:
        for src in self.cfg.dbt:
            if not src.manifest.exists():
                self.warn("dbt", f"manifest not found: {src.manifest} (run `dbt compile` or `dbt docs generate`)", "error")
                continue
            try:
                proj = load_dbt(src.manifest, src.catalog, src.project_dir)
            except Exception as ex:
                self.warn("dbt", f"could not read {src.manifest}: {ex}", "error")
                continue
            for w in proj.warnings:
                self.warn(f"dbt:{proj.name}", w)
            self.sources["dbt"].append({"name": proj.name, "manifest": str(src.manifest), "nodes": len(proj.nodes), "catalog": proj.has_catalog})
            self._ingest_dbt(proj)

    def _ingest_dbt(self, proj: DbtProject) -> None:
        # register all known columns first (sources, seeds, catalog columns)
        for n in proj.nodes.values():
            ntype = "dbt_source_column" if n.resource_type == "source" else "dbt_model_column"
            rel = n.relation
            for col in n.columns.values():
                nid = f"dbt:{n.unique_id}.{col.name}"
                self.g.add_node(Node(nid, ntype, col.name, parent=n.display, container=proj.name, file=n.file,
                                     description=col.description,
                                     data={"relation": rel, "resource_type": n.resource_type, "materialized": n.materialized,
                                           "data_type": col.data_type, "dbt_unique_id": n.unique_id, "layer": "dbt",
                                           "model_description": n.description, "schema": n.schema.upper(), "database": n.database.upper()}))
                self._register(rel, col.name, nid, {"layer": "dbt", "name": n.display, "unique_id": n.unique_id, "resource_type": n.resource_type})
            if n.columns:
                self._schema_put(rel, {c.name: c.data_type for c in n.columns.values()})
        # model lineage in dependency order
        ts = TopologicalSorter()
        for uid, n in proj.nodes.items():
            ts.add(uid, *[d for d in n.depends_on if d in proj.nodes])
        try:
            order = list(ts.static_order())
        except CycleError:
            order = list(proj.nodes)
            self.warn(f"dbt:{proj.name}", "dependency cycle detected; processing in manifest order")
        total = max(1, len(order))
        for i, uid in enumerate(order):
            n = proj.nodes[uid]
            if n.resource_type not in ("model", "snapshot") or not n.compiled_code:
                continue
            self.progress("dbt", 5 + int(25 * i / total), f"dbt model {n.name}")
            ql = lineage_for_sql(n.compiled_code, self.schema, n.database, n.schema,
                                 column_names=None)
            for w in ql.warnings:
                self.warn(f"dbt:{n.name}", w, "info" if "could not fully resolve" in w else "warning")
            rel = n.relation
            out_cols: dict[str, str] = {}
            for cl in ql.columns:
                nid = f"dbt:{uid}.{cl.name}"
                existing = self.g.node(nid)
                if existing is None:
                    self.g.add_node(Node(nid, "dbt_model_column", cl.name, parent=n.display, container=proj.name, file=n.file,
                                         data={"relation": rel, "resource_type": n.resource_type, "materialized": n.materialized,
                                               "data_type": "", "dbt_unique_id": uid, "inferred": True, "layer": "dbt",
                                               "model_description": n.description, "schema": n.schema.upper(), "database": n.database.upper()}))
                    self._register(rel, cl.name, nid, {"layer": "dbt", "name": n.display, "unique_id": uid, "resource_type": n.resource_type})
                node = self.g.node(nid)
                node.code = n.compiled_code
                node.code_lang = "sql"
                node.data.update({"transform": cl.transform, "expression": cl.expression})
                out_cols[cl.name] = node.data.get("data_type", "")
                for s in cl.sources:
                    up = self.upstream_col(s.relation, s.column)
                    if up:
                        reason = {"passthrough": "selected as-is", "renamed": f"renamed {s.column} → {cl.name}"}.get(
                            cl.transform, f"derived: {cl.expression[:160]}")
                        self.g.add_edge(up, nid, confidence="high" if cl.resolved else "medium", impact=BREAKS, reason=reason)
            for s in ql.filter_sources:
                up = self.upstream_col(s.relation, s.column)
                if not up:
                    continue
                for c in out_cols:
                    self.g.add_edge(up, f"dbt:{uid}.{c}", confidence="high", impact=MAY_CHANGE,
                                    reason="used in WHERE / JOIN / GROUP BY / QUALIFY")
            documented = {c for c in n.columns}
            missing = documented - set(out_cols) if out_cols else set()
            # dbt adds these meta columns to snapshots itself - not a lineage gap
            missing -= {"DBT_SCD_ID", "DBT_UPDATED_AT", "DBT_VALID_FROM", "DBT_VALID_TO", "DBT_IS_DELETED"}
            for c in sorted(missing):
                self.warn(f"dbt:{n.name}", f"column {c} is in catalog/schema.yml but not produced by the compiled SQL", "info")
            if out_cols:
                known = {c: (self.g.node(f"dbt:{uid}.{c}").data.get("data_type") or "VARCHAR") for c in out_cols}
                self._schema_put(rel, known)

    # ------------------------------------------------------------------ Snowflake views
    def scan_snowflake(self) -> None:
        objs = SnowflakeObjects()
        if self.cfg.view_dirs:
            o = load_view_files(self.cfg.view_dirs, self.cfg.default_database, self.cfg.default_schema)
            objs.views += o.views
            objs.warnings += o.warnings
        live = self.cfg.live_snowflake or {}
        if live.get("enabled"):
            self.progress("snowflake", 32, "reading Snowflake metadata (read-only)")
            try:
                o = load_live(live)
                objs.views += o.views
                objs.table_columns.update(o.table_columns)
                objs.warnings += o.warnings
            except Exception as ex:
                self.warn("snowflake", f"live connection failed: {ex}", "error")
        for w in objs.warnings:
            self.warn("snowflake", w)
        for rel, cols in objs.table_columns.items():
            if self.find_relation(rel) == rel:
                continue
            for c, t in cols:
                nid = f"sf:{rel}.{c.upper()}"
                self.g.add_node(Node(nid, "snowflake_table_column", c.upper(), parent=rel.split(".")[-1], container="Snowflake",
                                     data={"relation": rel, "data_type": t, "layer": "warehouse"}))
                self._register(rel, c.upper(), nid, {"layer": "table", "name": rel.split(".")[-1]})
            self._schema_put(rel, {c.upper(): t for c, t in cols})
        views = {v.relation: v for v in objs.views}
        dbt_rels = {k for k, m in self.rel_meta.items() if m.get("layer") == "dbt"}
        ts = TopologicalSorter()
        for rel, v in views.items():
            deps = [r for r in referenced_relations(v.query_sql, *rel.split(".")[:2]) if r in views and r != rel]
            ts.add(rel, *deps)
        try:
            order = list(ts.static_order())
        except CycleError:
            order = list(views)
        for i, rel in enumerate(order):
            v = views[rel]
            if rel in dbt_rels:
                self.warn("snowflake", f"{rel} is managed by dbt - using dbt lineage instead of the view script", "info")
                continue
            self.progress("snowflake", 32 + int(10 * i / max(1, len(order))), f"view {rel}")
            self._ingest_view(v)
        self.sources["views"] = [{"relation": v.relation, "file": v.file} for v in objs.views]

    def _ingest_view(self, v: ViewDef) -> None:
        db, sch, _ = (v.relation.split(".") + ["", "", ""])[:3]
        cols = [c.upper() for c in v.columns] if v.columns else None
        ql = lineage_for_sql(v.query_sql, self.schema, db, sch, column_names=cols)
        for w in ql.warnings:
            self.warn(f"view:{v.relation}", w, "info" if "could not fully resolve" in w else "warning")
        name = v.relation.split(".")[-1]
        out = {}
        for cl in ql.columns:
            nid = f"sf:{v.relation}.{cl.name}"
            self.g.add_node(Node(nid, "snowflake_view_column", cl.name, parent=name, container="Snowflake", file=v.file,
                                 code=v.full_sql, code_lang="sql", description=v.comment,
                                 data={"relation": v.relation, "transform": cl.transform, "expression": cl.expression,
                                       "layer": "view", "view_kind": v.kind}))
            self._register(v.relation, cl.name, nid, {"layer": "view", "name": name})
            out[cl.name] = "VARCHAR"
            for s in cl.sources:
                up = self.upstream_col(s.relation, s.column)
                if up:
                    reason = {"passthrough": "selected as-is", "renamed": f"renamed {s.column} → {cl.name}"}.get(
                        cl.transform, f"derived: {cl.expression[:160]}")
                    self.g.add_edge(up, nid, confidence="high" if cl.resolved else "medium", impact=BREAKS, reason=reason)
        for s in ql.filter_sources:
            up = self.upstream_col(s.relation, s.column)
            if up:
                for c in out:
                    self.g.add_edge(up, f"sf:{v.relation}.{c}", impact=MAY_CHANGE, reason="used in WHERE / JOIN / GROUP BY / QUALIFY")
        self._schema_put(v.relation, out)

    # ------------------------------------------------------------------ Power BI models
    def discover_powerbi(self) -> tuple[list[Path], list[Path]]:
        models = [p for p in self.cfg.semantic_models if p]
        reports = [p for p in self.cfg.reports if p] + [p for p in self.cfg.pbix if p]
        for d in self.cfg.search_dirs:
            if not d or not d.exists():
                self.warn("powerbi", f"search folder not found: {d}")
                continue
            for p in d.rglob("*.SemanticModel"):
                if p.is_dir() and p not in models:
                    models.append(p)
            for p in d.rglob("*.Dataset"):
                if p.is_dir() and p not in models:
                    models.append(p)
            for p in d.rglob("*.Report"):
                if p.is_dir() and p not in reports:
                    reports.append(p)
            for p in d.rglob("*.pbix"):
                if p not in reports:
                    reports.append(p)
        fab = self.cfg.fabric or {}
        if fab.get("enabled"):
            from .config import user_data_dir
            from .extractors.fabric import pull
            self.progress("powerbi", 42, "pulling definitions from Fabric (experimental)")
            cache = Path(fab["cache_dir"]) if fab.get("cache_dir") else user_data_dir() / "fabric-cache"
            fp = pull(fab, cache)
            for w in fp.warnings:
                self.warn("fabric", w)
            models += [p for p in fp.models if p not in models]
            reports += [p for p in fp.reports if p not in reports]
            for k, v in fp.report_model_map.items():
                self.cfg.report_model_map.setdefault(k, v)
        return models, reports

    def model_prefix(self, sm: SemanticModel) -> str:
        return f"pbi:{sm.name}"

    def col_ids(self, sm: SemanticModel, table: PTable, col: str) -> list[str]:
        pre = self.model_prefix(sm)
        if table.is_field_parameter:
            return [f"{pre}:fp:{table.name}"]
        if table.is_calc_group:
            return [f"{pre}:cg:{table.name}:{it.name}" for it in table.calc_items]
        for cname in table.columns:
            if cname.lower() == col.lower():
                return [f"{pre}:{table.name}[{cname}]"]
        return []

    def measure_id(self, sm: SemanticModel, table: str, measure: str) -> str:
        return f"{self.model_prefix(sm)}:measure:{table}[{measure}]"

    def resolve_dax(self, sm: SemanticModel, expr: str, home: str | None, where: str,
                    extra_measures: dict[str, str] | None = None) -> list[tuple[str, str, str]]:
        """-> [(node_id, reason, confidence)]"""
        out: list[tuple[str, str, str]] = []
        refs = daxmod.references(expr)
        extra = {k.lower(): v for k, v in (extra_measures or {}).items()}
        for t, c in refs.columns:
            tbl = sm.table(t)
            if tbl is None:
                self.warn(where, f"DAX reference to unknown table '{t}'[{c}]")
                continue
            ids = self.col_ids(sm, tbl, c)
            if ids and not (tbl.is_field_parameter or tbl.is_calc_group):
                out += [(i, f"references {tbl.name}[{c}]", "high") for i in ids]
                continue
            if ids:
                out += [(i, f"references {tbl.name}[{c}]", "high") for i in ids]
                continue
            hit = next((m for m in tbl.measures if m.lower() == c.lower()), None)
            if hit:
                out.append((self.measure_id(sm, tbl.name, hit), f"references [{hit}]", "high"))
            elif c.lower() in extra:
                out.append((extra[c.lower()], f"references [{c}]", "high"))
            else:
                self.warn(where, f"DAX reference '{t}'[{c}] could not be resolved")
        for b in refs.bare:
            if b.lower() in extra:
                out.append((extra[b.lower()], f"references [{b}]", "high"))
                continue
            fm = sm.find_measure(b)
            if fm:
                out.append((self.measure_id(sm, fm[0].name, fm[1].name), f"references [{fm[1].name}]", "high"))
                continue
            ht = sm.table(home) if home else None
            if ht is not None:
                ids = self.col_ids(sm, ht, b)
                if ids:
                    out += [(i, f"references [{b}] (column of {ht.name})", "high") for i in ids]
                    continue
            cands = [(t, cn) for t in sm.tables.values() for cn in t.columns if cn.lower() == b.lower()]
            if len(cands) == 1:
                out += [(i, f"references [{b}] (resolved to {cands[0][0].name})", "medium") for i in self.col_ids(sm, cands[0][0], cands[0][1])]
            else:
                self.warn(where, f"DAX reference [{b}] could not be resolved")
        return out

    def scan_models(self, model_paths: list[Path]) -> None:
        for i, p in enumerate(model_paths):
            self.progress("powerbi", 45 + int(20 * i / max(1, len(model_paths))), f"semantic model {p.name}")
            try:
                sm = load_semantic_model(p)
            except Exception as ex:
                self.warn("powerbi", f"could not load semantic model {p}: {ex}", "error")
                continue
            for w in sm.warnings:
                self.warn(f"model:{sm.name}", w)
            self.models[sm.name] = sm
            self.sources["semantic_models"].append({"name": sm.name, "path": str(p), "format": sm.format, "tables": len(sm.tables)})
            self._ingest_model(sm)

    def _ingest_model(self, sm: SemanticModel) -> None:
        pre = self.model_prefix(sm)
        g = self.g
        g.add_node(Node(pre, "semantic_model", sm.name, container=sm.name, file=sm.path,
                        data={"format": sm.format, "tables": len(sm.tables), "roles": len(sm.roles)}))
        params = sm.parameters
        # 1) nodes
        for t in sm.tables.values():
            if t.is_field_parameter:
                part = next(p for p in t.partitions if p.kind == "calculated")
                g.add_node(Node(f"{pre}:fp:{t.name}", "field_parameter", t.name, parent=t.name, container=sm.name, file=t.file,
                                code=part.expression, code_lang="dax", description=t.description, data={"table": t.name}))
                continue
            if t.is_calc_group:
                for it in t.calc_items:
                    g.add_node(Node(f"{pre}:cg:{t.name}:{it.name}", "calc_group_item", it.name, parent=t.name, container=sm.name,
                                    file=t.file, code=it.expression, code_lang="dax",
                                    data={"table": t.name, "format_string": it.format_string_expression}))
                continue
            for c in t.columns.values():
                ctype = "calc_column" if c.kind == "calculated" else "pbi_model_column"
                g.add_node(Node(f"{pre}:{t.name}[{c.name}]", ctype, c.name, parent=t.name, container=sm.name, file=t.file,
                                code=c.expression if c.expression else "", code_lang="dax" if c.expression else "",
                                description=c.description,
                                data={"table": t.name, "source_column": c.source_column, "data_type": c.data_type,
                                      "hidden": c.is_hidden}))
            for m in t.measures.values():
                g.add_node(Node(self.measure_id(sm, t.name, m.name), "measure", m.name, parent=t.name, container=sm.name,
                                file=t.file, code=m.expression, code_lang="dax", description=m.description,
                                data={"table": t.name, "display_folder": m.display_folder, "format_string": m.format_string}))
        for r in sm.roles.values():
            code = "\n\n".join(f"-- table permission on '{t}'\n{e}" for t, e in r.filters.items())
            g.add_node(Node(f"{pre}:rls:{r.name}", "rls_role", r.name, parent="Roles", container=sm.name, file=r.file,
                            code=code, code_lang="dax", data={"filters": r.filters}))
        # 2) source mapping for data columns
        for t in sm.tables.values():
            if t.is_field_parameter or t.is_calc_group:
                continue
            mparts = [p for p in t.partitions if p.kind in ("m", "")]
            if not mparts:
                cparts = [p for p in t.partitions if p.kind == "calculated"]
                for p in cparts:  # calculated table: all columns depend on the table expression
                    deps = self.resolve_dax(sm, p.expression, t.name, f"model:{sm.name}/{t.name}")
                    for c in t.columns.values():
                        if c.kind == "calculated":
                            continue
                        for nid, reason, conf in deps:
                            g.add_edge(nid, f"{pre}:{t.name}[{c.name}]", confidence=min_conf(conf, "medium"), impact=BREAKS,
                                       reason=f"calculated table: {reason}")
                continue
            part = mparts[0]
            src = parse_m(part.expression, params)
            for w in src.warnings:
                self.warn(f"model:{sm.name}/{t.name}", w)
            for c in t.columns.values():
                node = g.node(f"{pre}:{t.name}[{c.name}]")
                node.data["storage_mode"] = part.mode or "import"
                if c.kind == "calculated":
                    continue
                node.code = part.expression
                node.code_lang = "m"
                self._map_column(sm, t, c, src, node)
        # 3) DAX dependencies
        for t in sm.tables.values():
            for c in t.columns.values():
                if c.kind == "calculated" and c.expression:
                    nid = f"{pre}:{t.name}[{c.name}]"
                    for dep, reason, conf in self.resolve_dax(sm, c.expression, t.name, f"model:{sm.name}/{t.name}[{c.name}]"):
                        g.add_edge(dep, nid, confidence=conf, impact=BREAKS, reason=reason)
                if c.sort_by:
                    sb = self.col_ids(sm, t, c.sort_by)
                    for s in sb:
                        g.add_edge(s, f"{pre}:{t.name}[{c.name}]", impact=MAY_CHANGE, reason=f"sort by column {c.sort_by}")
            for m in t.measures.values():
                mid = self.measure_id(sm, t.name, m.name)
                for dep, reason, conf in self.resolve_dax(sm, m.expression, t.name, f"model:{sm.name}/[{m.name}]"):
                    g.add_edge(dep, mid, confidence=conf, impact=BREAKS, reason=reason)
            if t.is_calc_group:
                for it in t.calc_items:
                    iid = f"{pre}:cg:{t.name}:{it.name}"
                    for dep, reason, conf in self.resolve_dax(sm, it.expression + "\n" + it.format_string_expression, t.name, f"model:{sm.name}/{t.name}/{it.name}"):
                        g.add_edge(dep, iid, confidence=conf, impact=BREAKS, reason=reason)
            if t.is_field_parameter:
                part = next(p for p in t.partitions if p.kind == "calculated")
                fid = f"{pre}:fp:{t.name}"
                for dep, reason, conf in self.resolve_dax(sm, part.expression, t.name, f"model:{sm.name}/{t.name}"):
                    if dep != fid:
                        g.add_edge(dep, fid, confidence=conf, impact=BREAKS, reason=f"field parameter option: {reason.replace('references ', '')}")
        for r in sm.roles.values():
            rid = f"{pre}:rls:{r.name}"
            for table, expr in r.filters.items():
                for dep, reason, conf in self.resolve_dax(sm, expr, table, f"model:{sm.name}/role {r.name}"):
                    g.add_edge(dep, rid, confidence=conf, impact=BREAKS, reason=f"RLS filter on '{table}': {reason}")
        for rel in sm.relationships:
            ft, tt = sm.table(rel.from_table), sm.table(rel.to_table)
            if not ft or not tt:
                continue
            for a in self.col_ids(sm, ft, rel.from_column):
                for b in self.col_ids(sm, tt, rel.to_column):
                    g.add_edge(a, b, kind="relationship", reason=f"relationship {'active' if rel.active else 'inactive'}")
                    na, nb = g.node(a), g.node(b)
                    na.data.setdefault("relationships", []).append(f"{rel.to_table}[{rel.to_column}]" + ("" if rel.active else " (inactive)"))
                    nb.data.setdefault("relationships", []).append(f"{rel.from_table}[{rel.from_column}]" + ("" if rel.active else " (inactive)"))
        # 4) optional INFO.CALCDEPENDENCY import
        csv_path = self.cfg.calcdependency_csv.get(sm.name)
        if csv_path:
            self._apply_calcdependency(sm, csv_path)
        # 5) model contains tables (structure)
        for n in list(g.nodes()):
            if n.container == sm.name and n.id != pre and n.type in ("pbi_model_column", "calc_column", "measure", "rls_role", "calc_group_item", "field_parameter"):
                g.add_edge(pre, n.id, kind="contains")

    def _map_column(self, sm, t: PTable, c, src, node: Node) -> None:
        g = self.g
        where = f"model:{sm.name}/{t.name}[{c.name}]"
        source_name = c.source_column or c.name
        node.data["m_connector"] = src.connector
        if src.native_sql:
            ql = lineage_for_sql(src.native_sql, self.schema, src.database.upper(), src.schema.upper())
            for w in ql.warnings:
                self.warn(where, f"native query: {w}", "info")
            names = [cl.name for cl in ql.columns]
            upstream_name, how = src.source_name_for(source_name)
            m = best_match(upstream_name or source_name, names, self.rules)
            node.data["upstream_relation"] = ", ".join(ql.relations)
            if not m:
                node.data["unmatched"] = True
                self.warn(where, f"sourceColumn '{source_name}' not found in native query output ({', '.join(names)})")
                return
            cl = ql.column(m.candidate)
            node.data["match_method"] = f"native query, {m.method}"
            node.data["upstream_column"] = m.candidate
            for s in cl.sources:
                up = self.upstream_col(s.relation, s.column)
                if up:
                    g.add_edge(up, node.id, confidence=min_conf(m.confidence, "high" if cl.resolved else "medium"), impact=BREAKS,
                               reason=f"Value.NativeQuery: {cl.expression or cl.name} → {source_name}")
            for s in ql.filter_sources:
                up = self.upstream_col(s.relation, s.column)
                if up:
                    g.add_edge(up, node.id, impact=MAY_CHANGE, reason="used in native query WHERE / JOIN / GROUP BY")
            return
        if src.connector not in ("snowflake", "unknown") and not src.object:
            node.data["unmatched"] = True
            return
        if not src.object:
            node.data["unmatched"] = True
            self.warn(where, "no Snowflake object found in the partition's M expression")
            return
        rel_q = ".".join(p for p in (src.database, src.schema, src.object) if p).upper()
        rel = self.find_relation(rel_q)
        node.data["upstream_relation"] = rel or rel_q
        if not rel:
            node.data["unmatched"] = True
            self.warn(where, f"Power Query source {rel_q} is not in the scanned dbt project / views")
            return
        upstream_name, how = src.source_name_for(source_name)
        if upstream_name is None:
            deps = src.added.get(source_name, [])
            node.data["match_method"] = "Power Query added column"
            for d in deps:
                un, _ = src.source_name_for(d)
                mm = best_match(un or d, list(self.rel_index[rel]), self.rules)
                if mm:
                    g.add_edge(self.rel_index[rel][mm.candidate], node.id, confidence=min_conf(mm.confidence, "medium"),
                               impact=BREAKS, reason=f"Table.AddColumn '{source_name}' uses [{d}]")
            return
        cands = list(self.rel_index[rel])
        m = best_match(upstream_name, cands, self.rules)
        if m is None:
            node.data["unmatched"] = True
            self.warn(where, f"no column matching '{upstream_name}' in {rel}", "warning")
            return
        conf = m.confidence
        method = m.method
        if src.name_transform == "custom" and m.method in ("exact", "case-insensitive"):
            conf, method = "medium", m.method + " after Table.TransformColumnNames"
        node.data["match_method"] = method + (f" ({how})" if how != "direct" else "")
        node.data["upstream_column"] = m.candidate
        reason = f"sourceColumn '{source_name}'"
        if how != "direct":
            reason += f" ← Table.RenameColumns from {upstream_name}"
        reason += f" → {rel.split('.')[-1]}.{m.candidate} ({method})"
        g.add_edge(self.rel_index[rel][m.candidate], node.id, confidence=conf, impact=BREAKS, reason=reason)

    def _apply_calcdependency(self, sm: SemanticModel, path: Path) -> None:
        try:
            rows = daxmod.load_calcdependency_csv(path)
        except Exception as ex:
            self.warn(f"model:{sm.name}", f"could not read INFO.CALCDEPENDENCY csv {path}: {ex}")
            return
        pre = self.model_prefix(sm)

        def nid(kind: str, table: str, obj: str) -> list[str]:
            k = kind.upper()
            tbl = sm.table(table) if table else None
            if k == "MEASURE":
                fm = sm.find_measure(obj)
                return [self.measure_id(sm, fm[0].name, fm[1].name)] if fm else []
            if k in ("COLUMN", "CALC_COLUMN", "CALCULATED_COLUMN") and tbl:
                return self.col_ids(sm, tbl, obj)
            if k in ("CALC_ITEM", "CALCULATION_ITEM") and tbl:
                return [f"{pre}:cg:{tbl.name}:{obj}"]
            if k in ("ROWS_ALLOWED", "ROW_LEVEL_SECURITY"):
                return [f"{pre}:rls:{obj}"] if f"{pre}:rls:{obj}" in self.g else []
            return []

        n = 0
        for r in rows:
            for a in nid(r.ref_type, r.ref_table, r.ref_object):
                for b in nid(r.object_type, r.table, r.object):
                    self.g.add_edge(a, b, confidence="high", impact=BREAKS, reason="INFO.CALCDEPENDENCY")
                    n += 1
        self.warn(f"model:{sm.name}", f"imported {n} dependencies from INFO.CALCDEPENDENCY", "info")

    # ------------------------------------------------------------------ reports
    def resolve_report_model(self, rep: Report) -> SemanticModel | None:
        override = self.cfg.report_model_map.get(rep.name)
        target = override or rep.model_ref
        if not target:
            return None
        if target in self.models:
            return self.models[target]
        m = best_match(target, list(self.models), self.rules)
        if m:
            return self.models[m.candidate]
        return None

    def scan_reports(self, report_paths: list[Path]) -> None:
        for i, p in enumerate(report_paths):
            self.progress("reports", 68 + int(25 * i / max(1, len(report_paths))), f"report {p.name}")
            try:
                rep = load_report(p)
            except Exception as ex:
                self.warn("reports", f"could not load report {p}: {ex}", "error")
                continue
            for w in rep.warnings:
                self.warn(f"report:{rep.name}", w)
            self._ingest_report(rep)

    def _ingest_report(self, rep: Report) -> None:
        g = self.g
        sm = self.resolve_report_model(rep)
        rid = f"rpt:{rep.name}"
        visuals_total = sum(len(p.visuals) for p in rep.pages)
        g.add_node(Node(rid, "report", rep.name, container=rep.name, file=rep.path,
                        data={"format": rep.format, "model": sm.name if sm else rep.model_ref, "model_ref_kind": rep.model_ref_kind,
                              "pages": len(rep.pages), "visuals": visuals_total, "model_resolved": bool(sm),
                              "filters": [f"{f.entity}[{f.property}]" for f in rep.filters]}))
        self.sources["reports"].append({"name": rep.name, "path": rep.path, "format": rep.format, "model": sm.name if sm else None,
                                        "pages": len(rep.pages), "visuals": visuals_total})
        if sm is None:
            self.warn(f"report:{rep.name}", f"semantic model '{rep.model_ref or '?'}' not found - add it to the scan or to powerbi.report_model_map", "warning")
        else:
            g.add_edge(self.model_prefix(sm), rid, kind="dataset", reason="report bound to semantic model")
        ext: dict[str, str] = {}
        if sm:
            for em in rep.extension_measures:
                mid = f"rpt:{rep.name}:measure:{em.entity}[{em.name}]"
                g.add_node(Node(mid, "measure", em.name, parent=em.entity, container=rep.name, file=str(Path(rep.path) / "definition" / "reportExtensions.json"),
                                code=em.expression, code_lang="dax", description="Report-level measure (reportExtensions.json)",
                                data={"table": em.entity, "report_measure": True, "model": sm.name}))
                ext[em.name] = mid
            for em in rep.extension_measures:
                mid = ext[em.name]
                for dep, reason, conf in self.resolve_dax(sm, em.expression, em.entity, f"report:{rep.name}/[{em.name}]", ext):
                    g.add_edge(dep, mid, confidence=conf, impact=BREAKS, reason=reason)
        for f in rep.filters:
            self._link_field(sm, ext, f, rid, rep.name, "report filter")
        for page in rep.pages:
            pid = f"rpt:{rep.name}:page:{page.id}"
            g.add_node(Node(pid, "page", page.name, parent=rep.name, container=rep.name, file=page.file,
                            data={"ordinal": page.ordinal, "visuals": len(page.visuals), "filters": [f"{f.entity}[{f.property}]" for f in page.filters]}))
            g.add_edge(rid, pid, kind="contains")
            for f in page.filters:
                self._link_field(sm, ext, f, pid, rep.name, "page filter")
            for v in page.visuals:
                vid = f"rpt:{rep.name}:visual:{page.id}:{v.id}"
                code = ""
                try:
                    if v.file and v.file.endswith("visual.json"):
                        code = Path(v.file).read_text(encoding="utf-8")[:20000]
                except OSError:
                    pass
                g.add_node(Node(vid, "visual", v.name, parent=page.name, container=rep.name, file=v.file, code=code,
                                code_lang="json" if code else "",
                                data={"visual_type": v.visual_type, "page": page.name, "page_id": pid, "report": rep.name,
                                      "fields": [{"entity": f.entity, "property": f.property, "kind": f.kind, "usage": f.usage,
                                                  "aggregation": f.aggregation, "hierarchy": f.hierarchy} for f in v.fields],
                                      "position": v.position}))
                g.add_edge(pid, vid, kind="contains")
                unresolved = []
                for f in v.fields:
                    if not self._link_field(sm, ext, f, vid, rep.name, f.usage):
                        unresolved.append(f"{f.entity}[{f.property}]")
                if unresolved:
                    g.node(vid).data["unresolved_fields"] = unresolved

    def _link_field(self, sm: SemanticModel | None, ext: dict[str, str], f: FieldRef, target: str, report: str, usage: str) -> bool:
        if sm is None:
            return False
        g = self.g
        label = {"filter": "visual filter", "sort": "sort", "conditional formatting": "conditional formatting"}.get(usage, usage)
        targets: list[str] = []
        if f.kind == "measure":
            if f.property in ext:
                targets = [ext[f.property]]
            else:
                tbl = sm.table(f.entity)
                hit = next((m for m in (tbl.measures if tbl else {}) if m.lower() == f.property.lower()), None)
                if hit:
                    targets = [self.measure_id(sm, tbl.name, hit)]
                else:
                    fm = sm.find_measure(f.property)
                    if fm:
                        targets = [self.measure_id(sm, fm[0].name, fm[1].name)]
        else:
            tbl = sm.table(f.entity)
            if tbl is not None:
                col = f.property
                if f.kind == "hierarchy_level":
                    levels = tbl.hierarchies.get(f.hierarchy) or {}
                    col = levels.get(f.property, f.property)
                targets = self.col_ids(sm, tbl, col)
                if not targets:  # Table[Measure] used as column in filters
                    hit = next((m for m in tbl.measures if m.lower() == col.lower()), None)
                    if hit:
                        targets = [self.measure_id(sm, tbl.name, hit)]
        if not targets:
            self.warn(f"report:{report}", f"field {f.entity}[{f.property}] ({usage}) not found in model {sm.name}")
            return False
        reason = label
        if f.aggregation:
            reason = f"{label} (implicit {f.aggregation})"
        if f.kind == "hierarchy_level":
            reason = f"{label} (hierarchy {f.hierarchy} › {f.property})"
        for t in targets:
            g.add_edge(t, target, confidence="high", impact=BREAKS, reason=reason)
        return True

    # ------------------------------------------------------------------ run
    def run(self) -> ScanResult:
        started = time.time()
        self.progress("start", 1, "starting scan")
        self.scan_dbt()
        self.progress("snowflake", 31, "Snowflake views")
        self.scan_snowflake()
        model_paths, report_paths = self.discover_powerbi()
        self.progress("powerbi", 44, f"{len(model_paths)} semantic model(s)")
        self.scan_models(model_paths)
        self.progress("reports", 67, f"{len(report_paths)} report(s)")
        self.scan_reports(report_paths)
        self.progress("finalise", 96, "computing statistics")
        stats = graph_stats(self.g)
        stats["warnings"] = len([w for w in self.warnings if w["level"] != "info"])
        res = ScanResult(self.g, self.warnings, stats, started, time.time(), self.sources)
        self.progress("done", 100, f"scan complete: {stats['nodes']} nodes, {stats['edges']} edges")
        return res


def graph_stats(g: LineageGraph) -> dict:
    by_type: dict[str, int] = {}
    for n in g.nodes():
        by_type[n.type] = by_type.get(n.type, 0) + 1
    edges_by_kind: dict[str, int] = {}
    conf: dict[str, int] = {}
    for _, _, d in g.edges():
        edges_by_kind[d["kind"]] = edges_by_kind.get(d["kind"], 0) + 1
        if d["kind"] == "flow":
            conf[d["confidence"]] = conf.get(d["confidence"], 0) + 1
    return {"nodes": len(g), "edges": g.g.number_of_edges(), "by_type": by_type, "edges_by_kind": edges_by_kind,
            "flow_confidence": conf, "version": __version__}


def build(cfg: Config, progress: Progress | None = None) -> ScanResult:
    return Builder(cfg, progress).run()
