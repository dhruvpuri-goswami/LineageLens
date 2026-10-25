"""Configuration (YAML). Relative paths are resolved against the config file's folder."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
SAMPLES_DIR = PACKAGE_DIR / "samples"
SAMPLE_CONFIG = SAMPLES_DIR / "lineagelens.sample.yml"
LARGE_SAMPLES_DIR = PACKAGE_DIR / "samples_large"
LARGE_SAMPLE_CONFIG = LARGE_SAMPLES_DIR / "lineagelens.sample.yml"
#: Bundled synthetic samples: name -> (config path, short description)
SAMPLES: dict[str, tuple[Path, str]] = {
    "standard": (SAMPLE_CONFIG, "Northwind Outfitters - small retail estate (1 semantic model, 2 reports)"),
    "large": (LARGE_SAMPLE_CONFIG, "Helios Retail Group - large estate (46 dbt models, 3 semantic models, 7 reports, 150+ visuals)"),
}


def sample_name(path: str | Path | None) -> str | None:
    """Return 'standard' / 'large' if *path* is one of the bundled sample configs (None = standard)."""
    if path is None:
        return "standard"
    p = Path(path).resolve()
    for name, (cfg, _) in SAMPLES.items():
        if p == cfg.resolve():
            return name
    return None


def user_data_dir() -> Path:
    base = os.environ.get("LINEAGELENS_HOME")
    if base:
        p = Path(base)
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        p = Path(os.environ["LOCALAPPDATA"]) / "LineageLens"
    else:
        p = Path.home() / ".lineagelens"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class DbtSource:
    manifest: Path
    catalog: Path | None = None
    project_dir: Path | None = None


@dataclass
class Config:
    path: Path | None
    base_dir: Path
    project_name: str = "LineageLens project"
    dbt: list[DbtSource] = field(default_factory=list)
    view_dirs: list[Path] = field(default_factory=list)
    default_database: str = ""
    default_schema: str = ""
    live_snowflake: dict = field(default_factory=dict)
    semantic_models: list[Path] = field(default_factory=list)
    reports: list[Path] = field(default_factory=list)
    pbix: list[Path] = field(default_factory=list)
    search_dirs: list[Path] = field(default_factory=list)
    calcdependency_csv: dict[str, Path] = field(default_factory=dict)
    report_model_map: dict[str, str] = field(default_factory=dict)
    fabric: dict = field(default_factory=dict)
    naming: dict = field(default_factory=dict)
    database: Path | None = None
    raw: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        if self.database:
            return self.database
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.project_name.lower()).strip("_") or "project"
        return user_data_dir() / f"{safe}.db"

    def to_public_dict(self) -> dict:
        def s(p):
            return str(p) if p else None
        return {
            "path": s(self.path), "project_name": self.project_name,
            "dbt": [{"manifest": s(d.manifest), "catalog": s(d.catalog), "project_dir": s(d.project_dir)} for d in self.dbt],
            "snowflake": {"view_dirs": [s(p) for p in self.view_dirs], "default_database": self.default_database,
                          "default_schema": self.default_schema, "live": {k: v for k, v in self.live_snowflake.items()}},
            "powerbi": {"semantic_models": [s(p) for p in self.semantic_models], "reports": [s(p) for p in self.reports],
                        "pbix": [s(p) for p in self.pbix], "search_dirs": [s(p) for p in self.search_dirs],
                        "calcdependency_csv": {k: s(v) for k, v in self.calcdependency_csv.items()},
                        "report_model_map": self.report_model_map},
            "naming": self.naming, "database": s(self.db_path),
        }


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def parse_config(data: dict, base_dir: Path, path: Path | None = None) -> Config:
    if data.get("base_dir"):
        bd = Path(os.path.expandvars(os.path.expanduser(str(data["base_dir"]))))
        base_dir = bd if bd.is_absolute() else (base_dir / bd).resolve()

    def rp(v) -> Path | None:
        if not v:
            return None
        p = Path(os.path.expandvars(os.path.expanduser(str(v))))
        return p if p.is_absolute() else (base_dir / p).resolve()

    cfg = Config(path=path, base_dir=base_dir, raw=data)
    cfg.project_name = data.get("project_name") or cfg.project_name
    for d in _as_list(data.get("dbt")):
        if isinstance(d, str):
            d = {"project_dir": d}
        pdir = rp(d.get("project_dir"))
        manifest = rp(d.get("manifest")) or (pdir / "target" / "manifest.json" if pdir else None)
        catalog = rp(d.get("catalog")) or (pdir / "target" / "catalog.json" if pdir else None)
        if manifest:
            cfg.dbt.append(DbtSource(manifest, catalog, pdir))
    sf = data.get("snowflake") or {}
    cfg.view_dirs = [rp(p) for p in _as_list(sf.get("view_dirs"))]
    cfg.default_database = sf.get("default_database", "") or ""
    cfg.default_schema = sf.get("default_schema", "") or ""
    cfg.live_snowflake = sf.get("live") or {}
    pbi = data.get("powerbi") or {}
    cfg.semantic_models = [rp(p) for p in _as_list(pbi.get("semantic_models"))]
    cfg.reports = [rp(p) for p in _as_list(pbi.get("reports"))]
    cfg.pbix = [rp(p) for p in _as_list(pbi.get("pbix"))]
    cfg.search_dirs = [rp(p) for p in _as_list(pbi.get("search_dirs"))]
    cdc = pbi.get("calcdependency_csv") or {}
    if isinstance(cdc, dict):
        cfg.calcdependency_csv = {k: rp(v) for k, v in cdc.items()}
    cfg.report_model_map = dict(pbi.get("report_model_map") or {})
    cfg.fabric = pbi.get("fabric") or {}
    cfg.naming = data.get("naming") or {}
    cfg.database = rp(data.get("database"))
    return cfg


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path).resolve() if path else SAMPLE_CONFIG
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return parse_config(data, p.parent, p)


TEMPLATE = """# LineageLens configuration. Paths are relative to this file.
project_name: My analytics estate

