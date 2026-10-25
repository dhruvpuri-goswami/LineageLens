"""Power BI semantic model parsing: PBIP TMDL folders and legacy model.bim (TMSL JSON)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .mquery import parameter_value


# --------------------------------------------------------------------------- data model
@dataclass
class PColumn:
    name: str
    source_column: str = ""
    expression: str = ""            # calculated column DAX
    data_type: str = ""
    is_hidden: bool = False
    description: str = ""
    kind: str = "data"              # data | calculated | calculatedTableColumn
    sort_by: str = ""


@dataclass
class PMeasure:
    name: str
    expression: str
    description: str = ""
    display_folder: str = ""
    format_string: str = ""


@dataclass
class PPartition:
    name: str
    kind: str = "m"                 # m | calculated | entity | unknown
    mode: str = ""
    expression: str = ""


@dataclass
class PCalcItem:
    name: str
    expression: str
    format_string_expression: str = ""


@dataclass
class PTable:
    name: str
    columns: dict[str, PColumn] = field(default_factory=dict)
    measures: dict[str, PMeasure] = field(default_factory=dict)
    partitions: list[PPartition] = field(default_factory=list)
    calc_items: list[PCalcItem] = field(default_factory=list)
    is_calc_group: bool = False
    hierarchies: dict[str, dict[str, str]] = field(default_factory=dict)  # hierarchy -> level -> column
    description: str = ""
    file: str = ""
    is_hidden: bool = False

    @property
    def is_field_parameter(self) -> bool:
        for p in self.partitions:
            if p.kind == "calculated" and "NAMEOF" in p.expression.upper():
                return True
        return False


@dataclass
class PRole:
    name: str
    filters: dict[str, str] = field(default_factory=dict)  # table -> DAX filter
    file: str = ""


@dataclass
class PRelationship:
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    active: bool = True


@dataclass
class SemanticModel:
    name: str
    path: str
    format: str
    tables: dict[str, PTable] = field(default_factory=dict)
    roles: dict[str, PRole] = field(default_factory=dict)
    relationships: list[PRelationship] = field(default_factory=list)
    expressions: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def parameters(self) -> dict[str, str]:
        out = {}
        for k, v in self.expressions.items():
            pv = parameter_value(v)
            if pv is not None and "IsParameterQuery" in v:
                out[k] = pv
        return out

    def table(self, name: str) -> PTable | None:
        if name in self.tables:
            return self.tables[name]
        for k, t in self.tables.items():
            if k.lower() == name.lower():
                return t
        return None

    def find_measure(self, name: str) -> tuple[PTable, PMeasure] | None:
        for t in self.tables.values():
            for mk, m in t.measures.items():
                if mk.lower() == name.lower():
                    return t, m
        return None


# --------------------------------------------------------------------------- TMDL
@dataclass
class TNode:
    keyword: str
    name: str = ""
    expr: str | None = None
    value: str | None = None            # for "key: value" properties
    children: list["TNode"] = field(default_factory=list)
    description: str = ""
    is_ref: bool = False

    def prop(self, key: str, default: str = "") -> str:
        for c in self.children:
            if c.keyword == key:
                if c.value is not None:
                    return c.value
                if c.expr is not None:
                    return c.expr
                return "true"
        return default

    def has_flag(self, key: str) -> bool:
        return any(c.keyword == key for c in self.children)

    def kids(self, key: str):
        return [c for c in self.children if c.keyword == key]


def _depth(line: str) -> int:
    tabs = 0
    spaces = 0
    for ch in line:
        if ch == "\t":
            tabs += 1
        elif ch == " ":
            spaces += 1
        else:
            break
    return tabs + spaces // 4


def unquote_name(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        return s[1:-1].replace("''", "'")
    return s


def _split_name(rest: str) -> tuple[str, str | None]:
    rest = rest.strip()
    if rest.startswith("'"):
        j = 1
        while j < len(rest):
            if rest[j] == "'":
                if j + 1 < len(rest) and rest[j + 1] == "'":
                    j += 2
                    continue
                break
            j += 1
        name = rest[: j + 1]
        tail = rest[j + 1:].strip()
    else:
        m = re.match(r"([^=]*?)\s*(=.*)?$", rest)
        name = m.group(1) if m else rest
        tail = (m.group(2) or "") if m else ""
    expr = None
    if tail.startswith("="):
        expr = tail[1:].strip()
    return unquote_name(name), expr


def _dedent(lines: list[str]) -> str:
    rows = [ln.rstrip("\r\n") for ln in lines]
    while rows and not rows[-1].strip():
        rows.pop()
    while rows and not rows[0].strip():
        rows.pop(0)
    if not rows:
        return ""
    indents = [len(r) - len(r.lstrip("\t ")) for r in rows if r.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(r[cut:] if len(r) >= cut else r.strip() for r in rows)


def parse_tmdl(text: str) -> list[TNode]:
    lines = text.replace("\r\n", "\n").split("\n")
    n = len(lines)
    pos = 0

    def read_expression(inline: str, d: int) -> str:
        nonlocal pos
        if inline.startswith("```"):
            body = []
            first = inline[3:]
            if first.strip():
                body.append(first)
            while pos < n and lines[pos].strip() != "```":
                body.append(lines[pos])
                pos += 1
            pos += 1  # closing fence
            return _dedent(body)
        body = [inline] if inline else []
        cont = []
        while pos < n:
            ln = lines[pos]
            if not ln.strip():
                cont.append(ln)
                pos += 1
                continue
            if _depth(ln) >= d + 2:
                cont.append(ln)
                pos += 1
            else:
                break
        # give back trailing blank lines
        while cont and not cont[-1].strip():
            cont.pop()
            pos -= 1
        if inline:
            if cont:
                return inline + "\n" + _dedent(cont)
            return inline
        return _dedent(cont)

    def block(d: int) -> list[TNode]:
        nonlocal pos
        nodes: list[TNode] = []
        desc: list[str] = []
        while pos < n:
            ln = lines[pos]
            if not ln.strip():
                pos += 1
                continue
            ld = _depth(ln)
            if ld < d:
                break
            if ld > d:
                pos += 1
                continue
            s = ln.strip()
            if s.startswith("///"):
                desc.append(s[3:].strip())
                pos += 1
                continue
            if s.startswith("//"):
                pos += 1
                continue
            m = re.match(r"^(ref\s+)?([A-Za-z][A-Za-z0-9_]*)\s*(.*)$", s)
            if not m:
                pos += 1
                continue
            is_ref, kw, rest = bool(m.group(1)), m.group(2), m.group(3)
            pos += 1
            if rest.startswith(":"):
                node = TNode(kw, value=unquote_name(rest[1:].strip()) if rest[1:].strip().startswith("'") and kw not in ("fromColumn", "toColumn", "column") else rest[1:].strip())
                node.children = block(d + 1)
                nodes.append(node)
                desc = []
                continue
            if rest.startswith("="):
                name, expr = "", rest[1:].strip()
            else:
                name, expr = _split_name(rest)
            node = TNode(kw, name=name, is_ref=is_ref, description="\n".join(desc))
            desc = []
            if expr is not None:
                node.expr = read_expression(expr, d)
            node.children = block(d + 1)
            nodes.append(node)
        return nodes

    return block(0)


def _split_table_column(ref: str) -> tuple[str, str]:
    """Sales.'Customer Key'  |  'Sales Summary'.'Order Date'  |  Date.Date"""
    ref = ref.strip()
    if ref.startswith("'"):
        j = 1
        while j < len(ref):
            if ref[j] == "'":
                if j + 1 < len(ref) and ref[j + 1] == "'":
                    j += 2
                    continue
                break
            j += 1
        table = unquote_name(ref[: j + 1])
        col = ref[j + 2:]
    else:
        table, _, col = ref.partition(".")
    return table, unquote_name(col)


def _table_from_tnode(t: TNode, file: str) -> PTable:
    table = PTable(name=t.name, description=t.description, file=file, is_hidden=t.has_flag("isHidden"))
    for c in t.children:
        if c.keyword == "column":
            col = PColumn(
                name=c.name, source_column=c.prop("sourceColumn"), data_type=c.prop("dataType"),
                is_hidden=c.has_flag("isHidden"), description=c.description, sort_by=unquote_name(c.prop("sortByColumn")),
            )
            if c.expr:
                col.expression = c.expr
                col.kind = "calculated"
            table.columns[col.name] = col
        elif c.keyword == "measure":
            table.measures[c.name] = PMeasure(c.name, c.expr or "", c.description, c.prop("displayFolder"), c.prop("formatString"))
        elif c.keyword == "partition":
            kind = (c.expr or "").strip().lower() or "m"
            table.partitions.append(PPartition(c.name, kind, c.prop("mode"), c.prop("source")))
        elif c.keyword == "calculationGroup":
            table.is_calc_group = True
            for it in c.kids("calculationItem"):
                table.calc_items.append(PCalcItem(it.name, it.expr or "", it.prop("formatStringDefinition")))
        elif c.keyword == "hierarchy":
            levels = {}
            for lv in c.kids("level"):
                levels[lv.name] = unquote_name(lv.prop("column"))
            table.hierarchies[c.name] = levels
    # calculated tables (non-parameter) : columns get sourceColumn like [Value1]
    return table


def load_tmdl_folder(folder: str | Path, name: str | None = None) -> SemanticModel:
    folder = Path(folder)
    root = folder
    if (folder / "definition").is_dir():
        root = folder / "definition"
    model_name = name or folder.name.replace(".SemanticModel", "").replace(".Dataset", "")
    sm = SemanticModel(model_name, str(folder), "tmdl")
    files = sorted(root.rglob("*.tmdl"))
    if not files:
        sm.warnings.append(f"no .tmdl files found under {root}")
    for f in files:
        try:
            nodes = parse_tmdl(f.read_text(encoding="utf-8-sig"))
        except Exception as ex:  # pragma: no cover - defensive
            sm.warnings.append(f"{f.name}: TMDL parse error {ex}")
            continue
        _ingest_tmdl_nodes(sm, nodes, str(f))
    return sm


def _ingest_tmdl_nodes(sm: SemanticModel, nodes: list[TNode], file: str) -> None:
    for node in nodes:
        if node.is_ref:
            continue
        if node.keyword == "table":
            sm.tables[node.name] = _table_from_tnode(node, file)
        elif node.keyword == "role":
            role = PRole(node.name, file=file)
            for tp in node.kids("tablePermission"):
                if tp.expr:
                    role.filters[tp.name] = tp.expr
            sm.roles[node.name] = role
        elif node.keyword == "relationship":
            ft, fc = _split_table_column(node.prop("fromColumn"))
            tt, tc = _split_table_column(node.prop("toColumn"))
            sm.relationships.append(PRelationship(node.name, ft, fc, tt, tc, node.prop("isActive", "true") != "false"))
        elif node.keyword == "expression":
            sm.expressions[node.name] = node.expr or ""
        elif node.keyword in ("model", "database"):
            _ingest_tmdl_nodes(sm, node.children, file)


# --------------------------------------------------------------------------- model.bim
def _expr(v) -> str:
    if isinstance(v, list):
        return "\n".join(v)
    return v or ""


def load_bim(path: str | Path, name: str | None = None) -> SemanticModel:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    model = data.get("model", data)
    model_name = name or data.get("name") or path.parent.name.replace(".SemanticModel", "").replace(".Dataset", "") or path.stem
    sm = SemanticModel(model_name, str(path), "bim")
    for t in model.get("tables", []):
        table = PTable(name=t["name"], description=_expr(t.get("description")), file=str(path), is_hidden=bool(t.get("isHidden")))
        for c in t.get("columns", []):
            col = PColumn(c["name"], c.get("sourceColumn", ""), data_type=c.get("dataType", ""), is_hidden=bool(c.get("isHidden")),
                          description=_expr(c.get("description")), sort_by=c.get("sortByColumn", ""))
            if c.get("type") == "calculated" or c.get("expression"):
                col.kind = "calculated"
                col.expression = _expr(c.get("expression"))
            elif c.get("type") == "calculatedTableColumn":
                col.kind = "calculatedTableColumn"
            table.columns[col.name] = col
        for m in t.get("measures", []):
            table.measures[m["name"]] = PMeasure(m["name"], _expr(m.get("expression")), _expr(m.get("description")),
                                                 m.get("displayFolder", ""), m.get("formatString", ""))
        for p in t.get("partitions", []):
            src = p.get("source", {})
            kind = src.get("type", "m")
            table.partitions.append(PPartition(p.get("name", t["name"]), kind, p.get("mode", ""), _expr(src.get("expression") or src.get("query"))))
        cg = t.get("calculationGroup")
        if cg:
            table.is_calc_group = True
            for it in cg.get("calculationItems", []):
                fsd = it.get("formatStringDefinition", {})
                table.calc_items.append(PCalcItem(it["name"], _expr(it.get("expression")), _expr(fsd.get("expression")) if isinstance(fsd, dict) else ""))
        for h in t.get("hierarchies", []):
            table.hierarchies[h["name"]] = {lv["name"]: lv.get("column", lv["name"]) for lv in h.get("levels", [])}
        sm.tables[table.name] = table
    for r in model.get("roles", []):
        role = PRole(r["name"], file=str(path))
        for tp in r.get("tablePermissions", []):
            if tp.get("filterExpression"):
                role.filters[tp["name"]] = _expr(tp["filterExpression"])
        sm.roles[role.name] = role
    for rel in model.get("relationships", []):
        sm.relationships.append(PRelationship(rel.get("name", ""), rel["fromTable"], rel["fromColumn"], rel["toTable"], rel["toColumn"], rel.get("isActive", True)))
    for e in model.get("expressions", []):
        sm.expressions[e["name"]] = _expr(e.get("expression"))
    return sm


def load_semantic_model(path: str | Path) -> SemanticModel:
    """Load a *.SemanticModel folder (TMDL or model.bim inside), a definition folder, or a model.bim file."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".bim":
        return load_bim(p)
    if p.is_dir():
        if (p / "definition").is_dir() or list(p.glob("*.tmdl")):
            return load_tmdl_folder(p)
        if (p / "model.bim").exists():
            return load_bim(p / "model.bim", name=p.name.replace(".SemanticModel", "").replace(".Dataset", ""))
    raise FileNotFoundError(f"no TMDL definition or model.bim found at {path}")
