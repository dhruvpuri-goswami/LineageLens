"""SQLite persistence of the lineage graph and scan metadata."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .graph import LineageGraph, Node

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT, parent TEXT, container TEXT,
  file TEXT, code TEXT, code_lang TEXT, description TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT, confidence TEXT, impact TEXT, reason TEXT,
  PRIMARY KEY (src, dst)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS ix_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS ix_edges_dst ON edges(dst);
"""


def save(path: str | Path, graph: LineageGraph, meta: dict | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        con.executemany(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(n.id, n.type, n.name, n.parent, n.container, n.file, n.code, n.code_lang, n.description, json.dumps(n.data, default=str))
             for n in graph.nodes()])
        con.executemany(
            "INSERT INTO edges VALUES (?,?,?,?,?,?)",
            [(s, t, d["kind"], d["confidence"], d["impact"], d.get("reason", "")) for s, t, d in graph.edges()])
        m = dict(meta or {})
        m.setdefault("saved_at", time.time())
        con.executemany("INSERT INTO meta VALUES (?,?)", [(k, json.dumps(v, default=str)) for k, v in m.items()])
        con.commit()
    finally:
        con.close()
    tmp.replace(path)
    return path


def load(path: str | Path) -> tuple[LineageGraph, dict]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    con = sqlite3.connect(path)
    try:
        g = LineageGraph()
        for row in con.execute("SELECT id,type,name,parent,container,file,code,code_lang,description,data FROM nodes"):
            g.add_node(Node(row[0], row[1], row[2] or "", row[3] or "", row[4] or "", row[5] or "", row[6] or "", row[7] or "",
                            row[8] or "", json.loads(row[9] or "{}")))
        for s, t, kind, conf, imp, reason in con.execute("SELECT src,dst,kind,confidence,impact,reason FROM edges"):
            g.add_edge(s, t, kind=kind, confidence=conf, impact=imp, reason=reason or "")
        meta = {k: json.loads(v) for k, v in con.execute("SELECT key,value FROM meta")}
    finally:
        con.close()
    return g, meta
