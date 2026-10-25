"""Naming-convention normalisation used as a matching tie-breaker.

Matching tiers (best first):
  exact            -> high
  case-insensitive -> high
  normalised       -> medium   (prefix/suffix strip, snake_case <-> Title Case, regex map)
  fuzzy (>= threshold on normalised form) -> low
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

try:  # rapidfuzz is optional at runtime
    from rapidfuzz import fuzz as _fuzz
except Exception:  # pragma: no cover
    _fuzz = None


@dataclass
class NamingRules:
    case_insensitive: bool = True
    strip_prefixes: list[str] = field(default_factory=list)
    strip_suffixes: list[str] = field(default_factory=list)
    regex_map: list[dict] = field(default_factory=list)   # [{pattern, replace}]
    fuzzy_threshold: int = 90
    enable_fuzzy: bool = True

    @classmethod
    def from_dict(cls, d: dict | None) -> "NamingRules":
        d = d or {}
        return cls(
            case_insensitive=d.get("case_insensitive", True),
            strip_prefixes=list(d.get("strip_prefixes", []) or []),
            strip_suffixes=list(d.get("strip_suffixes", []) or []),
            regex_map=list(d.get("regex_map", []) or []),
            fuzzy_threshold=int(d.get("fuzzy_threshold", 90)),
            enable_fuzzy=bool(d.get("enable_fuzzy", True)),
        )


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokens(name: str) -> list[str]:
    """Split a name into lowercase word tokens (handles snake, kebab, camel, Title Case)."""
    s = _CAMEL.sub(" ", name.strip())
    s = re.sub(r"[_\-\s\.]+", " ", s)
    return [t.lower() for t in s.split() if t]


def normalise(name: str, rules: NamingRules | None = None) -> str:
    rules = rules or NamingRules()
    s = name.strip().strip('"').strip("'")
    for rm in rules.regex_map:
        try:
            s = re.sub(rm["pattern"], rm.get("replace", ""), s, flags=re.IGNORECASE)
        except (re.error, KeyError):
            continue
    up = s.upper()
    for p in sorted(rules.strip_prefixes, key=len, reverse=True):
        if p and up.startswith(p.upper()) and len(up) > len(p):
            s = s[len(p):]
            up = s.upper()
            break
    for p in sorted(rules.strip_suffixes, key=len, reverse=True):
        if p and up.endswith(p.upper()) and len(up) > len(p):
            s = s[: -len(p)]
            up = s.upper()
            break
    return "_".join(tokens(s))


def to_title(name: str) -> str:
    return " ".join(t.capitalize() for t in tokens(name))


def to_snake_upper(name: str) -> str:
    return "_".join(tokens(name)).upper()


@dataclass
class Match:
    candidate: str
    confidence: str
    method: str
    score: float = 100.0


def best_match(name: str, candidates: Iterable[str], rules: NamingRules | None = None) -> Match | None:
    rules = rules or NamingRules()
    cands = list(candidates)
    if not cands:
        return None
    if name in cands:
        return Match(name, "high", "exact")
    if rules.case_insensitive:
        lower = {c.lower(): c for c in cands}
        if name.lower() in lower:
            return Match(lower[name.lower()], "high", "case-insensitive")
    norm = normalise(name, rules)
    normed: dict[str, list[str]] = {}
    for c in cands:
        normed.setdefault(normalise(c, rules), []).append(c)
    if norm in normed and len(normed[norm]) == 1:
        return Match(normed[norm][0], "medium", "naming-convention")
    if rules.enable_fuzzy and _fuzz is not None and norm:
        best: tuple[float, str] | None = None
        for n, cs in normed.items():
            if len(cs) != 1:
                continue
            score = _fuzz.ratio(norm, n)
            if best is None or score > best[0]:
                best = (score, cs[0])
        if best and best[0] >= rules.fuzzy_threshold:
            return Match(best[1], "low", "fuzzy", best[0])
    return None
