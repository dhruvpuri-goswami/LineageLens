"""dbt artifacts: manifest.json (+ catalog.json, schema.yml descriptions)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class DbtColumn:
    name: str            # upper-case
    data_type: str = ""
    description: str = ""


@dataclass
class DbtNode:
    unique_id: str
    resource_type: str   # source | model | seed | snapshot
    name: str
    database: str
    schema: str
    alias: str
    columns: dict[str, DbtColumn] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    compiled_code: str = ""
    raw_code: str = ""
    file: str = ""
    description: str = ""
    materialized: str = ""
    package: str = ""
    source_name: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def relation(self) -> str:
        if self.materialized == "ephemeral":
            return f"__DBT__CTE__{self.name.upper()}"
        return ".".join(p.upper() for p in (self.database, self.schema, self.alias) if p)

    @property
    def display(self) -> str:
        if self.resource_type == "source":
            return f"{self.source_name}.{self.name}"
        return self.name


@dataclass
class DbtProject:
    name: str
    manifest_path: str
    nodes: dict[str, DbtNode] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    has_catalog: bool = False

    def by_relation(self) -> dict[str, DbtNode]:
        return {n.relation: n for n in self.nodes.values()}


RESOURCE_TYPES = {"model", "seed", "snapshot"}


def _yaml_descriptions(project_dir: Path) -> dict[str, dict]:
    """name -> {"description":..., "columns": {COL: desc}} from schema.yml files (models/sources)."""
    out: dict[str, dict] = {}
    if not project_dir or not project_dir.exists():
        return out
    for f in list(project_dir.rglob("*.yml")) + list(project_dir.rglob("*.yaml")):
        if any(part in ("target", "dbt_packages", "logs", "node_modules") for part in f.parts):
            continue
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for kind in ("models", "seeds", "snapshots"):
            for m in doc.get(kind) or []:
                if isinstance(m, dict) and m.get("name"):
                    out[m["name"]] = {"description": m.get("description", ""),
                                      "columns": {str(c.get("name", "")).upper(): c.get("description", "") for c in m.get("columns") or [] if isinstance(c, dict)}}
        for s in doc.get("sources") or []:
            for t in (s or {}).get("tables") or []:
                if isinstance(t, dict) and t.get("name"):
                    out[f"source:{s.get('name')}.{t['name']}"] = {"description": t.get("description", ""),
                                                                   "columns": {str(c.get("name", "")).upper(): c.get("description", "") for c in t.get("columns") or [] if isinstance(c, dict)}}
    return out


def load_dbt(manifest: str | Path, catalog: str | Path | None = None, project_dir: str | Path | None = None) -> DbtProject:
    manifest = Path(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    meta = data.get("metadata", {})
    proj = DbtProject(meta.get("project_name") or (Path(project_dir).name if project_dir else manifest.parent.name), str(manifest))
    version = meta.get("dbt_schema_version", "")
    if version and not any(f"/v{v}" in version for v in range(7, 14)):
        proj.warnings.append(f"untested manifest schema version {version}")

    def add(uid: str, n: dict, rtype: str) -> None:
        dn = DbtNode(
            unique_id=uid, resource_type=rtype, name=n.get("name", ""),
            database=n.get("database") or "", schema=n.get("schema") or "",
            alias=(n.get("identifier") if rtype == "source" else n.get("alias")) or n.get("name", ""),
            depends_on=list((n.get("depends_on") or {}).get("nodes", [])),
            compiled_code=n.get("compiled_code") or n.get("compiled_sql") or "",
            raw_code=n.get("raw_code") or n.get("raw_sql") or "",
            file=n.get("original_file_path") or n.get("path") or "",
            description=n.get("description") or "",
            materialized=(n.get("config") or {}).get("materialized", "") if rtype != "source" else "source",
            package=n.get("package_name", ""), source_name=n.get("source_name", ""), tags=n.get("tags") or [],
        )
        for cname, c in (n.get("columns") or {}).items():
            up = (c.get("name") or cname).upper()
            dn.columns[up] = DbtColumn(up, c.get("data_type") or "", c.get("description") or "")
        proj.nodes[uid] = dn

    for uid, n in (data.get("nodes") or {}).items():
        if n.get("resource_type") in RESOURCE_TYPES:
            add(uid, n, n["resource_type"])
    for uid, n in (data.get("sources") or {}).items():
        add(uid, n, "source")

    if catalog and Path(catalog).exists():
        proj.has_catalog = True
        cat = json.loads(Path(catalog).read_text(encoding="utf-8"))
        for section in ("nodes", "sources"):
            for uid, cn in (cat.get(section) or {}).items():
                node = proj.nodes.get(uid)
                if not node:
                    continue
                cols = sorted((cn.get("columns") or {}).values(), key=lambda c: c.get("index", 0))
                merged: dict[str, DbtColumn] = {}
                for c in cols:
                    up = c["name"].upper()
                    prev = node.columns.get(up)
                    merged[up] = DbtColumn(up, c.get("type") or (prev.data_type if prev else ""), prev.description if prev else (c.get("comment") or ""))
                for up, prev in node.columns.items():  # documented but not in warehouse
                    if up not in merged:
                        merged[up] = prev
                node.columns = merged
                if not node.description:
                    node.description = (cn.get("metadata") or {}).get("comment") or ""
    else:
        proj.warnings.append("catalog.json not provided - column lists come from schema.yml / SQL parsing (run `dbt docs generate` for full coverage)")

    if project_dir:
        ydesc = _yaml_descriptions(Path(project_dir))
        for node in proj.nodes.values():
            key = f"source:{node.source_name}.{node.name}" if node.resource_type == "source" else node.name
            y = ydesc.get(key)
            if not y:
                continue
            if not node.description and y["description"]:
                node.description = y["description"]
            for up, desc in y["columns"].items():
                if up in node.columns:
                    if not node.columns[up].description and desc:
                        node.columns[up].description = desc
                elif not proj.has_catalog:
                    node.columns[up] = DbtColumn(up, "", desc)
    missing = [n.name for n in proj.nodes.values() if n.resource_type in ("model", "snapshot") and not n.compiled_code]
    if missing:
        proj.warnings.append(f"{len(missing)} model(s) have no compiled SQL (run `dbt compile`): {', '.join(missing[:5])}")
    return proj
