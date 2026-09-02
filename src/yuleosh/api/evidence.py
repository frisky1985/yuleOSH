
# @req RS-006  @req RS-005
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Evidence endpoints — generate, list files, download compliance pack."""

import os
import shutil
import sys
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from . import json_ok, json_error
from ._errors import internal_error
from .middleware import require_auth
from yuleosh.api.cors import get_cors_origin


def _qp(query: dict, key: str, default: str = "") -> str:
    """Get a query parameter value (list-safe, like logs._qp)."""
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return str(val) if val is not None else default


@require_auth
def handle_evidence(method: str, path_tail: str, body: dict, query: dict, handler=None, **kwargs):
    """Route to evidence sub-resources."""
    if path_tail == "generate" and method == "POST":
        return _generate_evidence(body)
    elif path_tail == "files" and method == "GET":
        return _list_evidence_files()
    elif path_tail == "history" and method == "GET":
        return _list_evidence_history()
    elif path_tail == "pack" and method == "GET":
        return _download_pack(handler, query)
    elif path_tail == "file" and method == "GET":
        return _download_file(handler, query)
    return json_error(f"Unknown evidence resource: {path_tail}", 404)


def _snapshot_pack() -> str | None:
    """Copy the freshly generated compliance-pack.zip to a timestamped version
    snapshot so each generation is retrievable later (evidence history).

    Returns the versioned file name, or None if no pack exists yet.
    """
    from . import OSH_HOME

    ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
    src = ev_dir / "compliance-pack.zip"
    if not src.exists():
        return None
    ev_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    version = f"compliance-pack-{ts}.zip"
    dst = ev_dir / version
    n = 1
    while dst.exists():
        version = f"compliance-pack-{ts}-{n}.zip"
        dst = ev_dir / version
        n += 1
    shutil.copy2(src, dst)
    return version


def snapshot_bundle(bundle_dir: str) -> str | None:
    """Zip an evidence *bundle directory* (e.g. `.yuleosh/evidence-bundle`)
    into a versioned `.osh/evidence/compliance-pack-<ts>.zip` and overwrite the
    latest `compliance-pack.zip`.  Returns the versioned name, or None when the
    bundle dir is missing.

    Used by the dashboard generate flow so its real generations also land in
    the evidence history list (the dashboard produces a bundle dir + manifest,
    whereas the evidence-page path produces compliance-pack.zip directly).
    """
    from . import OSH_HOME

    src = Path(bundle_dir)
    if not src.exists() or not src.is_dir():
        return None
    ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    version = f"compliance-pack-{ts}.zip"
    dst = ev_dir / version
    n = 1
    while dst.exists():
        version = f"compliance-pack-{ts}-{n}.zip"
        dst = ev_dir / version
        n += 1
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src))
    shutil.copy2(dst, ev_dir / "compliance-pack.zip")
    return version


def _generate_evidence(body: dict) -> tuple[dict, int]:
    """POST /api/v1/evidence/generate — run evidence generation.

    SECURITY (SEC-C1): project_dir must resolve inside OSH_HOME — same
    guard as the pipeline trigger.  Otherwise an authenticated user could
    run the pack script with an arbitrary cwd (e.g. /etc) and probe/write
    anywhere on the server.
    """
    from . import OSH_HOME as _api_osh_home
    raw_dir = body.get("project_dir") or os.environ.get(
        "OSH_HOME", str(Path(__file__).resolve().parent.parent.parent)
    )
    try:
        project_dir = str(Path(raw_dir).expanduser().resolve())
        Path(project_dir).relative_to(Path(_api_osh_home).resolve())
    except (ValueError, TypeError, OSError):
        return json_error("project_dir must be inside OSH_HOME", 403)

    try:
        result = subprocess.run(
            [sys.executable, "src/evidence/pack.py", "pack"],
            capture_output=True, text=True, timeout=120,
            cwd=project_dir, check=False,
        )
        version = None
        if result.returncode == 0:
            version = _snapshot_pack()
        return json_ok({
            "status": "completed" if result.returncode == 0 else "failed",
            "project_dir": project_dir,
            "returncode": result.returncode,
            "version": version,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        })
    except subprocess.TimeoutExpired:
        return json_error("Evidence generation timed out", 504)
    except (OSError, subprocess.CalledProcessError) as e:
        # SEC-C2: never echo internal exception details to the client.
        return internal_error("evidence", e)


def _list_evidence_files() -> tuple[dict, int]:
    """GET /api/v1/evidence/files — list generated evidence files."""
    from . import OSH_HOME

    ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
    files = []
    if ev_dir.exists():
        for f in sorted(ev_dir.iterdir()):
            if f.is_file():
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "type": f.suffix.lstrip("."),
                })

    return json_ok({"files": files, "count": len(files)})


def _list_evidence_history() -> tuple[dict, int]:
    """GET /api/v1/evidence/history — list versioned evidence pack snapshots.

    Each generation snapshots compliance-pack.zip to compliance-pack-<ts>.zip,
    so this returns a chronological (newest-first) list of downloadable versions.
    """
    from . import OSH_HOME

    ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
    versions = []
    if ev_dir.exists():
        # Sort by mtime (newest first) — not by name, because same-second
        # collisions get a "-1" suffix that sorts before the plain name
        # lexicographically and would invert the intended order.
        for f in sorted(
            ev_dir.glob("compliance-pack-*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            versions.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime,
                "type": "zip",
            })
    latest = ev_dir / "compliance-pack.zip"
    return json_ok({
        "versions": versions,
        "count": len(versions),
        "has_latest": latest.exists(),
    })


def _download_pack(handler, query: dict | None = None) -> tuple[dict, int]:
    """GET /api/v1/evidence/pack — download compliance ZIP pack.

    With ?version=<name> downloads a specific history snapshot; otherwise the
    latest compliance-pack.zip.  version must be a bare filename (path-traversal
    guarded) and resolve inside the evidence dir.
    """
    from . import OSH_HOME

    ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
    version = _qp(query or {}, "version").strip() if query else ""

    # Only treat ?version= as a real snapshot when it looks like one
    # (compliance-pack-<ts>.zip, bare name).  Unknown/legacy params such as
    # the dashboard's ?task_id= fall back to the latest pack, not a 400.
    is_snapshot = bool(version) and version.startswith("compliance-pack-") and version.endswith(".zip") and "/" not in version and "\\" not in version and version not in (".", "..")

    if is_snapshot:
        zip_path = ev_dir / version
        if not zip_path.exists():
            return json_error("Evidence version not found", 404)
    elif version:
        # Explicit ?version= that is not a real snapshot name (e.g. a
        # traversal attempt) — reject rather than silently serving latest.
        return json_error("Invalid version name", 400)
    else:
        zip_path = ev_dir / "compliance-pack.zip"
        if not zip_path.exists():
            return json_error("Compliance pack not found. Run evidence generation first.", 404)

    if handler is not None:
        data = zip_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/zip")
        handler.send_header(
            "Content-Disposition",
            'attachment; filename="compliance-pack.zip"',
        )
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Access-Control-Allow-Origin", get_cors_origin(handler.headers.get("Origin")))
        handler.end_headers()
        handler.wfile.write(data)
        # Signal that the response was already sent
        return None

    return json_ok({
        "path": str(zip_path),
        "size": zip_path.stat().st_size,
        "status": "ready",
    })


# Single-file download: map extension → Content-Type so the browser opens
# text artifacts inline-friendly and still downloads binaries correctly.
_FILE_CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _download_file(handler, query: dict | None = None) -> tuple[dict, int] | None:
    """GET /api/v1/evidence/file?name=<bare_name> — download one evidence file.

    Lets an auditor grab a single artifact (e.g. traceability-matrix.md,
    review-log.json) without downloading and unzipping the whole pack.

    SECURITY: `name` must be a bare file name (no path separators, no
    dot-segments, no quote/newline/NUL to keep Content-Disposition well-formed),
    and the resolved path must stay inside .osh/evidence (also blocks symlink
    escapes).  Missing file → 404, bad name → 400.
    """
    from . import OSH_HOME

    ev_dir = Path(OSH_HOME).resolve() / ".osh" / "evidence"
    name = (_qp(query or {}, "name") or "").strip()

    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or name.startswith(".")
        or any(c in name for c in ('"', "\n", "\r", "\x00"))
    ):
        return json_error("Invalid file name", 400)

    try:
        target = (ev_dir / name).resolve()
        target.relative_to(ev_dir)
    except (ValueError, OSError):
        return json_error("Invalid file name", 400)

    if not target.is_file():
        return json_error("Evidence file not found", 404)

    ctype = _FILE_CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")

    if handler is not None:
        data = target.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Content-Disposition", f'attachment; filename="{name}"')
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Access-Control-Allow-Origin", get_cors_origin(handler.headers.get("Origin")))
        handler.end_headers()
        handler.wfile.write(data)
        # Signal that the response was already sent
        return None

    return json_ok({
        "path": str(target),
        "name": name,
        "size": target.stat().st_size,
        "content_type": ctype,
        "status": "ready",
    })
