"""Snowflake view definitions: from a folder of CREATE VIEW scripts or a read-only live connection."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..sqllineage import view_name_and_columns


@dataclass
class ViewDef:
    relation: str                        # DB.SCHEMA.NAME (upper)
    query_sql: str
    columns: list[str] | None = None     # explicit column list if any
    file: str = ""
    kind: str = "view"
    full_sql: str = ""
    comment: str = ""


@dataclass
class SnowflakeObjects:
    views: list[ViewDef] = field(default_factory=list)
    table_columns: dict[str, list[tuple[str, str]]] = field(default_factory=dict)   # relation -> [(col, type)]
    warnings: list[str] = field(default_factory=list)


def split_statements(sql: str) -> list[str]:
    """Split a script on semicolons outside strings/comments."""
    out, cur, i, n = [], [], 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'" and (j + 1 >= n or sql[j + 1] != "'"):
                    break
                j += 2 if sql[j] == "'" else 1
            cur.append(sql[i:j + 1])
            i = j + 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            cur.append(sql[i:j])
            i = j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            cur.append(sql[i:j])
            i = j
            continue
        if c == ";":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip():
        out.append("".join(cur))
    return [s for s in out if s.strip()]


_CREATE_VIEW = re.compile(r"\bcreate\s+(?:or\s+replace\s+)?(?:secure\s+)?(?:recursive\s+)?(?:materialized\s+)?view\b", re.IGNORECASE)


def load_view_files(dirs: list[str | Path], default_db: str = "", default_schema: str = "") -> SnowflakeObjects:
    res = SnowflakeObjects()
    for d in dirs:
        d = Path(d)
        if not d.exists():
            res.warnings.append(f"view folder not found: {d}")
            continue
        files = [d] if d.is_file() else sorted(d.rglob("*.sql"))
        for f in files:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
            for stmt in split_statements(text):
                if not _CREATE_VIEW.search(stmt):
                    continue
                try:
                    rel, cols, query, kind = view_name_and_columns(stmt, default_db, default_schema)
                except Exception as ex:
                    res.warnings.append(f"{f.name}: could not parse view ({ex})")
                    continue
                m = re.search(r"\bcomment\s*=\s*'((?:[^']|'')*)'", stmt, re.IGNORECASE)
                res.views.append(ViewDef(rel, query, cols, str(f), kind, stmt.strip(), m.group(1).replace("''", "'") if m else ""))
    return res


def load_live(cfg: dict) -> SnowflakeObjects:
    """Read-only metadata pull. Credentials come from environment variables only:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (or SNOWFLAKE_AUTHENTICATOR=externalbrowser /
    SNOWFLAKE_PRIVATE_KEY_PATH), SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE.
    cfg: {"databases": [...], "schemas": [...optional...]}
    """
    res = SnowflakeObjects()
    try:
        import snowflake.connector  # type: ignore
    except ImportError:
        res.warnings.append("snowflake-connector-python is not installed: pip install 'lineagelens[snowflake]'")
        return res
    params = {k: os.environ[v] for k, v in {
        "account": "SNOWFLAKE_ACCOUNT", "user": "SNOWFLAKE_USER", "password": "SNOWFLAKE_PASSWORD",
        "role": "SNOWFLAKE_ROLE", "warehouse": "SNOWFLAKE_WAREHOUSE", "authenticator": "SNOWFLAKE_AUTHENTICATOR",
        "private_key_file": "SNOWFLAKE_PRIVATE_KEY_PATH"}.items() if os.environ.get(v)}
    if "account" not in params or "user" not in params:
        res.warnings.append("live Snowflake enabled but SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER env vars are not set")
        return res
    params["session_parameters"] = {"QUERY_TAG": "lineagelens-readonly-metadata"}
    conn = snowflake.connector.connect(**params)
    try:
        cur = conn.cursor()
        schemas = [s.upper() for s in cfg.get("schemas") or []]
        for db in cfg.get("databases") or []:
            db = db.upper()
            where = f" AND TABLE_SCHEMA IN ({', '.join(repr(s) for s in schemas)})" if schemas else " AND TABLE_SCHEMA <> 'INFORMATION_SCHEMA'"
            cur.execute(f'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM "{db}".INFORMATION_SCHEMA.COLUMNS WHERE 1=1{where} ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION')
            for sch, tbl, col, typ in cur.fetchall():
                res.table_columns.setdefault(f"{db}.{sch}.{tbl}", []).append((col, typ))
            cur.execute(f'SELECT TABLE_SCHEMA, TABLE_NAME FROM "{db}".INFORMATION_SCHEMA.VIEWS WHERE 1=1{where}')
            for sch, name in cur.fetchall():
                try:
                    cur.execute("SELECT GET_DDL('VIEW', %s, TRUE)", (f'"{db}"."{sch}"."{name}"',))
                    ddl = cur.fetchone()[0]
                    rel, cols, query, kind = view_name_and_columns(ddl, db, sch)
                    res.views.append(ViewDef(rel, query, cols, f"snowflake://{db}.{sch}.{name}", kind, ddl))
                except Exception as ex:  # pragma: no cover - needs live account
                    res.warnings.append(f"GET_DDL failed for {db}.{sch}.{name}: {ex}")
    finally:
        conn.close()
    return res
