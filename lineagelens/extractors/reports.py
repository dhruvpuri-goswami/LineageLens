"""Power BI report parsing: PBIR (folder per visual), PBIR-Legacy report.json and .pbix (Report/Layout)."""
from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

AGG_FUNCS = {0: "Sum", 1: "Average", 2: "Count", 3: "Min", 4: "Max", 5: "CountNonNull", 6: "Median", 7: "StandardDeviation", 8: "Variance"}


@dataclass
class FieldRef:
    entity: str
    property: str
    kind: str                  # column | measure | hierarchy_level
    usage: str                 # e.g. "Values", "Category", "filter", "sort", "conditional formatting"
    aggregation: str = ""      # implicit measure aggregation if any
    hierarchy: str = ""

    def key(self):
        return (self.entity, self.property, self.kind, self.usage, self.aggregation)


@dataclass
class RVisual:
    id: str
    name: str
    visual_type: str
    fields: list[FieldRef] = field(default_factory=list)
    file: str = ""
    position: dict = field(default_factory=dict)


@dataclass
class RPage:
    id: str
    name: str
    visuals: list[RVisual] = field(default_factory=list)
    filters: list[FieldRef] = field(default_factory=list)
    file: str = ""
    ordinal: int = 0


@dataclass
class RExtMeasure:
    entity: str
    name: str
    expression: str


@dataclass
class Report:
    name: str
    path: str
    format: str                              # pbir | pbir-legacy | pbix
    pages: list[RPage] = field(default_factory=list)
    filters: list[FieldRef] = field(default_factory=list)
    extension_measures: list[RExtMeasure] = field(default_factory=list)
    model_ref: str = ""                      # semantic model name / path the report is bound to
    model_ref_kind: str = ""                 # byPath | byConnection | embedded
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- field walker
def _entity(expr: dict, aliases: dict[str, str]) -> str:
    sr = (expr or {}).get("SourceRef") or {}
    if "Entity" in sr:
        return sr["Entity"]
    if "Source" in sr:
        return aliases.get(sr["Source"], sr["Source"])
    return ""


def _usage_from_path(path: list[str]) -> str:
    joined = "/".join(path)
    if "sortDefinition" in path or "OrderBy" in path:
        return "sort"
    if "queryState" in path:
        i = path.index("queryState")
        if i + 1 < len(path):
            return path[i + 1]
    if any(p in ("filterConfig", "filters", "Where", "filter") for p in path):
        return "filter"
    if "objects" in path:
        return "conditional formatting"
    if "visualContainerObjects" in path or "vcObjects" in path:
        return "formatting"
    if "prototypeQuery" in path:
        return "field"
    if "expansionStates" in joined:
        return "drill state"
    return "reference"


