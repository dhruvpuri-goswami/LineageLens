"""Column-level lineage for Snowflake SQL using sqlglot.

The query is qualified against a schema (so SELECT * expands), then every output
column is resolved through CTEs / sub-queries / unions back to base relations.
Transformation is classified as passthrough / renamed / derived. Columns used in
WHERE / JOIN / QUALIFY / HAVING / GROUP BY are reported as filter dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, build_scope

DIALECT = "snowflake"


@dataclass(frozen=True)
class SourceCol:
    relation: str      # DB.SCHEMA.NAME (upper)
    column: str        # upper


@dataclass
class ColumnLineage:
    name: str                                   # output column (upper)
    sources: list[SourceCol] = field(default_factory=list)
    transform: str = "derived"                   # passthrough | renamed | derived | constant
    expression: str = ""
    resolved: bool = True


@dataclass
class QueryLineage:
    columns: list[ColumnLineage] = field(default_factory=list)
    filter_sources: list[SourceCol] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    qualified_sql: str = ""

    def column(self, name: str) -> ColumnLineage | None:
        for c in self.columns:
            if c.name.upper() == name.upper():
                return c
        return None


def _ident(e: exp.Expression | None) -> str:
    if e is None:
        return ""
    if isinstance(e, exp.Identifier):
        return e.this
    return e.name


def relation_key(table: exp.Table, default_db: str = "", default_schema: str = "") -> str:
    parts = [table.catalog or default_db, table.db or default_schema, table.name]
    return ".".join(p.upper() for p in parts if p)


def _upper_schema(schema: dict) -> dict:
    out: dict = {}
    for db, schemas in schema.items():
        for sc, tables in schemas.items():
            for t, cols in tables.items():
                out.setdefault(db.upper(), {}).setdefault(sc.upper(), {})[t.upper()] = {
                    c.upper(): (ty or "VARCHAR") for c, ty in cols.items()
                }
    return out


def parse_sql(sql: str) -> exp.Expression:
    exprs = [e for e in sqlglot.parse(sql, dialect=DIALECT) if e is not None]
    if not exprs:
        raise ValueError("empty SQL")
    return exprs[-1]


def _select_of(e: exp.Expression) -> exp.Expression:
    """Return the query part of CREATE VIEW ... AS <query> or the query itself."""
    if isinstance(e, exp.Create):
        return e.expression
    return e


class _Resolver:
    def __init__(self, default_db: str, default_schema: str):
        self.default_db = default_db
        self.default_schema = default_schema
        self.relations: set[str] = set()

    def table_source(self, scope: Scope, table: str):
        src = scope.sources.get(table)
        if src is None:
            # case-insensitive fallback
            for k, v in scope.sources.items():
                if k.upper() == table.upper():
                    return v
        return src

    def resolve_column(self, scope: Scope, table: str, column: str, depth: int = 0):
        """-> (list[SourceCol], transform, resolved)"""
        if depth > 40:
            return [], "derived", False
        if not table:
            # unqualified column: only resolvable if exactly one source
            try:
                selected = list(scope.selected_sources.keys())
            except Exception:
                selected = list(scope.sources.keys())
            if len(selected) == 1:
                table = selected[0]
            else:
                return [], "derived", False
        src = self.table_source(scope, table)
        if src is None:
            if scope.parent is not None:  # correlated reference
                return self.resolve_column(scope.parent, table, column, depth + 1)
            return [], "derived", False
        if isinstance(src, exp.Table):
            rk = relation_key(src, self.default_db, self.default_schema)
            self.relations.add(rk)
            return [SourceCol(rk, column.upper())], "passthrough", True
        if isinstance(src, Scope):
            if isinstance(src.expression, (exp.Lateral, exp.Unnest, exp.Explode)):
                # LATERAL FLATTEN(input => o.tags) f  ->  f.VALUE / f.KEY ... derive from the input columns
                srcs: list[SourceCol] = []
                ok = True
                for c in src.expression.find_all(exp.Column):
                    s_, _, r = self.resolve_column(scope, c.table, c.name, depth + 1)
                    srcs.extend(s_)
                    ok = ok and r
                return _dedupe(srcs), "derived", ok
            return self.resolve_output(src, column, depth + 1)
        return [], "derived", False

    def _projections(self, scope: Scope) -> list[exp.Expression]:
        e = scope.expression
        if isinstance(e, exp.Select):
            return list(e.expressions)
        return []

    def resolve_output(self, scope: Scope, column: str, depth: int = 0, index: int | None = None):
        e = scope.expression
        if isinstance(e, (exp.SetOperation,)) or scope.set_operation_scopes:
            # resolve by position across all branches
            branches = scope.set_operation_scopes
            if not branches:
                return [], "derived", False
            left_proj = self._branch_projections(branches[0])
            pos = index
            if pos is None:
                for i, p in enumerate(left_proj):
                    if p.alias_or_name.upper() == column.upper():
                        pos = i
                        break
            if pos is None:
                return [], "derived", False
            srcs: list[SourceCol] = []
            ok = True
            for b in branches:
                s, _, r = self.resolve_output(b, column, depth + 1, index=pos)
                srcs.extend(s)
                ok = ok and r
            return _dedupe(srcs), "derived", ok
        projs = self._projections(scope)
        target = None
        if index is not None and index < len(projs):
            target = projs[index]
        else:
            for p in projs:
                if p.alias_or_name.upper() == column.upper():
                    target = p
                    break
        if target is None:
            # star that could not be expanded -> try passthrough to single source
            if any(isinstance(p, exp.Star) or (isinstance(p, exp.Column) and isinstance(p.this, exp.Star)) for p in projs):
                if len(scope.sources) == 1:
                    s, t, r = self.resolve_column(scope, next(iter(scope.sources)), column, depth + 1)
                    return s, t, False
            return [], "derived", False
        return self.resolve_expression(scope, target, depth)

    def _branch_projections(self, scope: Scope):
        if scope.set_operation_scopes:
            return self._branch_projections(scope.set_operation_scopes[0])
        return self._projections(scope)

    def resolve_expression(self, scope: Scope, target: exp.Expression, depth: int = 0):
        out_name = target.alias_or_name.upper()
        inner = target.this if isinstance(target, exp.Alias) else target
        if isinstance(inner, exp.Column) and not isinstance(inner.this, exp.Star):
            srcs, t, ok = self.resolve_column(scope, inner.table, inner.name, depth + 1)
            if t == "derived":
                return srcs, "derived", ok
            leaf_names = {s.column for s in srcs}
            renamed = t == "renamed" or inner.name.upper() != out_name or (leaf_names and leaf_names != {out_name})
            return srcs, ("renamed" if renamed else "passthrough"), ok
        cols = [c for c in inner.find_all(exp.Column) if not isinstance(c.this, exp.Star)]
        if not cols:
            return [], "constant", True
        srcs: list[SourceCol] = []
        ok = True
        for c in cols:
            s, _, r = self.resolve_column(scope, c.table, c.name, depth + 1)
            srcs.extend(s)
            ok = ok and r
        return _dedupe(srcs), "derived", ok


def _dedupe(items):
    seen = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def lineage_for_sql(
    sql: str,
    schema: dict | None = None,
    default_db: str = "",
    default_schema: str = "",
    column_names: list[str] | None = None,
) -> QueryLineage:
    """Compute column lineage for a SELECT (or CREATE VIEW ... AS SELECT) statement.

    schema: {DB: {SCHEMA: {TABLE: {COL: TYPE}}}}
    column_names: explicit output column list (e.g. CREATE VIEW v (a, b) AS ...)
    """
    result = QueryLineage()
    try:
        parsed = parse_sql(sql)
    except Exception as ex:  # sqlglot ParseError etc.
        result.warnings.append(f"SQL parse error: {str(ex).splitlines()[0][:200]}")
        return result
    query = _select_of(parsed)
    if query is None or not isinstance(query, exp.Query):
        result.warnings.append("statement is not a query")
        return result
    sch = _upper_schema(schema or {})
    try:
        q = qualify(
            query.copy(),
            schema=sch,
            dialect=DIALECT,
            catalog=default_db or None,
            db=default_schema or None,
            validate_qualify_columns=False,
            quote_identifiers=False,
            identify=False,
        )
    except Exception as ex:
        result.warnings.append(f"could not qualify query ({type(ex).__name__}: {str(ex)[:160]}); falling back to unqualified parse")
        q = query.copy()
    result.qualified_sql = q.sql(DIALECT, pretty=True)
    try:
        root = build_scope(q)
    except Exception as ex:
        result.warnings.append(f"scope analysis failed: {ex}")
        return result
    if root is None:
        result.warnings.append("no scope found")
        return result

    res = _Resolver(default_db, default_schema)
    # output columns
    if root.set_operation_scopes:
        names = [p.alias_or_name for p in res._branch_projections(root)]
    else:
        names = [p.alias_or_name for p in res._projections(root)]
    for i, name in enumerate(names):
        out_name = (column_names[i] if column_names and i < len(column_names) else name).upper()
        if name == "*":
            result.warnings.append("SELECT * could not be expanded (upstream columns unknown)")
            continue
        srcs, transform, ok = res.resolve_output(root, name, index=i)
        expr_sql = ""
        if not root.set_operation_scopes:
            p = res._projections(root)[i]
            expr_sql = (p.this if isinstance(p, exp.Alias) else p).sql(DIALECT)
            if column_names and out_name != name.upper() and transform == "passthrough":
                transform = "renamed"
        result.columns.append(ColumnLineage(out_name, srcs, transform, expr_sql, ok))
        if not ok:
            result.warnings.append(f"column {out_name}: could not fully resolve sources")

    # filter / join dependencies across all scopes
    filt: list[SourceCol] = []
    for scope in root.traverse():
        e = scope.expression
        if not isinstance(e, exp.Select):
            continue
        clauses = []
        for key in ("where", "qualify", "having", "group"):
            if e.args.get(key) is not None:
                clauses.append(e.args[key])
        for j in e.args.get("joins") or []:
            if j.args.get("on") is not None:
                clauses.append(j.args["on"])
        for clause in clauses:
            for c in clause.find_all(exp.Column):
                if isinstance(c.this, exp.Star):
                    continue
                s, _, _ = res.resolve_column(scope, c.table, c.name)
                filt.extend(s)
    result.filter_sources = _dedupe(filt)
    result.relations = sorted(res.relations)
    return result


def referenced_relations(sql: str, default_db: str = "", default_schema: str = "") -> list[str]:
    """Base relations referenced by a statement (CTE names excluded)."""
    try:
        parsed = parse_sql(sql)
    except Exception:
        return []
    q = _select_of(parsed)
    if q is None:
        return []
    ctes = {c.alias_or_name.upper() for c in q.find_all(exp.CTE)}
    out = []
    for t in q.find_all(exp.Table):
        if not t.db and t.name.upper() in ctes:
            continue
        if not t.name:
            continue
        out.append(relation_key(t, default_db, default_schema))
    return sorted(set(out))


def view_name_and_columns(sql: str, default_db: str = "", default_schema: str = ""):
    """For CREATE VIEW statements -> (relation_key, explicit column names or None, query sql)."""
    parsed = parse_sql(sql)
    if not isinstance(parsed, exp.Create):
        raise ValueError("not a CREATE statement")
    target = parsed.this
    cols = None
    if isinstance(target, exp.Schema):
        cols = [_ident(c) if not isinstance(c, exp.ColumnDef) else c.name for c in target.expressions]
        target = target.this
    if not isinstance(target, exp.Table):
        raise ValueError("cannot find view name")
    kind = (parsed.args.get("kind") or "VIEW").upper()
    return relation_key(target, default_db, default_schema), cols, parsed.expression.sql(DIALECT), kind
