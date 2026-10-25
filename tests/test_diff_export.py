import json
import zipfile

from conftest import NET_AMOUNT

from lineagelens import analysis
from lineagelens.diff import run_diff, to_markdown
from lineagelens.export import export, to_csv, write


def test_diff_sample_builds(graph, samples):
    res = run_diff(samples / "dbt" / "target" / "manifest.json", samples / "dbt_changed" / "target" / "manifest.json", base=graph)
    assert res["breaking"] is True
    s = res["summary"]
    assert s["changes"] == 4
    assert s["visuals"] == 7 and s["visuals_breaking"] == 4
    kinds = {c["change"] for c in res["changes"]}
    assert {"drop", "rename"} <= kinds
    md = to_markdown(res)
    assert md.startswith("#") and "|" in md


def test_diff_identical_is_clean(graph, samples):
    m = samples / "dbt" / "target" / "manifest.json"
    res = run_diff(m, m, base=graph)
    assert res["breaking"] is False and res["summary"]["changes"] == 0


def test_exports_all_formats(graph, tmp_path):
    res = analysis.impact(graph, [NET_AMOUNT])
    csv_text = to_csv(res)
    assert csv_text.splitlines()[0].lower().startswith("impact,confidence,type,object")
    assert len(csv_text.splitlines()) > 20

    data, media, ext = export(res, "json")
    assert ext == "json" and json.loads(data)["summary"]["total"] == 28

    p = write(res, tmp_path / "r.xlsx")
    with zipfile.ZipFile(p) as z:
        assert any(n.startswith("xl/worksheets/") for n in z.namelist())

    html = write(res, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "<html" in html.lower() and "Net Sales" in html
    assert "http://" not in html and "https://" not in html.replace("https://github.com", "")  # self-contained
