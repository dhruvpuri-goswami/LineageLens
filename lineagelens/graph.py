"""Typed lineage graph built on networkx.

Edges point downstream (data flows from source -> consumer).
Edge kinds:
  flow      - a data / reference dependency (traversed by impact analysis)
  contains  - structural containment (report -> page -> visual, model -> table)
  relationship - Power BI model relationship between two columns (informational)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

import networkx as nx

NODE_TYPES = [
    "dbt_source_column",
    "dbt_model_column",
    "snowflake_table_column",
    "snowflake_view_column",
    "pbi_model_column",
    "calc_column",
    "measure",
    "rls_role",
    "calc_group_item",
    "field_parameter",
    "visual",
    "page",
    "report",
    "semantic_model",
]

NODE_TYPE_LABELS = {
    "dbt_source_column": "dbt source column",
    "dbt_model_column": "dbt model column",
    "snowflake_table_column": "Snowflake table column",
    "snowflake_view_column": "Snowflake view column",
    "pbi_model_column": "Power BI column",
    "calc_column": "Calculated column",
    "measure": "Measure",
    "rls_role": "RLS role",
    "calc_group_item": "Calculation item",
    "field_parameter": "Field parameter",
    "visual": "Visual",
    "page": "Page",
    "report": "Report",
    "semantic_model": "Semantic model",
}

CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
BREAKS = "breaks"
MAY_CHANGE = "values_may_change"


def min_conf(a: str, b: str) -> str:
    return a if CONFIDENCE_RANK.get(a, 0) <= CONFIDENCE_RANK.get(b, 0) else b


def max_conf(a: str, b: str) -> str:
    return a if CONFIDENCE_RANK.get(a, 0) >= CONFIDENCE_RANK.get(b, 0) else b


@dataclass
class Node:
    id: str
    type: str
    name: str
    parent: str = ""          # table / view / model / page the node belongs to
    container: str = ""       # higher level container: dbt project, semantic model, report
    file: str = ""
    code: str = ""
    code_lang: str = ""       # sql | dax | m | json
    description: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LineageGraph:
    def __init__(self) -> None:
        self.g = nx.DiGraph()

    # ------------------------------------------------------------------ nodes
    def add_node(self, node: Node) -> Node:
        if node.id in self.g:
            existing: Node = self.g.nodes[node.id]["obj"]
            # merge: keep richer information
            for attr in ("parent", "container", "file", "code", "code_lang", "description"):
                if not getattr(existing, attr) and getattr(node, attr):
                    setattr(existing, attr, getattr(node, attr))
            existing.data.update({k: v for k, v in node.data.items() if k not in existing.data})
            return existing
        self.g.add_node(node.id, obj=node, type=node.type)
        return node

    def node(self, node_id: str) -> Node | None:
        if node_id in self.g:
            return self.g.nodes[node_id]["obj"]
        return None

    def nodes(self, type_: str | None = None) -> Iterable[Node]:
        for _, d in self.g.nodes(data=True):
            if type_ is None or d["type"] == type_:
                yield d["obj"]

    def __contains__(self, node_id: str) -> bool:
        return node_id in self.g

    def __len__(self) -> int:
        return self.g.number_of_nodes()

    # ------------------------------------------------------------------ edges
    def add_edge(
        self,
        src: str,
        dst: str,
        kind: str = "flow",
        confidence: str = "high",
        impact: str = BREAKS,
        reason: str = "",
    ) -> None:
        if src == dst or src not in self.g or dst not in self.g:
            return
        if self.g.has_edge(src, dst):
            d = self.g.edges[src, dst]
            # strongest evidence wins
            d["confidence"] = max_conf(d["confidence"], confidence)
            if impact == BREAKS:
                d["impact"] = BREAKS
            if reason and reason not in d["reason"]:
                d["reason"] = (d["reason"] + "; " + reason).strip("; ")
            if kind == "flow":
                d["kind"] = "flow"
            return
        self.g.add_edge(src, dst, kind=kind, confidence=confidence, impact=impact, reason=reason)

    def edges(self, kind: str | None = None):
        for s, t, d in self.g.edges(data=True):
            if kind is None or d["kind"] == kind:
                yield s, t, d

    def flow_successors(self, node_id: str):
        for _, t, d in self.g.out_edges(node_id, data=True):
            if d["kind"] == "flow":
                yield t, d

    def flow_predecessors(self, node_id: str):
        for s, _, d in self.g.in_edges(node_id, data=True):
            if d["kind"] == "flow":
                yield s, d

    def children(self, node_id: str):
        for _, t, d in self.g.out_edges(node_id, data=True):
            if d["kind"] == "contains":
                yield t

    def container_of(self, node_id: str) -> str | None:
        for s, _, d in self.g.in_edges(node_id, data=True):
            if d["kind"] == "contains":
                return s
        return None
