"""EXPERIMENTAL: pull semantic model (TMDL) and report (PBIR) definitions from a Power BI / Fabric workspace.

Off by default. Only runs when `powerbi.fabric.enabled: true` is set in the config. It makes read-only calls to
the Fabric REST API (api.fabric.microsoft.com) and nothing else. Item definitions are saved to a local cache folder.
After that the normal file-based parsers read them, so the lineage logic is the same as for PBIP files.

Auth (pick one):
  * FABRIC_TOKEN env var: a bearer token you get yourself (e.g. `az account get-access-token
    --resource https://api.fabric.microsoft.com`).
  * azure-identity installed (`pip install "lineagelens[fabric]"`): uses DefaultAzureCredential, then
    interactive browser sign-in.

Needs the Fabric "getDefinition" APIs, which need Contributor (or higher) on the workspace and the
"Users can access data stored in OneLake..." / item definition tenant settings. Not tested against a live tenant
in this release; treat it as a convenience and fall back to PBIP files when it fails.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://api.fabric.microsoft.com/v1"
SCOPE = "https://api.fabric.microsoft.com/.default"


@dataclass
class FabricPull:
    models: list[Path] = field(default_factory=list)
    reports: list[Path] = field(default_factory=list)
    report_model_map: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _token() -> str:
    tok = os.environ.get("FABRIC_TOKEN")
    if tok:
        return tok.strip()
    try:
        from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential, ChainedTokenCredential  # type: ignore
    except ImportError as ex:
        raise RuntimeError("set FABRIC_TOKEN or pip install 'lineagelens[fabric]' (azure-identity)") from ex
    cred = ChainedTokenCredential(DefaultAzureCredential(exclude_interactive_browser_credential=True),
                                  InteractiveBrowserCredential())
    return cred.get_token(SCOPE).token


class _Client:
    def __init__(self, token: str, timeout: int = 60):
        self.h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.timeout = timeout

    def _req(self, method: str, url: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=self.h)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https host
            raw = r.read()
            return r.status, dict(r.headers), (json.loads(raw) if raw else None)

    def get_all(self, url: str) -> list[dict]:
        out: list[dict] = []
        while url:
            _, _, js = self._req("GET", url)
            out += (js or {}).get("value", [])
            url = (js or {}).get("continuationUri") or ""
        return out

    def definition(self, ws: str, kind: str, item: str, fmt: str | None) -> list[dict]:
        url = f"{API}/workspaces/{ws}/{kind}/{item}/getDefinition" + (f"?format={fmt}" if fmt else "")
        status, headers, js = self._req("POST", url, {})
        if status == 202:  # long-running operation
            loc = headers.get("Location") or headers.get("location")
            wait = int(headers.get("Retry-After", "2") or 2)
            for _ in range(90):
                time.sleep(max(1, wait))
                _, h2, op = self._req("GET", loc)
                st = (op or {}).get("status", "")
                if st == "Succeeded":
                    _, _, js = self._req("GET", loc.rstrip("/") + "/result")
                    break
                if st in ("Failed", "Undefined"):
                    raise RuntimeError(f"getDefinition failed: {(op or {}).get('error')}")
            else:
                raise RuntimeError("getDefinition timed out")
        return ((js or {}).get("definition") or {}).get("parts", [])


_SAFE = re.compile(r"[^\w\-. ]+")


def _write_parts(root: Path, parts: list[dict]) -> None:
    for part in parts:
        rel = Path(part["path"])
        if rel.is_absolute() or ".." in rel.parts:
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = part.get("payload", "")
        dest.write_bytes(base64.b64decode(payload) if part.get("payloadType", "InlineBase64") == "InlineBase64" else payload.encode())


def pull(cfg: dict, cache_dir: Path) -> FabricPull:
    res = FabricPull()
    workspaces = cfg.get("workspaces") or []
    if not workspaces:
        res.warnings.append("fabric.enabled is true but no fabric.workspaces (workspace GUIDs) are configured")
        return res
    try:
        cli = _Client(_token(), int(cfg.get("timeout", 60)))
    except Exception as ex:
        res.warnings.append(f"Fabric auth failed: {ex}")
        return res
    for ws in workspaces:
        base = cache_dir / _SAFE.sub("_", ws)
        id_to_model: dict[str, str] = {}
        try:
            models = cli.get_all(f"{API}/workspaces/{ws}/semanticModels")
            reports = cli.get_all(f"{API}/workspaces/{ws}/reports")
        except urllib.error.HTTPError as ex:
            res.warnings.append(f"Fabric workspace {ws}: HTTP {ex.code} listing items")
            continue
        except Exception as ex:
            res.warnings.append(f"Fabric workspace {ws}: {ex}")
            continue
        for m in models:
            name = m.get("displayName") or m["id"]
            try:
                parts = cli.definition(ws, "semanticModels", m["id"], "TMDL")
                folder = base / f"{_SAFE.sub('_', name)}.SemanticModel"
                _write_parts(folder, parts)
                res.models.append(folder)
                id_to_model[m["id"].lower()] = name
            except Exception as ex:
                res.warnings.append(f"Fabric model '{name}': {ex}")
        for r in reports:
            name = r.get("displayName") or r["id"]
            try:
                parts = cli.definition(ws, "reports", r["id"], None)
                folder = base / f"{_SAFE.sub('_', name)}.Report"
                _write_parts(folder, parts)
                res.reports.append(folder)
                pbir = folder / "definition.pbir"
                if pbir.exists():
                    txt = pbir.read_text(encoding="utf-8", errors="ignore")
                    mm = re.search(r"semanticmodelid=([0-9a-fA-F-]{36})", txt)
                    if mm and mm.group(1).lower() in id_to_model:
                        res.report_model_map[name] = id_to_model[mm.group(1).lower()]
            except Exception as ex:
                res.warnings.append(f"Fabric report '{name}': {ex}")
    return res
