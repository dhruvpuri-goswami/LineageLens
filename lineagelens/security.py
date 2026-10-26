"""HTTP hardening: security headers, host/origin checks, body-size limit, request log, safe paths."""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

from .settings import Settings

log = logging.getLogger("lineagelens.http")

# Everything is bundled: no CDN, no web fonts, no third-party scripts.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'none'")
SECURITY_HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
]
UPLOAD_PREFIX = "/api/upload/"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _host_only(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


class HardeningMiddleware:
    """Pure ASGI middleware (works with streaming bodies)."""

    def __init__(self, app, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.hosts = {h.lower() for h in settings.allowed_hosts}
        self.any_host = "*" in self.hosts

    async def _reject(self, send, status: int, detail: str, extra_headers=()) -> None:
        body = ('{"error":"%s","detail":"%s"}' % ({400: "bad_request", 403: "forbidden", 413: "payload_too_large"}.get(status, "error"),
                                                  detail.replace('"', "'"))).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                *SECURITY_HEADERS, *extra_headers]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        rid = uuid.uuid4().hex[:12]
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        method, path = scope.get("method", "GET"), scope.get("path", "")
        status_holder = {"status": 500}

        def done(status: int) -> None:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            lvl = logging.WARNING if status >= 400 and status != 404 else logging.INFO
            if path.startswith("/assets/") and status < 400:
                lvl = logging.DEBUG
            log.log(lvl, "%s %s %s", method, path, status,
                    extra={"request_id": rid, "method": method, "path": path, "status": status, "duration_ms": ms})

        # DNS-rebinding protection: only answer for known host names.
        host = _host_only(headers.get("host", ""))
        if not self.any_host and host not in self.hosts:
            done(400)
            return await self._reject(send, 400, "Host not allowed. Add it to LINEAGELENS_ALLOWED_HOSTS.")
        # CSRF protection: browsers send Origin on cross-site writes.
        origin = headers.get("origin")
        if method in UNSAFE_METHODS and origin and origin != "null":
            o = urlsplit(origin)
            if _host_only(o.netloc) != host:
                done(403)
                return await self._reject(send, 403, "Cross-origin request blocked.")
        elif method in UNSAFE_METHODS and origin == "null":
            done(403)
            return await self._reject(send, 403, "Cross-origin request blocked.")
        # Uploads must carry a custom header: a plain cross-site <form> cannot add one, and fetch() needs a
        # CORS preflight that this server never approves.
        is_upload = path.startswith(UPLOAD_PREFIX)
        if is_upload and method in UNSAFE_METHODS and headers.get("x-requested-with", "").lower() != "lineagelens":
            done(403)
            return await self._reject(send, 403, "Upload requests need the X-Requested-With: LineageLens header.")
        # Body size limit: file uploads get their own (larger) limit, everything else stays small.
        upload_body = is_upload and method == "POST" and path.startswith(UPLOAD_PREFIX + "files/")
        limit = self.settings.max_upload_bytes if upload_body else self.settings.max_body_bytes
        limit_mb = self.settings.max_upload_mb if upload_body else self.settings.max_body_mb
        too_big = (f"Upload larger than {limit_mb} MB (LINEAGELENS_MAX_UPLOAD_MB)." if upload_body
                   else f"Request body larger than {limit_mb} MB.")
        cl = headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            done(413)
            return await self._reject(send, 413, too_big)
        received = 0

        async def limited_receive():
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > limit:
                    raise HTTPException(413, too_big)
            return msg

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                hdrs = [h for h in message.get("headers", []) if h[0].lower() not in {k for k, _ in SECURITY_HEADERS}]
                hdrs += SECURITY_HEADERS + [(b"x-request-id", rid.encode())]
                if path.startswith("/api/"):
                    hdrs.append((b"cache-control", b"no-store"))
                message = {**message, "headers": hdrs}
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        finally:
            done(status_holder["status"])


def safe_path(raw: str | None, settings: Settings, *, extra_roots: list[Path] = (), suffixes: tuple[str, ...] = (),
              must_exist: bool = False, what: str = "path") -> Path:
    """Validate a user-supplied filesystem path.

    Rejects NUL bytes, non-allowed suffixes and (when ``LINEAGELENS_ALLOWED_ROOTS`` is set) anything that
    resolves outside the allowed roots, including ``..`` and symlink escapes.
    """
    if not raw or not isinstance(raw, str):
        raise HTTPException(400, f"{what} required")
    if "\x00" in raw or len(raw) > 4096:
        raise HTTPException(400, f"Invalid {what}")
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except (OSError, RuntimeError):
        raise HTTPException(400, f"Invalid {what}")
    if suffixes and p.suffix.lower() not in suffixes and not (p.is_dir() and "" in suffixes):
        raise HTTPException(400, f"{what} must end with {' or '.join(s for s in suffixes if s)}")
    roots = list(settings.allowed_roots)
    if roots:
        roots += [r.resolve() for r in extra_roots]
        if not any(p == r or r in p.parents for r in roots):
            raise HTTPException(403, f"{what} is outside the allowed folders (LINEAGELENS_ALLOWED_ROOTS)")
    if must_exist and not p.exists():
        raise HTTPException(404, f"Not found: {raw}")
    return p
