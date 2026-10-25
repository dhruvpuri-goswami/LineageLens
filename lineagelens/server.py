"""FastAPI backend: JSON API + the bundled single-page app. Binds to localhost only by default."""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, analysis, store
from .builder import build
from .config import SAMPLE_CONFIG, SAMPLES, SAMPLES_DIR, Config, load_config, sample_name
from .graph import NODE_TYPE_LABELS, LineageGraph
from .links import get_links

STATIC_DIR = Path(__file__).resolve().parent / "static"


class State:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.lock = threading.RLock()
        self.config_path: Path | None = Path(config_path).resolve() if config_path else None
        self.cfg: Config = load_config(self.config_path)
        self.graph: LineageGraph = LineageGraph()
        self.meta: dict[str, Any] = {}
        self._counts: dict | None = None
        self._summary: dict | None = None
        self.scan = {"running": False, "pct": 0, "step": "", "message": "", "log": [], "error": None,
                     "started": None, "finished": None}

    @property
    def is_sample(self) -> bool:
        return sample_name(self.config_path) is not None

    @property
    def sample_name(self) -> str | None:
        return sample_name(self.config_path)

    # -------------------------------------------------- graph lifecycle
    def load_or_scan(self) -> None:
        db = self.cfg.db_path
        if db.exists():
            try:
                g, meta = store.load(db)
                self._set(g, meta)
                return
            except Exception:  # corrupted / old schema -> rescan
                pass
        self.run_scan()

    def _set(self, g: LineageGraph, meta: dict) -> None:
        with self.lock:
            self.graph, self.meta = g, meta
            self._counts, self._summary = None, None

    @property
    def counts(self) -> dict:
        with self.lock:
            if self._counts is None:
                self._counts = analysis.downstream_counts(self.graph)
            return self._counts

    def run_scan(self) -> None:
        s = self.scan
        s.update(running=True, pct=0, step="starting", message="Starting scan", log=[], error=None, started=time.time(), finished=None)

        def progress(step: str, pct: int, msg: str) -> None:
            s.update(step=step, pct=pct, message=msg)
            s["log"].append({"t": time.time(), "step": step, "pct": pct, "message": msg})

        try:
            cfg = load_config(self.config_path)
            res = build(cfg, progress)
            meta = {"warnings": res.warnings, "stats": res.stats, "sources": res.sources, "scanned_at": res.finished,
                    "duration": round(res.finished - res.started, 2), "project_name": cfg.project_name,
                    "config_path": str(self.config_path or SAMPLE_CONFIG), "version": __version__}
            progress("save", 98, f"Saving graph to {cfg.db_path}")
            try:
                store.save(cfg.db_path, res.graph, meta)
            except OSError as e:
                progress("save", 98, f"Could not save database: {e}")
            with self.lock:
                self.cfg = cfg
            self._set(res.graph, meta)
            progress("done", 100, f"Scan complete: {len(res.graph)} objects, {res.stats.get('edges_by_kind', {}).get('flow', 0)} lineage links")
        except Exception as e:
            s["error"] = f"{type(e).__name__}: {e}"
            s["log"].append({"t": time.time(), "step": "error", "pct": s["pct"], "message": traceback.format_exc(limit=3)})
        finally:
            s["running"] = False
            s["finished"] = time.time()

    def start_scan(self) -> bool:
        if self.scan["running"]:
            return False
        self.scan["running"] = True
        threading.Thread(target=self.run_scan, daemon=True).start()
        return True

    def summary(self) -> dict:
        with self.lock:
            if self._summary is None:
                self._summary = analysis.summary(self.graph, self.meta.get("warnings", []), self.counts)
            return {**self._summary, "meta": {k: v for k, v in self.meta.items() if k != "warnings"},
                    "project_name": self.cfg.project_name, "is_sample": self.is_sample, "sample_name": self.sample_name}


