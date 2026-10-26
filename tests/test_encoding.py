"""Encoding regressions: Windows code pages, BOMs and plain-text reports."""
import io
import re
import shutil
import sys

from typer.testing import CliRunner

from lineagelens import cli
from lineagelens.builder import build
from lineagelens.config import load_config
from lineagelens.diff import run_diff, to_markdown

BOM = b"\xef\xbb\xbf"
# Pictographs, dingbats and symbols that legacy code pages such as cp1252 cannot encode.
EMOJI = re.compile("[\u2190-\u21ff\u2300-\u27bf\u2b00-\u2bff\ufe0f\U0001f000-\U0001faff]")


def _changed(samples):
    return samples / "dbt" / "target" / "manifest.json", samples / "dbt_changed" / "target" / "manifest.json"


def test_markdown_report_is_plain_text(graph, samples):
    old, new = _changed(samples)
    md = to_markdown(run_diff(old, new, base=graph))
    assert md.splitlines()[0] == "## LineageLens impact report: breaking change"
    assert "**Status: BREAKING.**" in md
    assert "| Rename |" in md and "| Drop |" in md and "**Yes**" in md
    # Markup is plain text: only object names or details taken from the inputs may be non-ASCII.
    assert not EMOJI.search(md.replace("\u2192", "->").replace("\u203a", ">"))
    clean = to_markdown(run_diff(old, old, base=graph))
    assert clean.startswith("## LineageLens impact report: no breaking change") and "**Status: OK.**" in clean


def test_cli_diff_markdown_is_utf8(tmp_path, samples):
    old, new = _changed(samples)
    md = tmp_path / "report.md"
    r = CliRunner().invoke(cli.app, ["diff", str(old), str(new), "-m", str(md)])
    assert r.exit_code == 1
    text = md.read_bytes().decode("utf-8")  # strict: must be valid UTF-8, no BOM
    assert not text.startswith("\ufeff") and "breaking change" in text
    assert text.splitlines()[0] in r.output


def test_safe_console_never_raises_on_legacy_code_page(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict", newline="\n", write_through=True)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    cli._safe_console()
    print("type NUMBER \u2192 FLOAT \U0001f534 Sales \u203a Overview")  # cp1252 has the chevron, not the arrow or emoji
    stream.flush()
    assert raw.getvalue() == b"type NUMBER ? FLOAT ? Sales \x9b Overview\n"


def test_inputs_with_bom_parse_identically(tmp_path, samples, scan):
    """Files saved by Windows tools (Notepad, SSMS, Power BI Desktop) often start with a UTF-8 BOM."""
    root = tmp_path / "s"
    shutil.copytree(samples, root, ignore=shutil.ignore_patterns("dbt_changed"))
    targets = [root / "lineagelens.sample.yml", root / "dbt" / "target" / "manifest.json", root / "dbt" / "target" / "catalog.json",
               root / "dbt" / "dbt_project.yml"]
    targets += list((root / "snowflake_views").glob("*.sql"))
    targets += list((root / "powerbi").rglob("*.tmdl")) + list((root / "powerbi").rglob("*.json"))
    targets += list((root / "powerbi").rglob("*.pbir")) + list((root / "powerbi").rglob("*.pbism"))
    assert len(targets) > 10
    for f in targets:
        f.write_bytes(BOM + f.read_bytes())
    res = build(load_config(root / "lineagelens.sample.yml"))
    assert res.graph.g.number_of_nodes() == scan.graph.g.number_of_nodes()
    assert res.graph.g.number_of_edges() == scan.graph.g.number_of_edges()
    assert len(res.warnings) == len(scan.warnings)
