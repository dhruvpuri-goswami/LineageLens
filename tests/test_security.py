"""Production hardening: headers, host / origin checks, body limits, path safety, settings."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lineagelens.server import create_app
from lineagelens.settings import Settings, load_dotenv, load_settings

HOSTS = ["127.0.0.1", "localhost", "testserver"]


def _client(tmp_path=None, **kw):
    roots = kw.pop("allowed_roots", [])
    st = Settings(allowed_hosts=kw.pop("allowed_hosts", HOSTS), allowed_roots=roots, **kw)
    return TestClient(create_app(None, scan_on_start=True, settings=st), raise_server_exceptions=False)


def test_security_headers_and_health():
    c = _client()
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    h = r.headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "script-src 'self'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"
    assert h["cache-control"] == "no-store"
    assert h["x-request-id"]
    # the UI shell gets the same headers
    ui = c.get("/")
    assert ui.status_code == 200 and "x-frame-options" in ui.headers


def test_ui_has_no_inline_scripts_or_external_assets():
    html = (Path(__file__).parents[1] / "lineagelens" / "static" / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html  # CSP forbids inline scripts
    for bad in ("http://", "https://", "//fonts.", "cdn"):
        assert bad not in html


def test_unknown_host_rejected():
    c = _client()
    r = c.get("/api/health", headers={"host": "evil.example.com"})
    assert r.status_code == 400
    assert _client(allowed_hosts=["*"]).get("/api/health", headers={"host": "evil.example.com"}).status_code == 200


def test_cross_origin_write_blocked():
    c = _client()
    r = c.post("/api/impact", json={"ids": [], "change": "logic"}, headers={"origin": "https://evil.example.com"})
    assert r.status_code == 403
    r = c.post("/api/impact", json={"ids": [], "change": "logic"}, headers={"origin": "null"})
    assert r.status_code == 403
    r = c.post("/api/impact", json={"ids": [], "change": "logic"}, headers={"origin": "http://testserver"})
    assert r.status_code != 403


def test_body_too_large():
    c = _client(max_body_mb=1)
    r = c.post("/api/impact", content=b"x" * (1024 * 1024 + 10), headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert "detail" in r.json()


def test_docs_disabled_by_default_and_optional():
    c = _client()
    assert c.get("/api/openapi.json").status_code == 404
    assert c.get("/api/docs").status_code == 404
    c2 = _client(enable_docs=True)
    assert c2.get("/api/openapi.json").json()["info"]["title"] == "LineageLens"


def test_config_path_rules(tmp_path):
    allowed = tmp_path / "inputs"
    allowed.mkdir()
    c = _client(allowed_roots=[allowed])
    # outside the allowed roots
    r = c.put("/api/config", json={"path": str(tmp_path / "elsewhere.yml"), "yaml": "project_name: x\n"})
    assert r.status_code == 403
    # traversal out of the root
    r = c.put("/api/config", json={"path": str(allowed / ".." / "escape.yml"), "yaml": "project_name: x\n"})
    assert r.status_code == 403
    # wrong file type
    r = c.put("/api/config", json={"path": str(allowed / "evil.py"), "yaml": "x"})
    assert r.status_code == 400
    # NUL byte
    r = c.put("/api/config", json={"path": str(allowed) + "/a\x00.yml", "yaml": "x"})
    assert r.status_code == 400
    assert not (tmp_path / "elsewhere.yml").exists() and not (tmp_path / "escape.yml").exists()


def test_config_write_can_be_disabled(tmp_path):
    c = _client(allow_config_write=False)
    r = c.put("/api/config", json={"path": str(tmp_path / "x.yml"), "yaml": "project_name: x\n"})
    assert r.status_code == 403 and not (tmp_path / "x.yml").exists()


def test_diff_paths_checked(tmp_path):
    allowed = tmp_path / "inputs"
    allowed.mkdir()
    c = _client(allowed_roots=[allowed])
    r = c.post("/api/diff", json={"old": "/etc/passwd", "new": "/etc/hostname"})
    assert r.status_code in (400, 403)
    r = c.post("/api/diff", json={"old": str(allowed / "missing.json"), "new": str(allowed / "missing2.json")})
    assert r.status_code == 404


def test_errors_are_json_without_traceback():
    c = _client()
    r = c.get("/api/impact", params={"id": "does_not_exist_xyz_123"})
    assert r.status_code == 404
    body = r.json()
    assert body["detail"] and "Traceback" not in r.text


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("LINEAGELENS_PORT", "9999")
    monkeypatch.setenv("LINEAGELENS_LOG_FORMAT", "json")
    monkeypatch.setenv("LINEAGELENS_MAX_BODY_MB", "100000")
    monkeypatch.setenv("LINEAGELENS_ALLOWED_HOSTS", "a.local, b.local")
    s = load_settings()
    assert s.port == 9999 and s.log_format == "json" and s.max_body_mb == 512
    assert s.allowed_hosts == ["a.local", "b.local"]
    assert s.host == "127.0.0.1" and s.enable_docs is False


def test_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text('# c\nLL_TEST_A="quoted"\nLL_TEST_B=plain\nLL_TEST_C=keep\n', encoding="utf-8")
    monkeypatch.delenv("LL_TEST_A", raising=False)
    monkeypatch.delenv("LL_TEST_B", raising=False)
    monkeypatch.setenv("LL_TEST_C", "real")
    assert load_dotenv(env) == 2
    import os
    assert os.environ["LL_TEST_A"] == "quoted" and os.environ["LL_TEST_B"] == "plain" and os.environ["LL_TEST_C"] == "real"
    monkeypatch.delenv("LL_TEST_A")
    monkeypatch.delenv("LL_TEST_B")


def test_json_logging(capsys):
    import json
    import logging

    from lineagelens.logging_setup import setup_logging
    setup_logging("info", "json")
    logging.getLogger("lineagelens").info("hello", extra={"k": 1})
    line = capsys.readouterr().out.strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["msg"] == "hello" and rec["level"] == "info" and rec["k"] == 1
    setup_logging("warning", "text")
