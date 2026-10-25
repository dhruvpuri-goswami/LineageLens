"""LineageLens command line interface."""
from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import List, Optional

import typer

from . import __version__, analysis, store
from .builder import build
from .config import SAMPLE_CONFIG, TEMPLATE, load_config
from .graph import BREAKS

app = typer.Typer(add_completion=False, no_args_is_help=False, rich_markup_mode=None,
                  help="LineageLens - column-level lineage & impact analysis: dbt / Snowflake -> Power BI visuals. 100% local.")

ConfigOpt = typer.Option(None, "--config", "-c", help="Path to lineagelens.yml (default: bundled sample project)")
SampleOpt = typer.Option(None, "--sample", help="Use a bundled synthetic sample instead of --config: 'standard' or 'large'")


def _pick(config: Optional[Path], sample: Optional[str]) -> Optional[Path]:
    from .config import SAMPLES
    if sample:
        if sample not in SAMPLES:
            _echo_err(f"Unknown sample '{sample}'. Choose: {', '.join(SAMPLES)}")
            raise typer.Exit(2)
        return SAMPLES[sample][0]
    return config


def _echo_err(msg: str) -> None:
    typer.echo(msg, err=True)


def _graph(config: Optional[Path], rescan: bool = False):
    cfg = load_config(config)
    if not rescan and cfg.db_path.exists():
        g, meta = store.load(cfg.db_path)
        return cfg, g, meta
    res = build(cfg)
    meta = {"warnings": res.warnings, "stats": res.stats, "scanned_at": res.finished, "project_name": cfg.project_name}
    try:
        store.save(cfg.db_path, res.graph, meta)
    except OSError:
        pass
    return cfg, res.graph, meta


def _resolve(g, query: str):
    hits = analysis.find_nodes(g, query, limit=8)
    if not hits:
        _echo_err(f"No object matches '{query}'. Try e.g. fct_sales.NET_AMOUNT, 'Sales[Total Net Sales]' or a node id.")
        raise typer.Exit(2)
    if len(hits) > 1 and hits[0].id != query and analysis.display_name(hits[0]).lower() != query.lower():
        _echo_err(f"'{query}' is ambiguous, using {analysis.display_name(hits[0])}. Other matches: "
                  + ", ".join(analysis.display_name(h) for h in hits[1:]))
    return hits[0]


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version", help="Show version")):
    if version:
        typer.echo(f"LineageLens {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def serve(config: Optional[Path] = ConfigOpt, sample: Optional[str] = SampleOpt,
          host: str = typer.Option("127.0.0.1", help="Bind address (keep 127.0.0.1 to stay local)"),
          port: int = typer.Option(8765, help="Port"),
          no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the browser"),
          rescan: bool = typer.Option(False, help="Re-scan sources on start instead of loading the saved graph")):
    """Start the web app (opens your browser)."""
    import uvicorn
    from .server import create_app

    config = _pick(config, sample)
    if rescan:
        cfg = load_config(config)
        if cfg.db_path.exists():
            cfg.db_path.unlink()
    application = create_app(config)
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    typer.echo(f"LineageLens {__version__} running at {url}  (Ctrl+C to stop)")
    if not no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(application, host=host, port=port, log_level="warning")


@app.command()
def scan(config: Optional[Path] = ConfigOpt, sample: Optional[str] = SampleOpt, quiet: bool = typer.Option(False, "-q")):
    """Scan all configured sources and save the lineage graph."""
    config = _pick(config, sample)
    cfg = load_config(config)

    def progress(step, pct, msg):
        if not quiet:
            typer.echo(f"[{pct:3d}%] {msg}")
    res = build(cfg, progress)
    meta = {"warnings": res.warnings, "stats": res.stats, "sources": res.sources, "scanned_at": res.finished,
            "duration": round(res.finished - res.started, 2), "project_name": cfg.project_name,
            "config_path": str(config or SAMPLE_CONFIG), "version": __version__}
    store.save(cfg.db_path, res.graph, meta)
    s = res.stats
    typer.echo(f"Saved {s['nodes']} objects / {s['edges_by_kind'].get('flow', 0)} lineage links to {cfg.db_path}")
    warns = [w for w in res.warnings if w.get("level") != "info"]
    if warns:
        typer.echo(f"{len(warns)} warning(s):")
        for w in warns[:30]:
            typer.echo(f"  - [{w.get('source', '')}] {w.get('message', '')}")