def _node_or_404(g: LineageGraph, node_id: str):
    n = g.node(node_id)
    if n is None:
        hits = analysis.find_nodes(g, node_id, limit=1)
        if not hits:
            raise HTTPException(404, f"Unknown object: {node_id}")
        n = hits[0]
    return n


def create_app(config_path: str | Path | None = None, scan_on_start: bool = True) -> FastAPI:
    app = FastAPI(title="LineageLens", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    state = State(config_path)
    app.state.ll = state
    if scan_on_start:
        state.load_or_scan()

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__, "nodes": len(state.graph), "links": get_links()}

    @app.get("/api/summary")
    def summary():
        return state.summary()

    @app.get("/api/nodes")
    def nodes(types: str | None = None):
        tset = set(types.split(",")) if types else None
        out = []
        for n in state.graph.nodes():
            if tset and n.type not in tset:
                continue
            out.append({"id": n.id, "type": n.type, "name": n.name, "parent": n.parent, "container": n.container,
                        "display": analysis.display_name(n), "relation": n.data.get("relation", ""),
                        "visuals": state.counts.get(n.id, {}).get("visuals", 0)})
        return {"nodes": out, "type_labels": NODE_TYPE_LABELS}

    @app.get("/api/node/{node_id:path}")
    def node(node_id: str):
        g = state.graph
        n = _node_or_404(g, node_id)

        def link(other, d):
            o = g.node(other)
            return {"id": other, "type": o.type, "display": analysis.display_name(o), **{k: d.get(k) for k in ("confidence", "impact", "reason")}}
        d = n.to_dict()
        d.update(display=analysis.display_name(n), type_label=NODE_TYPE_LABELS.get(n.type, n.type),
                 upstream=[link(p, e) for p, e in g.flow_predecessors(n.id)],
                 downstream=[link(s, e) for s, e in g.flow_successors(n.id)],
                 children=[{"id": c, "type": g.node(c).type, "display": analysis.display_name(g.node(c))} for c in g.children(n.id)],
                 counts=state.counts.get(n.id, {}))
        return d

    def _impact(ids: list[str], change: str) -> dict:
        g = state.graph
        resolved = [_node_or_404(g, i).id for i in ids]
        return analysis.impact(g, resolved, change)

    @app.get("/api/impact")
    def impact_get(id: list[str] = Query(...), change: str = "drop"):
        return _impact(id, change)

    @app.post("/api/impact")
    def impact_post(body: dict = Body(...)):
        ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
        if not ids:
            raise HTTPException(400, "ids required")
        return _impact(ids, body.get("change", "drop"))

    @app.get("/api/upstream")
    def upstream(id: str):
        n = _node_or_404(state.graph, id)
        return analysis.upstream(state.graph, n.id)

    @app.get("/api/reports")
    def reports():
        g = state.graph
        out = []
        for r in g.nodes("report"):
            pages = []
            for pid in g.children(r.id):
                p = g.node(pid)
                if p.type != "page":
                    continue
                vis = [{"id": v, "name": g.node(v).name, "visual_type": g.node(v).data.get("visual_type", ""),
                        "fields": len(g.node(v).data.get("fields", []))} for v in g.children(pid) if g.node(v).type == "visual"]
                pages.append({"id": pid, "name": p.name, "ordinal": p.data.get("ordinal", 0), "visuals": sorted(vis, key=lambda x: x["name"])})
            out.append({"id": r.id, "name": r.name, "format": r.data.get("format"), "model": r.data.get("model"),
                        "pages": sorted(pages, key=lambda x: x["ordinal"])})
        return out

    @app.get("/api/catalog")
    def catalog(kind: str | None = None):
        return {"rows": analysis.catalog(state.graph, kind, state.counts), "type_labels": NODE_TYPE_LABELS}

    @app.post("/api/scan")
    def scan():
        started = state.start_scan()
        return {"started": started, "status": state.scan}

    @app.get("/api/scan/status")
    def scan_status():
        return {**state.scan, "log": state.scan["log"][-200:]}

    @app.get("/api/config")
    def get_config():
        path = state.config_path or SAMPLE_CONFIG
        text = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
        return {"path": str(path), "is_sample": state.is_sample, "sample_name": state.sample_name, "yaml": text,
                "config": state.cfg.to_public_dict(), "samples_dir": str(SAMPLES_DIR),
                "samples": [{"name": k, "description": d, "path": str(c)} for k, (c, d) in SAMPLES.items()]}

    @app.put("/api/config")
    def put_config(body: dict = Body(...)):
        """Switch to another config file, or save YAML to a path and switch to it."""
        path = body.get("path")
        text = body.get("yaml")
        if not path:
            raise HTTPException(400, "path required")
        p = Path(path).expanduser().resolve()
        if text is not None:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as e:
                raise HTTPException(400, f"Invalid YAML: {e}")
            if sample_name(p) is not None:
                raise HTTPException(400, "The bundled sample config is read-only; save to another path.")
            data = yaml.safe_load(text) or {}
            if state.is_sample and isinstance(data, dict) and not data.get("base_dir"):
                # Saving a copy of the bundled sample elsewhere: keep its relative paths pointing at the samples.
                src = SAMPLES[state.sample_name or "standard"][0]
                text = f"base_dir: {json.dumps(str(src.parent))}\n" + text
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        if not p.exists():
            raise HTTPException(404, f"Config not found: {p}")
        try:
            cfg = load_config(p)
        except Exception as e:
            raise HTTPException(400, f"Config error: {e}")
        with state.lock:
            state.config_path, state.cfg = p, cfg
        return {"ok": True, "config": cfg.to_public_dict()}

    @app.post("/api/config/sample")
    def use_sample(body: dict | None = Body(None)):
        name = (body or {}).get("name") or "standard"
        if name not in SAMPLES:
            raise HTTPException(400, f"Unknown sample '{name}'. Choose one of: {', '.join(SAMPLES)}")
        path = None if name == "standard" else SAMPLES[name][0].resolve()
        with state.lock:
            state.config_path, state.cfg = path, load_config(path)
        state.start_scan()
        return {"ok": True}

    @app.get("/api/export")
    def export_impact(id: list[str] = Query(...), change: str = "drop", format: str = "html"):
        from .export import export
        res = _impact(id, change)
        data, media, ext = export(res, format)
        name = "".join(ch if ch.isalnum() else "_" for ch in res["start"][0]["display"])[:60] if res["start"] else "impact"
        return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="impact_{name}.{ext}"'})

    @app.post("/api/diff")
    def diff(body: dict = Body(...)):
        from .diff import run_diff, to_markdown
        old, new = body.get("old"), body.get("new")
        if body.get("sample"):
            old = str(SAMPLES_DIR / "dbt" / "target" / "manifest.json")
            new = str(SAMPLES_DIR / "dbt_changed" / "target" / "manifest.json")
        if not old or not new:
            raise HTTPException(400, "old and new paths required")
        for p in (old, new):
            if not Path(p).expanduser().exists():
                raise HTTPException(404, f"Not found: {p}")
        try:
            res = run_diff(Path(old).expanduser(), Path(new).expanduser(), base=state.graph, base_cfg=state.cfg)
        except Exception as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")
        for c in res["changes"]:  # keep payload small
            if c.get("impact"):
                c["impact"] = {"summary": c["impact"]["summary"]}
        res["markdown"] = to_markdown(res)
        res["old"], res["new"] = str(old), str(new)
        return res

    # -------------------------------------------------- SPA
    if (STATIC_DIR / "index.html").exists():
        if (STATIC_DIR / "assets").exists():
            app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404)
            f = (STATIC_DIR / full_path).resolve()
            if full_path and f.is_file() and STATIC_DIR in f.parents:
                return FileResponse(f)
            return FileResponse(STATIC_DIR / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def no_ui():
            return HTMLResponse("<h1>LineageLens API</h1><p>The web UI has not been built. Run <code>npm run build</code> in "
                                "<code>frontend/</code>. API docs: <a href='/api/docs'>/api/docs</a></p>")
    return app
