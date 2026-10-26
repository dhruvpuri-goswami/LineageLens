from fastapi.testclient import TestClient

from lineagelens import links


def test_links_defaults_and_env(monkeypatch):
    monkeypatch.delenv("BUYMEACOFFEE_URL", raising=False)
    monkeypatch.delenv("GITHUB_REPO_URL", raising=False)
    d = links.get_links()
    assert d["buymeacoffee_url"].startswith("https://www.buymeacoffee.com/")
    assert d["github_repo_url"].startswith("https://github.com/")
    monkeypatch.setenv("BUYMEACOFFEE_URL", "")
    monkeypatch.setenv("GITHUB_REPO_URL", "javascript:alert(1)")
    assert links.get_links() == {"buymeacoffee_url": "", "github_repo_url": ""}


def test_health_exposes_links(monkeypatch, tmp_path):
    monkeypatch.setenv("LINEAGELENS_HOME", str(tmp_path))
    monkeypatch.setenv("GITHUB_REPO_URL", "https://github.com/example/lineagelens")
    from lineagelens.server import create_app
    c = TestClient(create_app(scan_on_start=False))
    r = c.get("/api/health").json()
    assert r["links"]["github_repo_url"] == "https://github.com/example/lineagelens"
