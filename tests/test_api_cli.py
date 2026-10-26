from conftest import NET_AMOUNT
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from lineagelens.cli import app as cli_app
from lineagelens.server import create_app


def _client():
    return TestClient(create_app(None, scan_on_start=True))


def test_api_endpoints():
    c = _client()
    assert c.get("/api/health").json()["nodes"] > 150
    s = c.get("/api/summary").json()
    assert s["is_sample"] is True
    r = c.get("/api/impact", params={"id": "fct_sales.NET_AMOUNT"}).json()
    assert r["summary"]["visuals"] == 12
    r = c.post("/api/impact", json={"ids": [NET_AMOUNT], "change": "logic"}).json()
    assert r["change"] == "logic"
    assert c.get("/api/upstream", params={"id": "pbi:RetailSales:rls:EMEA Only"}).status_code == 200
    reps = c.get("/api/reports").json()
    assert {r["name"] for r in reps} == {"RetailSales", "RegionalScorecard"}
    assert c.get("/api/catalog", params={"kind": "rls_role"}).json()["rows"]
    assert c.get("/api/node/" + NET_AMOUNT).status_code == 200
    assert c.get("/api/impact", params={"id": "does_not_exist_xyz_123"}).status_code == 404
    for fmt in ("html", "csv", "json", "xlsx"):
        resp = c.get("/api/export", params={"id": NET_AMOUNT, "format": fmt})
        assert resp.status_code == 200 and len(resp.content) > 200
    d = c.post("/api/diff", json={"sample": True}).json()
    assert d["breaking"] is True and "markdown" in d


def test_api_config_sample_read_only(tmp_path):
    c = _client()
    cfg = c.get("/api/config").json()
    bad = c.put("/api/config", json={"path": cfg["path"], "yaml": cfg["yaml"]})
    assert bad.status_code == 400
    # Saving a copy elsewhere keeps the sample's relative paths working (base_dir injected).
    target = tmp_path / "copy.yml"
    ok = c.put("/api/config", json={"path": str(target), "yaml": cfg["yaml"]})
    assert ok.status_code == 200, ok.text
    assert target.read_text(encoding="utf-8").startswith("base_dir:")
    assert c.put("/api/config", json={"path": str(tmp_path / "nope.yml")}).status_code == 404


def test_spa_served():
    c = _client()
    r = c.get("/impact")
    assert r.status_code == 200 and "<div id=\"root\">" in r.text


runner = CliRunner()


def test_cli_impact_and_upstream():
    r = runner.invoke(cli_app, ["impact", "fct_sales.NET_AMOUNT"])
    assert r.exit_code == 0, r.output
    assert "12 visuals" in r.output and "Net Sales" in r.output
    r = runner.invoke(cli_app, ["upstream", "pbi:RetailSales:rls:Regional Manager"])
    assert r.exit_code == 0 and "MANAGER_EMAIL" in r.output


def test_cli_export_and_init(tmp_path):
    out = tmp_path / "rep.html"
    r = runner.invoke(cli_app, ["export", "fct_sales.NET_AMOUNT", "-o", str(out)])
    assert r.exit_code == 0 and out.exists()
    yml = tmp_path / "lineagelens.yml"
    assert runner.invoke(cli_app, ["init", str(yml)]).exit_code == 0
    assert runner.invoke(cli_app, ["init", str(yml)]).exit_code == 1


def test_cli_diff_fails_on_breaking(tmp_path, samples):
    md = tmp_path / "report.md"
    r = runner.invoke(cli_app, ["diff", str(samples / "dbt" / "target" / "manifest.json"),
                                str(samples / "dbt_changed" / "target" / "manifest.json"), "-m", str(md)])
    assert r.exit_code == 1
    assert md.exists() and "breaking" in md.read_text(encoding="utf-8").lower()
    r = runner.invoke(cli_app, ["diff", str(samples / "dbt" / "target" / "manifest.json"),
                                str(samples / "dbt_changed" / "target" / "manifest.json"), "--fail-on", "never"])
    assert r.exit_code == 0