def collect_fields(obj, path: list[str] | None = None, aliases: dict[str, str] | None = None, out: list[FieldRef] | None = None) -> list[FieldRef]:
    path = path or []
    aliases = dict(aliases or {})
    out = out if out is not None else []
    if isinstance(obj, dict):
        frm = obj.get("From")
        if isinstance(frm, list):
            for f in frm:
                if isinstance(f, dict) and "Name" in f and "Entity" in f:
                    aliases[f["Name"]] = f["Entity"]
        handled = False
        for kind_key, kind in (("Column", "column"), ("Measure", "measure")):
            v = obj.get(kind_key)
            if isinstance(v, dict) and "Property" in v and isinstance(v.get("Expression"), dict):
                out.append(FieldRef(_entity(v["Expression"], aliases), v["Property"], kind, _usage_from_path(path)))
                handled = True
        agg = obj.get("Aggregation")
        if isinstance(agg, dict) and isinstance(agg.get("Expression"), dict):
            inner = agg["Expression"].get("Column")
            if isinstance(inner, dict) and "Property" in inner:
                out.append(FieldRef(_entity(inner.get("Expression", {}), aliases), inner["Property"], "column",
                                    _usage_from_path(path), aggregation=AGG_FUNCS.get(agg.get("Function", 0), "Aggregate")))
                handled = True
        hl = obj.get("HierarchyLevel")
        if isinstance(hl, dict):
            h = (hl.get("Expression") or {}).get("Hierarchy") or {}
            hexpr = h.get("Expression") or {}
            # auto date/time variation: Expression.PropertyVariationSource
            pvs = hexpr.get("PropertyVariationSource")
            if isinstance(pvs, dict):
                out.append(FieldRef(_entity(pvs.get("Expression", {}), aliases), pvs.get("Property", ""), "column", _usage_from_path(path)))
            else:
                out.append(FieldRef(_entity(hexpr, aliases), hl.get("Level", ""), "hierarchy_level", _usage_from_path(path), hierarchy=h.get("Hierarchy", "")))
            handled = True
        if handled:
            return out
        for k, v in obj.items():
            collect_fields(v, path + [k], aliases, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_fields(v, path, aliases, out)
    return out


def _dedupe_fields(fields: list[FieldRef]) -> list[FieldRef]:
    seen, out = set(), []
    for f in fields:
        if f.entity and f.property and f.key() not in seen:
            seen.add(f.key())
            out.append(f)
    return out


def _visual_title(vobj: dict, fallback: str) -> str:
    try:
        for container_key in ("visualContainerObjects", "vcObjects"):
            t = vobj.get(container_key, {}).get("title")
            if t:
                val = t[0]["properties"]["text"]["expr"]["Literal"]["Value"]
                return val.strip("'")
    except (KeyError, IndexError, TypeError):
        pass
    return fallback


def _describe(vtype: str, fields: list[FieldRef]) -> str:
    names = [f.property for f in fields if f.usage not in ("filter", "sort", "formatting", "conditional formatting")]
    pretty = re.sub(r"(?<!^)(?=[A-Z])", " ", vtype).capitalize() if vtype else "Visual"
    if names:
        return f"{pretty}: {', '.join(names[:3])}" + ("…" if len(names) > 3 else "")
    return pretty


# --------------------------------------------------------------------------- PBIR
def load_pbir(folder: str | Path) -> Report:
    folder = Path(folder)
    name = folder.name.replace(".Report", "")
    defn = folder / "definition"
    rep = Report(name, str(folder), "pbir")
    _read_dataset_reference(folder, rep)
    rj = defn / "report.json"
    if rj.exists():
        data = _load_json(rj, rep)
        rep.filters = _dedupe_fields(collect_fields(data.get("filterConfig", {}), ["filterConfig"]))
    ext = defn / "reportExtensions.json"
    if ext.exists():
        data = _load_json(ext, rep)
        for ent in data.get("entities", []):
            for m in ent.get("measures", []):
                rep.extension_measures.append(RExtMeasure(ent.get("name", ""), m.get("name", ""), m.get("expression", "")))
    order: list[str] = []
    pj = defn / "pages" / "pages.json"
    if pj.exists():
        order = _load_json(pj, rep).get("pageOrder", [])
    page_dirs = [p for p in (defn / "pages").glob("*") if p.is_dir()] if (defn / "pages").exists() else []
    page_dirs.sort(key=lambda p: order.index(p.name) if p.name in order else 10_000)
    for idx, pdir in enumerate(page_dirs):
        pjson = pdir / "page.json"
        pdata = _load_json(pjson, rep) if pjson.exists() else {}
        page = RPage(pdata.get("name", pdir.name), pdata.get("displayName", pdir.name), file=str(pjson), ordinal=idx)
        page.filters = _dedupe_fields(collect_fields(pdata.get("filterConfig", {}), ["filterConfig"]))
        for vdir in sorted((pdir / "visuals").glob("*")) if (pdir / "visuals").exists() else []:
            vj = vdir / "visual.json"
            if not vj.exists():
                continue
            vdata = _load_json(vj, rep)
            vis = vdata.get("visual") or {}
            if not vis and "visualGroup" in vdata:
                continue  # groups contain no fields
            fields = _dedupe_fields(collect_fields(vis, ["visual"]) + collect_fields(vdata.get("filterConfig", {}), ["filterConfig"]))
            vtype = vis.get("visualType", "")
            v = RVisual(vdata.get("name", vdir.name), _visual_title(vis, _describe(vtype, fields)), vtype, fields, str(vj), vdata.get("position", {}))
            page.visuals.append(v)
        rep.pages.append(page)
    if not rep.pages:
        rep.warnings.append("no pages found in PBIR definition")
    return rep


def _load_json(path: Path, rep: Report) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as ex:
        rep.warnings.append(f"{path.name}: invalid JSON ({ex})")
        return {}


def _read_dataset_reference(folder: Path, rep: Report) -> None:
    pbir = folder / "definition.pbir"
    if not pbir.exists():
        return
    data = _load_json(pbir, rep)
    ref = data.get("datasetReference", {})
    if ref.get("byPath"):
        p = ref["byPath"].get("path", "")
        rep.model_ref = Path(p.replace("\\", "/")).name.replace(".SemanticModel", "").replace(".Dataset", "")
        rep.model_ref_kind = "byPath"
    elif ref.get("byConnection"):
        bc = ref["byConnection"]
        cs = bc.get("connectionString") or ""
        m = re.search(r'initial catalog\s*=\s*"?([^";]+)"?', cs, re.IGNORECASE)
        rep.model_ref = m.group(1).strip() if m else (bc.get("pbiModelDatabaseName") or "")
        rep.model_ref_kind = "byConnection"


# --------------------------------------------------------------------------- legacy
def _maybe_json(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {}
    return v or {}


def parse_legacy_layout(layout: dict, name: str, path: str, fmt: str) -> Report:
    rep = Report(name, path, fmt)
    rep.filters = _dedupe_fields(collect_fields(_maybe_json(layout.get("filters")), ["filters"]))
    for idx, sec in enumerate(sorted(layout.get("sections", []), key=lambda s: s.get("ordinal", 0))):
        page = RPage(sec.get("name", f"page{idx}"), sec.get("displayName", f"Page {idx + 1}"), file=path, ordinal=idx)
        page.filters = _dedupe_fields(collect_fields(_maybe_json(sec.get("filters")), ["filters"]))
        for vc_i, vc in enumerate(sec.get("visualContainers", [])):
            cfg = _maybe_json(vc.get("config"))
            sv = cfg.get("singleVisual") or {}
            if not sv:
                continue
            fields = collect_fields(sv.get("prototypeQuery", {}), ["prototypeQuery"])
            fields += collect_fields({k: v for k, v in sv.items() if k in ("objects",)}, [])
            fields += collect_fields(_maybe_json(vc.get("filters")), ["filters"])
            fields = _dedupe_fields(fields)
            # map role names from projections
            roles = {}
            for role, items in (sv.get("projections") or {}).items():
                for it in items:
                    roles[it.get("queryRef")] = role
            sel = (sv.get("prototypeQuery") or {}).get("Select", [])
            aliases = {f["Name"]: f["Entity"] for f in (sv.get("prototypeQuery") or {}).get("From", []) if "Name" in f}
            for s in sel:
                role = roles.get(s.get("Name"))
                if not role:
                    continue
                for f in collect_fields(s, ["prototypeQuery"], aliases):
                    for ex in fields:
                        if ex.entity == f.entity and ex.property == f.property and ex.usage == "field":
                            ex.usage = role
            vtype = sv.get("visualType", "")
            vid = cfg.get("name", f"{page.id}_{vc_i}")
            pos = {k: vc.get(k) for k in ("x", "y", "width", "height") if k in vc}
            page.visuals.append(RVisual(vid, _visual_title(sv, _describe(vtype, fields)), vtype, fields, path, pos))
        rep.pages.append(page)
    return rep


def load_legacy_report_json(folder: str | Path) -> Report:
    folder = Path(folder)
    rj = folder / "report.json"
    layout = json.loads(rj.read_text(encoding="utf-8-sig"))
    rep = parse_legacy_layout(layout, folder.name.replace(".Report", ""), str(rj), "pbir-legacy")
    _read_dataset_reference(folder, rep)
    return rep


def load_pbix(path: str | Path) -> Report:
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        layout_name = next((n for n in names if n.replace("\\", "/") == "Report/Layout"), None)
        if layout_name is None:
            raise ValueError(f"{path.name}: Report/Layout not found (is this a .pbix?)")
        raw = z.read(layout_name)
        has_model = any(n == "DataModel" for n in names)
        conn = z.read("Connections").decode("utf-8", "ignore") if "Connections" in names else ""
    text = raw.decode("utf-16-le", errors="ignore").lstrip("\ufeff")
    layout = json.loads(text)
    rep = parse_legacy_layout(layout, path.stem, str(path), "pbix")
    if has_model:
        rep.model_ref = path.stem
        rep.model_ref_kind = "embedded"
        rep.warnings.append(f"{path.name}: embedded data model is binary - save as PBIP (TMDL) to analyse the model; visuals are matched by name")
    elif conn:
        m = re.search(r'initial catalog\s*=\s*\\?"?([^";\\]+)', conn, re.IGNORECASE)
        if m:
            rep.model_ref = m.group(1)
            rep.model_ref_kind = "byConnection"
    return rep


def load_report(path: str | Path) -> Report:
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".pbix":
        return load_pbix(p)
    if p.is_dir():
        if (p / "definition" / "pages").exists() or (p / "definition" / "report.json").exists():
            return load_pbir(p)
        if (p / "report.json").exists():
            return load_legacy_report_json(p)
    raise FileNotFoundError(f"no PBIR definition, report.json or .pbix found at {path}")
