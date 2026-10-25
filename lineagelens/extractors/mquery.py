"""Power Query (M) analysis focused on Snowflake sources.

Supports Snowflake.Databases navigation, Value.NativeQuery embedded SQL, parameter
substitution, Table.RenameColumns / SelectColumns / RemoveColumns / AddColumn /
TransformColumnNames.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_STR = r'"(?:[^"]|"")*"'
_NAME_VAL = rf'({_STR}|#"(?:[^"]|"")*"|[A-Za-z_][\w\.]*)'
NAV_RE = re.compile(
    r"\[\s*Name\s*=\s*" + _NAME_VAL + r"\s*(?:,\s*Kind\s*=\s*\"(\w+)\")?\s*(?:,[^\]]*)?\]"
    r"|\[\s*Kind\s*=\s*\"(\w+)\"\s*,\s*Name\s*=\s*" + _NAME_VAL + r"\s*\]"
)
M_ESCAPES = {"#(lf)": "\n", "#(cr)": "\r", "#(tab)": "\t", "#(#)": "#", "#(cr,lf)": "\r\n"}


def m_unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('#"') and s.endswith('"'):
        return s[2:-1].replace('""', '"')
    if s.startswith('"') and s.endswith('"'):
        inner = s[1:-1].replace('""', '"')
        for k, v in M_ESCAPES.items():
            inner = inner.replace(k, v)
        return inner
    return s


def parameter_value(expr: str) -> str | None:
    """Value of an M parameter expression:  "ANALYTICS" meta [IsParameterQuery=true ...]"""
    m = re.match(r'\s*(' + _STR + r')', expr or "")
    if m:
        return m_unquote(m.group(1))
    return None


def _call_args(text: str, start: int) -> tuple[str, int]:
    """Given index of '(' return inner text of the balanced call and index after ')'."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], n


def _split_top(args: str) -> list[str]:
    out, depth, cur, i, n = [], 0, [], 0, len(args)
    while i < n:
        c = args[i]
        if c == '"':
            j = i + 1
            while j < n:
                if args[j] == '"':
                    if j + 1 < n and args[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            cur.append(args[i:j + 1])
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if cur:
        out.append("".join(cur).strip())
    return out


def _strings(text: str) -> list[str]:
    return [m_unquote(m) for m in re.findall(_STR, text)]


def strip_m_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


@dataclass
class MSource:
    connector: str = "unknown"            # snowflake | native_query | other | unknown
    database: str = ""
    schema: str = ""
    object: str = ""
    object_kind: str = ""                 # Table | View
    native_sql: str = ""
    renames: list[tuple[str, str]] = field(default_factory=list)
    selected: list[str] | None = None
    removed: list[str] = field(default_factory=list)
    added: dict[str, list[str]] = field(default_factory=dict)
    name_transform: str = ""              # lower | upper | custom
    warnings: list[str] = field(default_factory=list)

    @property
    def relation(self) -> str:
        parts = [p for p in (self.database, self.schema, self.object) if p]
        return ".".join(p.upper() for p in parts)

    def source_name_for(self, final_name: str) -> tuple[str | None, str]:
        """Map a column name as exposed by the M query back to the upstream column name.

        Returns (upstream_name or None if produced by AddColumn / removed, how)
        """
        current = final_name
        how = "direct"
        for old, new in reversed(self.renames):
            if current == new:
                current = old
                how = "renamed in Power Query"
            elif current.lower() == new.lower():
                current = old
                how = "renamed in Power Query"
        if final_name in self.added:
            return None, "added in Power Query"
        return current, how


def parse_m(expr: str, params: dict[str, str] | None = None) -> MSource:
    params = params or {}
    src = MSource()
    if not expr:
        src.warnings.append("empty M expression")
        return src
    text = strip_m_comments(expr)

    def resolve(raw: str) -> str:
        raw = raw.strip()
        if raw.startswith('"'):
            return m_unquote(raw)
        name = m_unquote(raw)
        if name in params:
            return params[name]
        src.warnings.append(f"navigation uses '{name}' which is not a known text parameter")
        return name

    if re.search(r"\bSnowflake\.Databases\s*\(", text):
        src.connector = "snowflake"
    elif re.search(r"\b(Sql\.Database|Databricks\.|Odbc\.|Sql\.Databases|GoogleBigQuery|AmazonRedshift)", text):
        src.connector = "other"

    # navigation records in order of appearance
    order = ["Database", "Schema", "Table"]
    navs: list[tuple[str, str]] = []
    for m in NAV_RE.finditer(text):
        if m.group(1) is not None:
            name, kind = resolve(m.group(1)), (m.group(2) or "")
        else:
            kind, name = m.group(3), resolve(m.group(4))
        if not kind:
            kind = order[min(len(navs), 2)]
        navs.append((name, kind))
    for name, kind in navs:
        k = kind.lower()
        if k == "database":
            src.database = name
        elif k == "schema":
            src.schema = name
        elif k in ("table", "view", "function", "materializedview", "dynamictable"):
            src.object = name
            src.object_kind = kind

    # Value.NativeQuery(<target>, "<sql>", ...)
    for m in re.finditer(r"\bValue\.NativeQuery\s*\(", text):
        args, _ = _call_args(text, m.end() - 1)
        parts = _split_top(args)
        if len(parts) >= 2:
            sql_part = parts[1].strip()
            if sql_part.startswith('"'):
                src.native_sql = m_unquote(sql_part)
            elif m_unquote(sql_part) in params:
                src.native_sql = params[m_unquote(sql_part)]
            else:
                src.warnings.append("Value.NativeQuery SQL is not a literal string (dynamic) - cannot parse")
            src.connector = "native_query" if src.connector in ("snowflake", "unknown") else src.connector
            src.object = ""
    # transformations, in textual order
    for m in re.finditer(r"\bTable\.(RenameColumns|SelectColumns|RemoveColumns|AddColumn|TransformColumnNames)\s*\(", text):
        fn = m.group(1)
        args, _ = _call_args(text, m.end() - 1)
        parts = _split_top(args)
        if fn == "RenameColumns" and len(parts) >= 2:
            for a, b in re.findall(r"\{\s*(" + _STR + r")\s*,\s*(" + _STR + r")\s*\}", parts[1]):
                src.renames.append((m_unquote(a), m_unquote(b)))
        elif fn == "SelectColumns" and len(parts) >= 2:
            sel = _strings(parts[1])
            # names refer to the current (possibly renamed) names
            src.selected = sel
        elif fn == "RemoveColumns" and len(parts) >= 2:
            src.removed.extend(_strings(parts[1]))
        elif fn == "AddColumn" and len(parts) >= 3:
            name = m_unquote(parts[1])
            deps = [d for d in re.findall(r"\[([^\]=,]+)\]", ",".join(parts[2:])) if not d.strip().startswith("Name")]
            src.added[name] = [d.strip() for d in deps]
        elif fn == "TransformColumnNames" and len(parts) >= 2:
            f = parts[1]
            if re.fullmatch(r"\s*Text\.Lower\s*", f) or re.search(r"each\s+Text\.Lower\s*\(\s*_\s*\)", f):
                src.name_transform = "lower"
            elif re.fullmatch(r"\s*Text\.Upper\s*", f) or re.search(r"each\s+Text\.Upper\s*\(\s*_\s*\)", f):
                src.name_transform = "upper"
            else:
                src.name_transform = "custom"
    if src.connector == "unknown" and not navs:
        src.warnings.append("no Snowflake source found in M expression")
    return src