dbt:
  - project_dir: ../my-dbt-project          # expects target/manifest.json (+ target/catalog.json)
    # manifest: path/to/manifest.json
    # catalog: path/to/catalog.json

snowflake:
  view_dirs: []                              # folders of CREATE VIEW .sql scripts (views not managed by dbt)
  default_database: ANALYTICS
  default_schema: GOLD
  live:
    enabled: false                           # read-only metadata pull; credentials from SNOWFLAKE_* env vars
    databases: [ANALYTICS]
    schemas: []

powerbi:
  semantic_models: []                        # *.SemanticModel folders (TMDL) or model.bim files
  reports: []                                # *.Report folders (PBIR or PBIR-Legacy report.json)
  pbix: []                                   # .pbix files (report layer only)
  search_dirs: [../powerbi]                  # auto-discover *.SemanticModel / *.Report / *.pbix below these folders
  calcdependency_csv: {}                     # {model name: INFO.CALCDEPENDENCY export .csv}
  report_model_map: {}                       # {report name: semantic model name} for thin reports
  fabric:                                    # EXPERIMENTAL read-only pull of TMDL/PBIR via Fabric REST API
    enabled: false
    workspaces: []                           # workspace GUIDs; auth via FABRIC_TOKEN env var or azure-identity

naming:
  case_insensitive: true
  strip_prefixes: []                         # e.g. [DIM_, FCT_]
  strip_suffixes: []                         # e.g. [_KEY]
  regex_map: []                              # e.g. [{pattern: "^AMT_", replace: "AMOUNT_"}]
  enable_fuzzy: true
  fuzzy_threshold: 90

# database: .lineagelens/lineage.db          # default: per-user data folder
# base_dir: C:/analytics                     # optional: resolve relative paths against this folder instead of this file's folder
"""
