"""The experimental Fabric pull must never touch the network unless enabled, and must sanitise paths."""
import base64

from lineagelens.extractors import fabric


def test_disabled_without_workspaces(tmp_path):
    res = fabric.pull({"enabled": True}, tmp_path)
    assert res.models == [] and res.warnings


def test_write_parts_blocks_path_traversal(tmp_path):
    b = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731
    fabric._write_parts(tmp_path, [
        {"path": "definition/model.tmdl", "payload": b("model Model"), "payloadType": "InlineBase64"},
        {"path": "../escape.txt", "payload": b("x"), "payloadType": "InlineBase64"},
    ])
    assert (tmp_path / "definition" / "model.tmdl").read_text() == "model Model"
    assert not (tmp_path.parent / "escape.txt").exists()


def test_pull_with_fake_client(tmp_path, monkeypatch, samples):
    tmdl = (samples / "powerbi" / "RetailSales.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8")
    enc = lambda s: base64.b64encode(s.encode()).decode()  # noqa: E731
    mid = "11111111-2222-3333-4444-555555555555"

    class Fake:
        def __init__(self, *a, **k): ...
        def get_all(self, url):
            return [{"id": mid, "displayName": "Sales Model"}] if url.endswith("semanticModels") else [{"id": "r1", "displayName": "Exec"}]
        def definition(self, ws, kind, item, fmt):
            if kind == "semanticModels":
                return [{"path": "definition/model.tmdl", "payload": enc(tmdl)}]
            return [{"path": "definition.pbir", "payload": enc('{"datasetReference":{"byConnection":{"connectionString":"semanticmodelid=%s"}}}' % mid)}]

    monkeypatch.setattr(fabric, "_token", lambda: "t")
    monkeypatch.setattr(fabric, "_Client", Fake)
    res = fabric.pull({"enabled": True, "workspaces": ["ws1"]}, tmp_path)
    assert res.models[0].name == "Sales Model.SemanticModel"
    assert res.report_model_map == {"Exec": "Sales Model"}