@app.command()
def impact(column: List[str] = typer.Argument(..., help="Column(s) / objects, e.g. fct_sales.NET_AMOUNT"),
           change: str = typer.Option("drop", help="drop | rename | type | logic"),
           config: Optional[Path] = ConfigOpt,
           output: Optional[Path] = typer.Option(None, "-o", "--output", help="Write report (.html .csv .xlsx .json)"),
           as_json: bool = typer.Option(False, "--json", help="Print JSON"),
           rescan: bool = typer.Option(False, help="Re-scan first")):
    """Show everything downstream of a column (measures, RLS, visuals...)."""
    _, g, _ = _graph(config, rescan)
    ids = [_resolve(g, c).id for c in column]
    res = analysis.impact(g, ids, change)
    if output:
        from .export import write
        write(res, output)
        _echo_err(f"Report written to {output}")
    if as_json:
        res.pop("graph", None)
        typer.echo(json.dumps(res, indent=2, default=str))
        return
    s = res["summary"]
    typer.echo(f"\nImpact of '{res['change_label']}' on {', '.join(x['display'] for x in res['start'])}")
    typer.echo(f"  {s['total']} objects affected  |  {s['breaks']} break  |  {s['visuals']} visuals in {s['reports']} report(s)  |  "
               f"{s['measures']} measures  |  {s['rls_roles']} RLS roles\n")
    for r in res["reports"]:
        typer.echo(f"  REPORT {r['name']}  [{r['impact']}]" + ("  (report filter)" if r.get("report_filter") else ""))
        for p in r["pages"]:
            typer.echo(f"    PAGE {p['name']}" + ("  (page filter)" if p.get("page_filter") else ""))
            for v in p["visuals"]:
                mark = "x" if v["impact"] == BREAKS else "~"
                typer.echo(f"      [{mark}] {v['name']:<32} {v['visual_type']:<18} via {v['via_display']}  ({v['confidence']})")
    for t, label in [("rls_role", "RLS roles"), ("measure", "Measures"), ("calc_column", "Calculated columns"),
                     ("calc_group_item", "Calc group items"), ("field_parameter", "Field parameters"), ("pbi_model_column", "Model columns")]:
        lst = res["groups"].get(t, [])
        if lst:
            typer.echo(f"\n  {label}:")
            for e in lst:
                typer.echo(f"    [{'x' if e['impact'] == BREAKS else '~'}] {e['display']}  ({e['confidence']})")
    typer.echo("\n  [x] breaks   [~] values may change")


@app.command()
def upstream(obj: str = typer.Argument(..., help="Visual, measure, column, page or report"),
             config: Optional[Path] = ConfigOpt, as_json: bool = typer.Option(False, "--json"),
             rescan: bool = typer.Option(False)):
    """Trace an object back to its warehouse source columns."""
    _, g, _ = _graph(config, rescan)
    n = _resolve(g, obj)
    res = analysis.upstream(g, n.id)
    if as_json:
        res.pop("graph", None)
        typer.echo(json.dumps(res, indent=2, default=str))
        return
    typer.echo(f"\nUpstream of {analysis.display_name(n)}: {res['summary']['total']} objects")
    order = ["measure", "calc_column", "pbi_model_column", "snowflake_view_column", "dbt_model_column", "snowflake_table_column", "dbt_source_column"]
    for t in order:
        lst = res["groups"].get(t, [])
        if lst:
            typer.echo(f"\n  {lst[0]['type_label']}:")
            for e in lst:
                typer.echo(f"    {'*' if e['impact'] == BREAKS else '-'} {e['display']}")
    typer.echo("\n  * direct dependency   - filter/join dependency")


@app.command("export")
def export_cmd(column: List[str] = typer.Argument(...), output: Path = typer.Option(..., "-o", "--output"),
               change: str = typer.Option("drop"), fmt: Optional[str] = typer.Option(None, "--format", help="csv|xlsx|json|html"),
               config: Optional[Path] = ConfigOpt):
    """Export an impact report to CSV, XLSX, JSON or self-contained HTML."""
    from .export import write
    _, g, _ = _graph(config)
    res = analysis.impact(g, [_resolve(g, c).id for c in column], change)
    write(res, output, fmt)
    typer.echo(f"Wrote {output}")


@app.command()
def diff(old: Path = typer.Argument(..., help="Old version: lineage .db, manifest.json, dbt project dir or config .yml"),
         new: Path = typer.Argument(..., help="New version (same kinds)"),
         config: Optional[Path] = ConfigOpt,
         markdown: Optional[Path] = typer.Option(None, "--markdown", "-m", help="Write markdown summary (e.g. for a PR comment)"),
         output_json: Optional[Path] = typer.Option(None, "--json-out"),
         fail_on: str = typer.Option("breaking", help="breaking | any | never")):
    """Compare two versions and report Power BI impact. Exits 1 on breaking impact (CI friendly)."""
    from .diff import diff_graphs, load_any, to_markdown
    cfg, base, _ = _graph(config)
    res = diff_graphs(load_any(old, cfg), load_any(new, cfg), base)
    md = to_markdown(res)
    if markdown:
        markdown.write_text(md, encoding="utf-8")
        _echo_err(f"Markdown written to {markdown}")
    if output_json:
        output_json.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    typer.echo(md.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8"))
    affected = res["summary"]["visuals"] + res["summary"]["objects"]
    if (fail_on == "breaking" and res["breaking"]) or (fail_on == "any" and affected):
        raise typer.Exit(1)


@app.command()
def init(path: Path = typer.Argument(Path("lineagelens.yml")), force: bool = typer.Option(False)):
    """Create a starter lineagelens.yml."""
    if path.exists() and not force:
        _echo_err(f"{path} exists (use --force)")
        raise typer.Exit(1)
    path.write_text(TEMPLATE, encoding="utf-8")
    typer.echo(f"Created {path}. Edit the paths, then run: lineagelens serve -c {path}")


@app.command()
def samples(dest: Path = typer.Argument(Path("lineagelens-samples"))):
    """Copy the bundled synthetic sample projects (standard + large) to a folder so you can inspect / edit them."""
    import shutil
    from .config import SAMPLES
    for name, (cfg, _) in SAMPLES.items():
        shutil.copytree(cfg.parent, dest / name, dirs_exist_ok=True)
    typer.echo(f"Samples copied to {dest}. Run: lineagelens serve -c {dest / 'standard' / 'lineagelens.sample.yml'}"
               f"  (or {dest / 'large' / 'lineagelens.sample.yml'})")


def run() -> None:
    app()


if __name__ == "__main__":
    run()
