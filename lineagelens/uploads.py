"""In-app uploads: store the user's own exports under ``LINEAGELENS_HOME/workspace/<project>/``.

Flow
----
1. The browser uploads files per *slot* (``manifest``, ``catalog``, ``sql``, ``powerbi``, ``pbix``) with
   ``POST /api/upload/files/<slot>``. Bodies are parsed with a streaming multipart parser and written straight
   to ``workspace/.staging/<slot>/``; nothing is held in memory or in ``/tmp``.
2. Every file is checked on arrival: extension allow-list, safe relative path, JSON sanity for dbt files,
   ``CREATE VIEW`` for SQL, ``Report/Layout`` for .pbix, and zip-slip / zip-bomb limits for zipped PBIP projects.
3. ``POST /api/upload/scan`` moves the staged files into ``workspace/<project>/``, writes a ``lineagelens.yml``
   next to them, marks it active (``workspace/active.json``) and starts a scan. The active upload is used again
   after a restart.

Everything stays on this machine. The only writes are below the workspace folder.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, Request
from python_multipart.multipart import MultipartParser, parse_options_header

from .config import user_data_dir
from .settings import Settings

log = logging.getLogger("lineagelens.upload")

WORKSPACE_DIR = "workspace"
STAGING_DIR = ".staging"
ACTIVE_FILE = "active.json"
INFO_FILE = "upload.json"
CONFIG_NAME = "lineagelens.yml"

#: Files LineageLens reads from a PBIP project. Everything else (images, .pbi cache, .abf) is skipped.
PBIP_EXTS = {".pbip", ".pbir", ".pbism", ".tmdl", ".json", ".bim", ".dax", ".m", ".pq"}
PBIP_NAMES = {".platform"}
JSON_FULL_PARSE_BYTES = 64 * 1024 * 1024     # larger dbt files get a header + structure check instead
MAX_FILES_PER_REQUEST = 20000
MAX_REL_PATH = 1024
_BAD_CHARS = re.compile(r'[\x00-\x1f<>:"|?*]')
_IDENT = re.compile(r"^[A-Za-z0-9_$.\- \"]{0,255}$")


@dataclass(frozen=True)
class Slot:
    key: str
    label: str
    exts: frozenset[str]
    multi: bool
    folder: bool = False   # keeps relative paths (folder / zip uploads)


SLOTS: dict[str, Slot] = {
    "manifest": Slot("manifest", "dbt manifest.json", frozenset({".json"}), multi=False),
    "catalog": Slot("catalog", "dbt catalog.json", frozenset({".json"}), multi=False),
    "sql": Slot("sql", "Snowflake view SQL", frozenset({".sql"}), multi=True),
    "powerbi": Slot("powerbi", "Power BI project (PBIP)", frozenset(PBIP_EXTS | {".zip"}), multi=True, folder=True),
    "pbix": Slot("pbix", "Power BI .pbix", frozenset({".pbix"}), multi=True),
}


# ---------------------------------------------------------------- paths
def root() -> Path:
    p = user_data_dir() / WORKSPACE_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def staging() -> Path:
    p = root() / STAGING_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def slot_dir(slot: str) -> Path:
    return staging() / slot


def _inside(base: Path, p: Path) -> bool:
    base = base.resolve()
    p = p.resolve()
    return p == base or base in p.parents


def safe_relpath(raw: str, *, keep_dirs: bool) -> str:
    """Normalise a browser-supplied file name / relative path, rejecting traversal and odd characters."""
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(400, "File name missing.")
    s = raw.replace("\\", "/").strip()
    if len(s) > MAX_REL_PATH or _BAD_CHARS.search(s):
        raise HTTPException(400, f"Unsafe file name: {raw[:120]!r}")
    if s.startswith("/") or re.match(r"^[A-Za-z]:", s):
        raise HTTPException(400, f"Absolute paths are not allowed: {raw[:120]!r}")
    parts = [x for x in s.split("/") if x not in ("", ".")]
    if not parts or any(x == ".." for x in parts):
        raise HTTPException(400, f"Path traversal is not allowed: {raw[:120]!r}")
    if any(len(x) > 255 or x.endswith(" ") for x in parts):
        raise HTTPException(400, f"Unsafe file name: {raw[:120]!r}")
    return "/".join(parts) if keep_dirs else parts[-1]


def _ext_ok(slot: Slot, name: str) -> bool:
    n = name.rsplit("/", 1)[-1]
    if slot.folder and n in PBIP_NAMES:
        return True
    return Path(n).suffix.lower() in slot.exts


def _skip_pbip(rel: str) -> bool:
    """Power BI desktop cache folders (``.pbi``) and unknown file types are not needed."""
    parts = rel.split("/")
    return any(p == ".pbi" for p in parts) or not (parts[-1] in PBIP_NAMES or Path(parts[-1]).suffix.lower() in PBIP_EXTS)


# ---------------------------------------------------------------- status (persisted per slot)
def _status_path() -> Path:
    return user_data_dir() / WORKSPACE_DIR / STAGING_DIR / "status.json"  # reading must not create folders


def _read_status() -> dict[str, list[dict]]:
    try:
        d = json.loads(_status_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_status(d: dict) -> None:
    staging()
    tmp = _status_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    os.replace(tmp, _status_path())


def clear_slot(slot: str) -> None:
    if slot not in SLOTS:
        raise HTTPException(404, f"Unknown upload slot '{slot}'.")
    shutil.rmtree(slot_dir(slot), ignore_errors=True)
    st = _read_status()
    st.pop(slot, None)
    _write_status(st)


def clear_staging() -> None:
    shutil.rmtree(root() / STAGING_DIR, ignore_errors=True)


# ---------------------------------------------------------------- validation
def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"


def check_dbt_json(path: Path, kind: str) -> dict:
    """Sanity-check a dbt artifact: JSON object with ``metadata.dbt_schema_version`` for *kind*."""
    other = "catalog" if kind == "manifest" else "manifest"
    size = path.stat().st_size
    if size == 0:
        return {"status": "error", "message": "The file is empty."}
    if size <= JSON_FULL_PARSE_BYTES:
        try:
            with path.open("rb") as f:
                data = json.load(f)
        except (ValueError, UnicodeDecodeError) as e:
            return {"status": "error", "message": f"Not valid JSON ({str(e)[:120]})."}
        if not isinstance(data, dict):
            return {"status": "error", "message": "Expected a JSON object."}
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        ver = str(meta.get("dbt_schema_version") or "")
        nodes = data.get("nodes") if isinstance(data.get("nodes"), dict) else None
        dbt_version = str(meta.get("dbt_version") or "")
    else:  # very large manifest: check the header and that the document is closed
        with path.open("rb") as f:
            head = f.read(1024 * 1024).decode("utf-8", "replace")
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", "replace").rstrip()
        if not head.lstrip().startswith("{") or not tail.endswith("}"):
            return {"status": "error", "message": "Not a JSON object (file looks truncated)."}
        m = re.search(r'"dbt_schema_version"\s*:\s*"([^"]+)"', head)
        ver = m.group(1) if m else ""
        mv = re.search(r'"dbt_version"\s*:\s*"([^"]+)"', head)
        dbt_version = mv.group(1) if mv else ""
        nodes = None
    if not ver:
        return {"status": "error", "message": f"metadata.dbt_schema_version is missing: this is not a dbt {kind}.json."}
    if f"/{other}/" in ver:
        return {"status": "error", "message": f"This is a dbt {other}.json. Drop it in the {other} box."}
    if f"/{kind}/" not in ver:
        return {"status": "error", "message": f"Unexpected schema {ver!r}; expected a dbt {kind}.json."}
    if nodes is not None and kind == "manifest" and not nodes:
        return {"status": "warning", "message": "The manifest has no nodes.", "detected": f"dbt {kind}"}
    v = ver.rsplit("/", 1)[-1].removesuffix(".json")
    bits = [f"dbt {kind} {v}"]
    if dbt_version:
        bits.append(f"dbt {dbt_version}")
    if nodes is not None:
        bits.append(f"{len(nodes)} nodes")
    return {"status": "ok", "detected": " · ".join(bits), "message": ""}


def check_sql(path: Path) -> dict:
    raw = path.read_bytes()[: 4 * 1024 * 1024]
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("cp1252")
        except UnicodeDecodeError:
            return {"status": "error", "message": "Not a text file."}
    n = len(re.findall(r"\bcreate\s+(?:or\s+replace\s+)?(?:secure\s+)?(?:materialized\s+)?view\b", text, re.I))
    if not n:
        return {"status": "warning", "detected": "SQL", "message": "No CREATE VIEW statement found; the file will be skipped."}
    return {"status": "ok", "detected": f"{n} view{'s' if n > 1 else ''}", "message": ""}


def check_pbix(path: Path) -> dict:
    if not zipfile.is_zipfile(path):
        return {"status": "error", "message": "Not a .pbix file (expected a zip package)."}
    try:
        with zipfile.ZipFile(path) as z:
            names = {n.replace("\\", "/") for n in z.namelist()}
    except zipfile.BadZipFile:
        return {"status": "error", "message": "The .pbix package is damaged."}
    if "Report/Layout" not in names:
        return {"status": "error", "message": "Report/Layout not found. Newer .pbix files store the report as PBIR: save as PBIP instead."}
    return {"status": "ok", "detected": "PBIX report layout",
            "message": "Report pages and visuals only. Measures and model columns need the PBIP project."}


def detect_pbip(base: Path) -> dict:
    models = sorted({p.name for p in base.rglob("*.SemanticModel") if p.is_dir()})
    reports = sorted({p.name for p in base.rglob("*.Report") if p.is_dir()})
    bims = [p for p in base.rglob("model.bim") if not any(x.endswith(".SemanticModel") for x in p.parts)]
    return {"models": models, "reports": reports, "bim": len(bims)}


def _pbip_summary(d: dict) -> str:
    parts = []
    if d["models"]:
        parts.append(f"{len(d['models'])} semantic model{'s' if len(d['models']) > 1 else ''}")
    if d["reports"]:
        parts.append(f"{len(d['reports'])} report{'s' if len(d['reports']) > 1 else ''}")
    return ", ".join(parts)


def safe_extract_zip(zpath: Path, dest: Path, settings: Settings) -> dict:
    """Extract only PBIP files from *zpath* into *dest* with zip-slip, symlink and zip-bomb protection."""
    max_total = settings.max_unzipped_bytes
    try:
        z = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        raise ValueError("Not a valid .zip file.")
    with z:
        infos = z.infolist()
        if len(infos) > settings.max_zip_files:
            raise ValueError(f"The zip has {len(infos)} entries; the limit is {settings.max_zip_files} (LINEAGELENS_MAX_ZIP_FILES).")
        declared = sum(i.file_size for i in infos)
        if declared > max_total:
            raise ValueError(f"The zip expands to {_fmt_size(declared)}; the limit is {settings.max_unzipped_mb} MB (LINEAGELENS_MAX_UNZIPPED_MB).")
        plan: list[tuple[zipfile.ZipInfo, Path]] = []
        skipped = 0
        for i in infos:
            name = i.filename
            if i.is_dir():
                continue
            try:
                rel = safe_relpath(name, keep_dirs=True)
            except HTTPException:
                raise ValueError(f"Unsafe path inside the zip: {name[:120]!r}")
            if stat.S_ISLNK(i.external_attr >> 16):
                raise ValueError(f"Symbolic links are not allowed inside the zip: {name[:120]!r}")
            if i.flag_bits & 0x1:
                raise ValueError("Encrypted zip files are not supported.")
            target = dest / rel
            if not _inside(dest, target):
                raise ValueError(f"Unsafe path inside the zip: {name[:120]!r}")
            if _skip_pbip(rel):
                skipped += 1
                continue
            plan.append((i, target))
        written = 0
        for i, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, target.open("wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_total:  # do not trust the declared sizes
                        raise ValueError(f"The zip expands beyond {settings.max_unzipped_mb} MB (LINEAGELENS_MAX_UNZIPPED_MB).")
                    out.write(chunk)
    return {"files": len(plan), "skipped": skipped, "bytes": written}


# ---------------------------------------------------------------- streaming multipart receiver
@dataclass
class _Part:
    headers: dict[str, bytes] = field(default_factory=dict)
    name: str = ""
    filename: str | None = None
    value: bytearray = field(default_factory=bytearray)
    fh: Any = None
    tmp: Path | None = None
    dest: Path | None = None
    rel: str = ""
    size: int = 0
    skip: str | None = None     # reason the data is discarded


class _Receiver:
    def __init__(self, slot: Slot, base: Path, max_file_bytes: int) -> None:
        self.slot, self.base, self.max_file_bytes = slot, base, max_file_bytes
        self.part: _Part | None = None
        self.hfield = bytearray()
        self.hvalue = bytearray()
        self.next_path: str | None = None
        self.files: list[dict] = []        # written files: {rel, path, size}
        self.rejected: list[dict] = []     # per-file errors
        self.skipped = 0
        self.count = 0
        self.temps: list[Path] = []

    # callbacks -----------------------------------------------------
    def on_part_begin(self) -> None:
        self.part = _Part()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self.hfield += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self.hvalue += data[start:end]

    def on_header_end(self) -> None:
        assert self.part is not None
        self.part.headers[self.hfield.decode("latin-1").lower()] = bytes(self.hvalue)
        self.hfield.clear()
        self.hvalue.clear()

    def on_headers_finished(self) -> None:
        p = self.part
        assert p is not None
        _, opts = parse_options_header(p.headers.get("content-disposition", b""))
        p.name = opts.get(b"name", b"").decode("utf-8", "replace")
        fn = opts.get(b"filename")
        p.filename = fn.decode("utf-8", "replace") if fn is not None else None
        if p.filename is None:
            return  # a plain form field (e.g. "path")
        self.count += 1
        if self.count > MAX_FILES_PER_REQUEST:
            raise HTTPException(413, f"Too many files in one upload (limit {MAX_FILES_PER_REQUEST}).")
        raw = self.next_path or p.filename
        self.next_path = None
        p.rel = safe_relpath(raw, keep_dirs=self.slot.folder)
        if self.slot.folder and not p.rel.lower().endswith(".zip") and _skip_pbip(p.rel):
            p.skip = "not needed"
            self.skipped += 1
            return
        if not _ext_ok(self.slot, p.rel):
            want = ", ".join(sorted(self.slot.exts))
            p.skip = f"Not accepted here: expected {want}."
            return
        if not self.slot.multi:
            p.rel = {"manifest": "manifest.json", "catalog": "catalog.json"}.get(self.slot.key, p.rel)
        p.dest = self.base / p.rel
        if not _inside(self.base, p.dest):
            raise HTTPException(400, f"Path traversal is not allowed: {raw[:120]!r}")
        p.dest.parent.mkdir(parents=True, exist_ok=True)
        p.tmp = p.dest.with_name(p.dest.name + f".{os.getpid()}.part")
        self.temps.append(p.tmp)
        p.fh = p.tmp.open("wb")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        p = self.part
        assert p is not None
        n = end - start
        if p.filename is None:
            if len(p.value) + n > 4096:
                raise HTTPException(400, "Form field too long.")
            p.value += data[start:end]
            return
        p.size += n
        if p.fh is not None:
            if p.size > self.max_file_bytes:
                raise HTTPException(413, f"{p.rel} is larger than the upload limit.")
            p.fh.write(data[start:end])

    def on_part_end(self) -> None:
        p = self.part
        assert p is not None
        self.part = None
        if p.filename is None:
            if p.name == "path":
                self.next_path = p.value.decode("utf-8", "replace")
            return
        if p.fh is not None:
            p.fh.close()
            os.replace(p.tmp, p.dest)
            self.temps.remove(p.tmp)
            self.files.append({"rel": p.rel, "path": p.dest, "size": p.size})
        elif p.skip and p.skip != "not needed":
            self.rejected.append({"name": p.rel, "size": p.size, "status": "error", "detected": "", "message": p.skip})

    def cleanup(self, discard: bool = False) -> None:
        """Remove partial files; with *discard* also the files this request already completed."""
        if self.part and self.part.fh:
            try:
                self.part.fh.close()
            except OSError:
                pass
        if discard:
            self.temps += [f["path"] for f in self.files]
            self.files = []
        for t in self.temps:
            try:
                t.unlink()
            except OSError:
                pass


async def receive(request: Request, slot_key: str, settings: Settings) -> dict:
    """Stream a multipart upload for *slot_key* into the staging folder and validate each file."""
    from starlette.concurrency import run_in_threadpool

    slot = SLOTS.get(slot_key)
    if slot is None:
        raise HTTPException(404, f"Unknown upload slot '{slot_key}'. Use one of: {', '.join(SLOTS)}.")
    ctype, opts = parse_options_header(request.headers.get("content-type", ""))
    if ctype != b"multipart/form-data" or not opts.get(b"boundary"):
        raise HTTPException(400, "Expected multipart/form-data.")
    base = slot_dir(slot_key)
    if not slot.multi:
        shutil.rmtree(base, ignore_errors=True)  # single-file slots are replaced
    base.mkdir(parents=True, exist_ok=True)
    rec = _Receiver(slot, base, settings.max_upload_bytes)
    parser = MultipartParser(opts[b"boundary"], callbacks={
        "on_part_begin": rec.on_part_begin, "on_part_data": rec.on_part_data, "on_part_end": rec.on_part_end,
        "on_header_field": rec.on_header_field, "on_header_value": rec.on_header_value,
        "on_header_end": rec.on_header_end, "on_headers_finished": rec.on_headers_finished,
    })
    try:
        async for chunk in request.stream():
            if chunk:
                parser.write(chunk)
        parser.finalize()
    except HTTPException:
        rec.cleanup(discard=True)
        raise
    except Exception as e:  # malformed multipart
        rec.cleanup(discard=True)
        raise HTTPException(400, f"Malformed upload: {type(e).__name__}")
    if rec.part is not None:
        rec.cleanup(discard=True)
        raise HTTPException(400, "Upload ended early.")
    results = await run_in_threadpool(_validate, slot, base, rec, settings)
    return {"slot": slot_key, "results": results, "skipped": rec.skipped}


def _validate(slot: Slot, base: Path, rec: _Receiver, settings: Settings) -> list[dict]:
    results: list[dict] = list(rec.rejected)
    status = _read_status()
    kept: list[dict] = [] if not slot.multi else list(status.get(slot.key, []))

    def keep(r: dict) -> None:
        nonlocal kept
        kept = [k for k in kept if k["name"] != r["name"]] + [r]

    if slot.key in ("manifest", "catalog"):
        for f in rec.files:
            r = {"name": f["rel"], "size": f["size"], **check_dbt_json(f["path"], slot.key)}
            r.setdefault("detected", "")
            results.append(r)
            if r["status"] == "error":
                f["path"].unlink(missing_ok=True)
            else:
                keep(r)
    elif slot.key == "sql":
        for f in rec.files:
            r = {"name": f["rel"], "size": f["size"], **check_sql(f["path"])}
            r.setdefault("detected", "")
            results.append(r)
            if r["status"] == "error":
                f["path"].unlink(missing_ok=True)
            else:
                keep(r)
    elif slot.key == "pbix":
        for f in rec.files:
            r = {"name": f["rel"], "size": f["size"], **check_pbix(f["path"])}
            results.append(r)
            if r["status"] == "error":
                f["path"].unlink(missing_ok=True)
            else:
                keep(r)
    else:  # powerbi: folder files and/or zips
        zips = [f for f in rec.files if f["rel"].lower().endswith(".zip")]
        loose = [f for f in rec.files if f not in zips]
        for f in zips:
            stem = Path(f["rel"]).stem
            dest = base / safe_relpath(stem, keep_dirs=False)
            r: dict = {"name": f["rel"], "size": f["size"], "detected": "", "message": ""}
            try:
                shutil.rmtree(dest, ignore_errors=True)
                info = safe_extract_zip(f["path"], dest, settings)
                d = detect_pbip(dest)
                if not d["models"] and not d["reports"] and not d["bim"]:
                    raise ValueError("No .SemanticModel or .Report folder inside the zip. Zip the folder that contains the .pbip file.")
                r.update(status="ok", detected=f"PBIP zip: {_pbip_summary(d) or 'model.bim'}",
                         message=f"{info['files']} files extracted" + (f", {info['skipped']} not needed (images, cache)" if info["skipped"] else ""),
                         files=info["files"], models=d["models"], reports=d["reports"])
                keep(r)
            except ValueError as e:
                shutil.rmtree(dest, ignore_errors=True)
                r.update(status="error", message=str(e))
            finally:
                f["path"].unlink(missing_ok=True)
            results.append(r)
        if loose:
            tops = sorted({f["rel"].split("/")[0] for f in loose})
            total = sum(f["size"] for f in loose)
            name = tops[0] + "/" if len(tops) == 1 else f"{len(tops)} folders"
            d = detect_pbip(base)
            r = {"name": name, "size": total, "detected": "", "message": ""}
            found = [f for f in loose if any(seg.endswith((".SemanticModel", ".Report")) for seg in f["rel"].split("/")[:-1])
                     or f["rel"].rsplit("/", 1)[-1] == "model.bim"]
            if not found:
                for f in loose:
                    f["path"].unlink(missing_ok=True)
                r.update(status="error", message="No .SemanticModel or .Report folder found. Choose the folder that contains the .pbip file.")
            else:
                r.update(status="ok", detected=f"PBIP folder: {_pbip_summary(d) or 'model.bim'}",
                         message=f"{len(loose)} files" + (f", {rec.skipped} not needed (images, cache)" if rec.skipped else ""),
                         files=len(loose), models=d["models"], reports=d["reports"])
                keep(r)
            results.append(r)
        elif rec.skipped and not zips:
            results.append({"name": "folder", "size": 0, "status": "error", "detected": "",
                            "message": "None of the files are part of a PBIP project (.tmdl, .pbir, .json, .pbism)."})
    if kept:
        status[slot.key] = kept
    else:
        status.pop(slot.key, None)
    _write_status(status)
    for r in results:
        log.info("upload %s", r["status"], extra={"slot": slot.key, "file": r["name"], "bytes": r.get("size", 0), "detail": r.get("message", "")})
    return results


# ---------------------------------------------------------------- workspace
def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "my-project"


def read_active() -> dict:
    try:
        d = json.loads((user_data_dir() / WORKSPACE_DIR / ACTIVE_FILE).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_active(d: dict) -> None:
    p = root() / ACTIVE_FILE
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.replace(tmp, p)


def workspace_config() -> Path | None:
    """The uploaded workspace config, if one exists (active or not)."""
    a = read_active()
    proj = a.get("project")
    if not isinstance(proj, str) or _slug(proj) != proj:
        return None
    p = user_data_dir() / WORKSPACE_DIR / proj / CONFIG_NAME
    return p if p.is_file() else None


def active_config() -> Path | None:
    """Config of the uploaded workspace if it is the active one (used at start-up)."""
    return workspace_config() if read_active().get("active") else None


def set_active(flag: bool) -> None:
    a = read_active()
    if a.get("project"):
        a["active"] = bool(flag)
        _write_active(a)


def is_workspace_config(path: Path | None) -> bool:
    if not path:
        return False
    try:
        return _inside(user_data_dir() / WORKSPACE_DIR, Path(path)) and Path(path).name == CONFIG_NAME
    except OSError:
        return False


def staging_state() -> dict:
    st = _read_status()
    return {k: st.get(k, []) for k in SLOTS}


def workspace_info() -> dict | None:
    cfg = workspace_config()
    if not cfg:
        return None
    try:
        info = json.loads((cfg.parent / INFO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    size = sum(p.stat().st_size for p in cfg.parent.rglob("*") if p.is_file())
    return {**info, "project": cfg.parent.name, "config_path": str(cfg), "path": str(cfg.parent),
            "active": bool(read_active().get("active")), "bytes": size}


def _clean_ident(v: Any, what: str) -> str:
    s = str(v or "").strip()
    if not _IDENT.match(s):
        raise HTTPException(400, f"{what} may contain letters, digits, _ $ . - and quotes only (max 255).")
    return s


def commit(body: dict) -> Path:
    """Move staged files into ``workspace/<project>/``, write its config and make it active."""
    name = str(body.get("project_name") or "").strip()
    if not name or len(name) > 80 or _BAD_CHARS.search(name.replace(":", "-")):
        raise HTTPException(400, "Enter a project name (up to 80 characters).")
    db = _clean_ident(body.get("default_database"), "Default database")
    schema = _clean_ident(body.get("default_schema"), "Default schema")
    st = staging_state()
    if st["catalog"] and not st["manifest"]:
        raise HTTPException(400, "catalog.json needs a manifest.json: add the manifest too.")
    if not any(st[k] for k in SLOTS):
        raise HTTPException(400, "Add at least one file before scanning.")
    slug = _slug(name)
    base = root()
    new = base / f".{slug}.new"
    shutil.rmtree(new, ignore_errors=True)
    new.mkdir(parents=True)
    sd = staging()
    moves = {"manifest": new / "dbt" / "target", "catalog": new / "dbt" / "target", "sql": new / "snowflake",
             "powerbi": new / "powerbi", "pbix": new / "powerbi" / "_pbix"}
    for key, dest in moves.items():
        src = sd / key
        if not st[key] or not src.is_dir():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            if item.name.endswith(".part"):
                continue
            target = dest / item.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(item), str(target))
    cfg: dict[str, Any] = {"project_name": name, "database": "lineage.db"}
    if st["manifest"]:
        d = {"manifest": "dbt/target/manifest.json"}
        if st["catalog"]:
            d["catalog"] = "dbt/target/catalog.json"
        cfg["dbt"] = [d]
    cfg["snowflake"] = {"view_dirs": ["snowflake"] if st["sql"] else [], "default_database": db, "default_schema": schema}
    cfg["powerbi"] = {"search_dirs": ["powerbi"] if (st["powerbi"] or st["pbix"]) else [], "report_model_map": {}}
    cfg["naming"] = {"case_insensitive": True, "strip_prefixes": [], "strip_suffixes": [], "enable_fuzzy": True, "fuzzy_threshold": 90}
    header = ("# Generated by LineageLens from files uploaded in the app. Paths are relative to this file.\n"
              "# Remove it from Settings > Load your data, or edit it like any other lineagelens.yml.\n")
    (new / CONFIG_NAME).write_text(header + yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    info = {"project_name": name, "created": time.time(), "default_database": db, "default_schema": schema,
            "sources": {k: [{kk: v for kk, v in r.items() if kk in ("name", "size", "detected", "models", "reports", "files")} for r in st[k]] for k in SLOTS}}
    (new / INFO_FILE).write_text(json.dumps(info, indent=1), encoding="utf-8")
    # One upload workspace at a time: replace any previous one.
    for p in base.iterdir():
        if p.is_dir() and p.name not in (STAGING_DIR, new.name):
            shutil.rmtree(p, ignore_errors=True)
    final = base / slug
    os.replace(new, final)
    clear_staging()
    _write_active({"project": slug, "active": True})
    log.info("upload workspace created", extra={"project": slug, "path": str(final)})
    return final / CONFIG_NAME


def remove_workspace() -> None:
    """Delete every uploaded file, the staging area, the generated config and its database."""
    base = user_data_dir() / WORKSPACE_DIR
    shutil.rmtree(base, ignore_errors=True)
    log.info("upload workspace removed")
