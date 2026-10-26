"""In-app uploads ("Load your data"): validation, safety limits, commit + scan, persistence and removal."""
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lineagelens import uploads
from lineagelens.config import SAMPLES_DIR
from lineagelens.server import create_app
from lineagelens.settings import Settings

H = {"X-Requested-With": "LineageLens"}
SAMPLE_NODES = 212


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LINEAGELENS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _client(scan=False, **kw):
    st = Settings(allowed_hosts=["testserver"], **kw)
    return TestClient(create_app(None, scan_on_start=scan, settings=st), raise_server_exceptions=False)


def _up(c, slot, files, headers=H):
    return c.post(f"/api/upload/files/{slot}", files=[("file", (n, d)) for n, d in files], headers=headers)


def _wait(c, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = c.get("/api/scan/status").json()
        if not s["running"]:
            return s
        time.sleep(0.1)
    raise AssertionError("scan did not finish")


def _sample_files():
    t = SAMPLES_DIR / "dbt" / "target"
    pbi = SAMPLES_DIR / "powerbi"
    return {
        "manifest": [("manifest.json", (t / "manifest.json").read_bytes())],
        "catalog": [("catalog.json", (t / "catalog.json").read_bytes())],
        "sql": [(p.name, p.read_bytes()) for p in sorted((SAMPLES_DIR / "snowflake_views").glob("*.sql"))],
        "powerbi": [("Retail/" + p.relative_to(pbi).as_posix(), p.read_bytes()) for p in sorted(pbi.rglob("*")) if p.is_file()],
    }


def test_state_and_manifest_ok(home):
    c = _client()
    s = c.get("/api/upload").json()
    assert s["allowed"] and s["max_upload_mb"] == 500 and s["workspace"] is None
    r = _up(c, "manifest", _sample_files()["manifest"])
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["status"] == "ok" and "manifest v12" in res["detected"]
    assert (home / "workspace" / ".staging" / "manifest" / "manifest.json").is_file()
    assert r.json()["state"]["staging"]["manifest"][0]["name"] == "manifest.json"
    assert c.delete("/api/upload/files/manifest", headers=H).json()["state"]["staging"]["manifest"] == []


def test_bad_json_and_wrong_schema(home):
    c = _client()
    r = _up(c, "manifest", [("manifest.json", b"{not json")]).json()["results"][0]
    assert r["status"] == "error" and "valid JSON" in r["message"]
    cat = (SAMPLES_DIR / "dbt" / "target" / "catalog.json").read_bytes()
    r = _up(c, "manifest", [("manifest.json", cat)]).json()["results"][0]
    assert r["status"] == "error" and "catalog" in r["message"]
    r = _up(c, "catalog", [("catalog.json", json.dumps({"metadata": {}}).encode())]).json()["results"][0]
    assert r["status"] == "error" and "dbt_schema_version" in r["message"]
    assert not list((home / "workspace" / ".staging").rglob("*.json*")) or \
        all(p.name == "status.json" for p in (home / "workspace" / ".staging").rglob("*.json*"))


def test_extension_allow_list(home):
    c = _client()
    r = _up(c, "sql", [("evil.exe", b"MZ"), ("v.sql", b"create view a.b.c as select 1 x")]).json()
    st = {x["name"]: x["status"] for x in r["results"]}
    assert st == {"evil.exe": "error", "v.sql": "ok"}
    assert not (home / "workspace" / ".staging" / "sql" / "evil.exe").exists()
    r = _up(c, "sql", [("notes.sql", b"select 1")]).json()["results"][0]
    assert r["status"] == "warning"
    r = _up(c, "pbix", [("r.pbix", b"not a zip")]).json()["results"][0]
    assert r["status"] == "error"


@pytest.mark.parametrize("name", ["../../etc/x.sql", "/abs/x.sql", "C:/x/y.sql", "a/../../b.sql", "..\\..\\x.sql"])
def test_path_traversal_rejected(home, name):
    c = _client()
    r = _up(c, "powerbi" if "/" in name or "\\" in name else "sql", [(name, b"create view x as select 1")])
    assert r.status_code == 400, r.text
    assert not list((home.parent).glob("etc")) and not Path("/abs").exists()


def test_safe_relpath_rules():
    from fastapi import HTTPException
    for bad in ["a\x00.sql", "a/\x1fb.sql", "a/b:c.sql", "", "  ", "x/" + "a" * 300]:
        with pytest.raises(HTTPException):
            uploads.safe_relpath(bad, keep_dirs=True)
    assert uploads.safe_relpath("a\\b/./c.tmdl", keep_dirs=True) == "a/b/c.tmdl"
    assert uploads.safe_relpath("dir/manifest.json", keep_dirs=False) == "manifest.json"


def test_path_field_sets_relative_path(home):
    """Browsers that strip folders from file names can send the relative path in a preceding "path" field."""
    c = _client()
    body = (b"--B\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\nP/P.Report/definition.pbir\r\n"
            b"--B\r\nContent-Disposition: form-data; name=\"file\"; filename=\"definition.pbir\"\r\n\r\n{}\r\n--B--\r\n")
    r = c.post("/api/upload/files/powerbi", content=body, headers={**H, "Content-Type": "multipart/form-data; boundary=B"})
    assert r.status_code == 200 and r.json()["results"][0]["reports"] == ["P.Report"], r.text
    bad = body.replace(b"P/P.Report", b"../P.Report")
    assert c.post("/api/upload/files/powerbi", content=bad, headers={**H, "Content-Type": "multipart/form-data; boundary=B"}).status_code == 400


def test_folder_upload_keeps_paths_and_skips_unneeded(home):
    c = _client()
    files = [("P/S.SemanticModel/definition/model.tmdl", b"model Model"), ("P/S.Report/definition.pbir", b"{}"),
             ("P/S.Report/StaticResources/logo.png", b"\x89PNG"), ("P/.pbi/cache.abf", b"x"), ("P/S.pbip", b"{}")]
    r = _up(c, "powerbi", files).json()
    res = r["results"][0]
    assert res["status"] == "ok" and res["models"] == ["S.SemanticModel"] and res["reports"] == ["S.Report"]
    assert r["skipped"] == 2
    base = home / "workspace" / ".staging" / "powerbi" / "P"
    assert (base / "S.SemanticModel/definition/model.tmdl").is_file() and not (base / ".pbi").exists()
    r = _up(c, "powerbi", [("x/readme.json", b"{}")]).json()["results"][0]
    assert r["status"] == "error"


def _zip(entries, compression=zipfile.ZIP_DEFLATED):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", compression) as z:
        for n, d in entries:
            if isinstance(n, zipfile.ZipInfo):
                z.writestr(n, d)
            else:
                z.writestr(n, d)
    return b.getvalue()


def test_zip_ok(home):
    c = _client()
    data = _zip([("Sales/Sales.SemanticModel/definition/model.tmdl", "model Model"), ("Sales/Sales.Report/definition.pbir", "{}"),
                 ("Sales/Sales.Report/img.png", "x")])
    res = _up(c, "powerbi", [("Sales.zip", data)]).json()["results"][0]
    assert res["status"] == "ok" and res["files"] == 2, res
    base = home / "workspace" / ".staging" / "powerbi"
    assert (base / "Sales" / "Sales" / "Sales.Report" / "definition.pbir").is_file()
    assert not (base / "Sales.zip").exists()


@pytest.mark.parametrize("member", ["../evil.json", "/etc/evil.json", "a/../../evil.json", "C:/evil.json"])
def test_zip_slip_rejected(home, member):
    c = _client()
    data = _zip([("P/P.Report/definition.pbir", "{}"), (member, "{}")])
    res = _up(c, "powerbi", [("p.zip", data)]).json()["results"][0]
    assert res["status"] == "error" and "Unsafe path" in res["message"]
    assert not list(home.parent.rglob("evil.json"))


def test_zip_symlink_rejected(home):
    c = _client()
    info = zipfile.ZipInfo("P/P.Report/link.json")
    info.external_attr = (0o120777 << 16)
    data = _zip([("P/P.Report/definition.pbir", "{}"), (info, "/etc/passwd")])
    res = _up(c, "powerbi", [("p.zip", data)]).json()["results"][0]
    assert res["status"] == "error" and "Symbolic links" in res["message"]


def test_zip_bomb_limits(home):
    c = _client(max_unzipped_mb=1)
    data = _zip([("P/P.Report/definition.pbir", "{}"), ("P/P.Report/big.json", "0" * (3 * 1024 * 1024))])
    assert len(data) < 100_000  # tiny on the wire, big when expanded
    res = _up(c, "powerbi", [("bomb.zip", data)]).json()["results"][0]
    assert res["status"] == "error" and "expands" in res["message"]
    assert not (home / "workspace" / ".staging" / "powerbi" / "bomb").exists()
    c = _client(max_zip_files=3)
    data = _zip([(f"P/P.Report/f{i}.json", "{}") for i in range(10)])
    res = _up(c, "powerbi", [("many.zip", data)]).json()["results"][0]
    assert res["status"] == "error" and "entries" in res["message"]


def test_oversize_upload_413(home):
    c = _client(max_upload_mb=1)
    r = _up(c, "sql", [("big.sql", b"-" * (2 * 1024 * 1024))])
    assert r.status_code == 413 and "LINEAGELENS_MAX_UPLOAD_MB" in r.json()["detail"]
    assert not list((home / "workspace" / ".staging").rglob("*.part"))
    # other JSON endpoints keep the small body limit
    c = _client(max_upload_mb=100, max_body_mb=1)
    assert c.post("/api/diff", content=b"x" * (2 * 1024 * 1024)).status_code == 413


def test_upload_needs_header_same_origin_and_toggle(home):
    c = _client()
    files = [("v.sql", b"create view a as select 1")]
    assert _up(c, "sql", files, headers={}).status_code == 403
    assert _up(c, "sql", files, headers={**H, "Origin": "http://evil.example"}).status_code == 403
    assert _up(c, "sql", files, headers={**H, "Origin": "null"}).status_code == 403
    assert _up(c, "sql", files, headers={**H, "Origin": "http://testserver"}).status_code == 200
    assert c.delete("/api/upload/workspace").status_code == 403
    assert _up(c, "nope", files).status_code == 404
    assert c.post("/api/upload/files/sql", content=b"{}", headers={**H, "Content-Type": "application/json"}).status_code == 400
    off = _client(allow_upload=False)
    assert _up(off, "sql", files).status_code == 403
    assert off.get("/api/upload").json()["allowed"] is False


def test_commit_validation(home):
    c = _client()
    assert c.post("/api/upload/scan", json={"project_name": "X"}, headers=H).status_code == 400  # nothing staged
    _up(c, "catalog", _sample_files()["catalog"])
    r = c.post("/api/upload/scan", json={"project_name": "X"}, headers=H)
    assert r.status_code == 400 and "manifest" in r.json()["detail"]
    r = c.post("/api/upload/scan", json={"project_name": "", "default_database": "A"}, headers=H)
    assert r.status_code == 400
    r = c.post("/api/upload/scan", json={"project_name": "X", "default_database": "A;\nDROP"}, headers=H)
    assert r.status_code == 400


def test_upload_scan_persist_and_remove(home):
    c = _client(scan=True)
    assert c.get("/api/summary").json()["is_sample"]
    for slot, files in _sample_files().items():
        r = _up(c, slot, files)
        assert r.status_code == 200 and all(x["status"] != "error" for x in r.json()["results"]), r.text
    r = c.post("/api/upload/scan", json={"project_name": "Northwind upload", "default_database": "ANALYTICS",
                                         "default_schema": "REPORTING"}, headers=H)
    assert r.status_code == 200, r.text
    s = _wait(c)
    assert s["error"] is None, s
    summ = c.get("/api/summary").json()
    assert summ["is_upload"] and not summ["is_sample"] and summ["project_name"] == "Northwind upload"
    assert len(c.get("/api/nodes").json()["nodes"]) == SAMPLE_NODES
    ws = home / "workspace" / "northwind-upload"
    assert (ws / "lineagelens.yml").is_file() and (ws / "lineage.db").is_file()
    assert (ws / "dbt/target/manifest.json").is_file() and len(list((ws / "snowflake").glob("*.sql"))) == 2
    assert not (home / "workspace" / ".staging").exists()
    info = c.get("/api/upload").json()["workspace"]
    assert info["active"] and info["project_name"] == "Northwind upload"
    assert uploads.active_config() == ws / "lineagelens.yml"

    # "restart": a new app picks the active upload (what `lineagelens serve` does)
    c2 = TestClient(create_app(uploads.active_config(), settings=Settings(allowed_hosts=["testserver"])))
    assert c2.get("/api/summary").json()["is_upload"]
    assert len(c2.get("/api/nodes").json()["nodes"]) == SAMPLE_NODES

    # switching to a sample deactivates the upload, activate brings it back
    assert c.post("/api/config/sample", json={"name": "standard"}).status_code == 200
    _wait(c)
    assert uploads.active_config() is None and uploads.workspace_config() is not None
    assert c.post("/api/upload/activate", headers=H).status_code == 200
    _wait(c)
    assert c.get("/api/summary").json()["is_upload"]

    # remove: files gone, back to the sample
    r = c.delete("/api/upload/workspace", headers=H)
    assert r.status_code == 200 and r.json()["rescanning"]
    _wait(c)
    assert not ws.exists() and uploads.workspace_config() is None
    summ = c.get("/api/summary").json()
    assert summ["is_sample"] and not summ["is_upload"]
    assert len(c.get("/api/nodes").json()["nodes"]) == SAMPLE_NODES


def test_cli_precedence(home, monkeypatch, tmp_path):
    """--config wins over an active upload; otherwise the upload wins over LINEAGELENS_CONFIG."""
    from lineagelens import cli

    captured = {}

    def fake_create_app(config, settings=None, default_config=None):
        captured.update(config=config, default=default_config)
        return object()

    import lineagelens.server as server
    monkeypatch.setattr(server, "create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: None)
    monkeypatch.delenv("LINEAGELENS_CONFIG", raising=False)
    ws = home / "workspace" / "proj"
    ws.mkdir(parents=True)
    (ws / "lineagelens.yml").write_text("project_name: P\n", encoding="utf-8")
    (home / "workspace" / "active.json").write_text(json.dumps({"project": "proj", "active": True}))
    from typer.testing import CliRunner
    CliRunner().invoke(cli.app, ["serve", "--no-browser"])
    assert captured["config"] == ws / "lineagelens.yml" and captured["default"] is None
    own = tmp_path / "own.yml"
    own.write_text("project_name: Own\n", encoding="utf-8")
    CliRunner().invoke(cli.app, ["serve", "--no-browser", "--config", str(own)])
    assert Path(captured["config"]) == own
