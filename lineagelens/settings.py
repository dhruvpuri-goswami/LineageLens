"""Runtime settings from environment variables (12-factor style).

Every setting has a safe default for a desktop install. Docker and production
deployments override them via env (see ``.env.example``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, lo: int, hi: int) -> int:
    v = os.environ.get(name, "").strip()
    try:
        n = int(v) if v else default
    except ValueError:
        n = default
    return max(lo, min(hi, n))


def _list(name: str, default: list[str], sep: str = ",") -> list[str]:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return list(default)
    return [x.strip() for x in v.split(sep) if x.strip()]


def _paths(name: str) -> list[Path]:
    v = os.environ.get(name, "")
    parts = [x.strip() for x in v.replace(";", os.pathsep).split(os.pathsep) if x.strip()] if os.name != "nt" else \
        [x.strip() for x in v.split(";") if x.strip()]
    return [Path(p).expanduser().resolve() for p in parts]


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "info"
    log_format: str = "text"          # "text" or "json"
    config: str | None = None          # path to lineagelens.yml
    sample: str | None = None          # "standard" | "large"
    enable_docs: bool = False          # /api/docs pulls Swagger UI from a CDN, so it is off by default
    max_body_mb: int = 5               # largest accepted request body
    allow_config_write: bool = True    # allow "Save" of YAML from the UI
    allowed_roots: list[Path] = field(default_factory=list)  # empty = no restriction (desktop)
    allowed_hosts: list[str] = field(default_factory=lambda: ["127.0.0.1", "localhost", "[::1]"])

    @property
    def max_body_bytes(self) -> int:
        return self.max_body_mb * 1024 * 1024


def load_dotenv(path: str | Path = ".env") -> int:
    """Load KEY=VALUE lines from a .env file into os.environ (existing variables win).

    Minimal and dependency-free: ``#`` comments, blank lines and optional quotes are supported.
    Returns the number of variables set.
    """
    p = Path(path)
    if not p.is_file():
        return 0
    n = 0
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip().removeprefix("export ").strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


def load_settings() -> Settings:
    lvl = os.environ.get("LINEAGELENS_LOG_LEVEL", "info").strip().lower()
    fmt = os.environ.get("LINEAGELENS_LOG_FORMAT", "text").strip().lower()
    return Settings(
        host=os.environ.get("LINEAGELENS_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int("LINEAGELENS_PORT", 8765, 1, 65535),
        log_level=lvl if lvl in LOG_LEVELS else "info",
        log_format=fmt if fmt in {"text", "json"} else "text",
        config=os.environ.get("LINEAGELENS_CONFIG", "").strip() or None,
        sample=os.environ.get("LINEAGELENS_SAMPLE", "").strip() or None,
        enable_docs=_bool("LINEAGELENS_ENABLE_DOCS", False),
        max_body_mb=_int("LINEAGELENS_MAX_BODY_MB", 5, 1, 512),
        allow_config_write=_bool("LINEAGELENS_ALLOW_CONFIG_WRITE", True),
        allowed_roots=_paths("LINEAGELENS_ALLOWED_ROOTS"),
        allowed_hosts=_list("LINEAGELENS_ALLOWED_HOSTS", ["127.0.0.1", "localhost", "[::1]"]),
    )
