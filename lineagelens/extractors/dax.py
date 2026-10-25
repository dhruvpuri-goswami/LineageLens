"""Small, dependency-free DAX tokenizer that extracts object references.

Recognises:  'Quoted Table'[Column], Table[Column], [Measure or Column], bare table
names (COUNTROWS(Sales)), strings, // -- /* */ comments and VAR names.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

KEYWORDS = {
    "VAR", "RETURN", "TRUE", "FALSE", "IN", "NOT", "AND", "OR", "DEFINE", "EVALUATE",
    "MEASURE", "ORDER", "BY", "ASC", "DESC", "START", "AT", "COLUMN", "TABLE", "BLANK",
}


@dataclass
class DaxRefs:
    columns: list[tuple[str, str]] = field(default_factory=list)   # (table, column)
    bare: list[str] = field(default_factory=list)                   # [Name] without table
    tables: list[str] = field(default_factory=list)                 # unbracketed identifiers / 'quoted' tables
    variables: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)

    def add_unique(self, attr: str, value) -> None:
        lst = getattr(self, attr)
        if value not in lst:
            lst.append(value)


def _read_bracket(s: str, i: int) -> tuple[str, int]:
    # s[i] == '['
    j = i + 1
    out = []
    while j < len(s):
        if s[j] == "]":
            if j + 1 < len(s) and s[j + 1] == "]":
                out.append("]")
                j += 2
                continue
            return "".join(out), j + 1
        out.append(s[j])
        j += 1
    return "".join(out), j


def _read_quoted(s: str, i: int, q: str) -> tuple[str, int]:
    j = i + 1
    out = []
    while j < len(s):
        if s[j] == q:
            if j + 1 < len(s) and s[j + 1] == q:
                out.append(q)
                j += 2
                continue
            return "".join(out), j + 1
        out.append(s[j])
        j += 1
    return "".join(out), j


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _is_ident_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _is_ident_char(c: str) -> bool:
    return c.isalnum() or c in "_."


def strip_comments(expr: str) -> str:
    out = []
    i, n = 0, len(expr)
    while i < n:
        c = expr[i]
        if c == '"':
            _, j = _read_quoted(expr, i, '"')
            out.append(expr[i:j])
            i = j
        elif c == "'":
            _, j = _read_quoted(expr, i, "'")
            out.append(expr[i:j])
            i = j
        elif expr.startswith("//", i) or expr.startswith("--", i):
            j = expr.find("\n", i)
            i = n if j < 0 else j
        elif expr.startswith("/*", i):
            j = expr.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def references(expr: str | None) -> DaxRefs:
    refs = DaxRefs()
    if not expr:
        return refs
    s = expr
    i, n = 0, len(s)
    prev_kw = ""
    while i < n:
        c = s[i]
        if s.startswith("//", i) or s.startswith("--", i):
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue
        if s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '"':
            _, i = _read_quoted(s, i, '"')
            prev_kw = ""
            continue
        if c == "'":
            name, j = _read_quoted(s, i, "'")
            k = _skip_ws(s, j)
            if k < n and s[k] == "[":
                col, k2 = _read_bracket(s, k)
                refs.add_unique("columns", (name, col))
                i = k2
            else:
                refs.add_unique("tables", name)
                i = j
            prev_kw = ""
            continue
        if c == "[":
            name, i = _read_bracket(s, i)
            refs.add_unique("bare", name)
            prev_kw = ""
            continue
        if _is_ident_start(c):
            j = i
            while j < n and _is_ident_char(s[j]):
                j += 1
            ident = s[i:j]
            k = _skip_ws(s, j)
            up = ident.upper()
            if prev_kw == "VAR":
                refs.add_unique("variables", ident)
                prev_kw = ""
                i = j
                continue
            if k < n and s[k] == "(":
                refs.add_unique("functions", up)
                prev_kw = ""
            elif k < n and s[k] == "[" and up not in KEYWORDS and ident not in refs.variables:
                col, k2 = _read_bracket(s, k)
                refs.add_unique("columns", (ident, col))
                i = k2
                prev_kw = ""
                continue
            elif up in KEYWORDS:
                prev_kw = up
            elif ident not in refs.variables:
                refs.add_unique("tables", ident)
                prev_kw = ""
            i = j
            continue
        if not c.isspace():
            prev_kw = ""
        i += 1
    # identifiers that turned out to be variables declared later are removed
    refs.tables = [t for t in refs.tables if t not in refs.variables]
    return refs


@dataclass
class CalcDependency:
    object_type: str
    table: str
    object: str
    ref_type: str
    ref_table: str
    ref_object: str


def load_calcdependency_csv(path: str | Path) -> list[CalcDependency]:
    """Import the output of  EVALUATE INFO.CALCDEPENDENCY()  saved as CSV (DAX Studio / Tabular Editor)."""
    out: list[CalcDependency] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            r = {k.strip().strip("[]").upper(): (v or "").strip() for k, v in row.items() if k}
            out.append(CalcDependency(
                r.get("OBJECT_TYPE", ""), r.get("TABLE", ""), r.get("OBJECT", ""),
                r.get("REFERENCED_OBJECT_TYPE", ""), r.get("REFERENCED_TABLE", ""), r.get("REFERENCED_OBJECT", ""),
            ))
    return out
