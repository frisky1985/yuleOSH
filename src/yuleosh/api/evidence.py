
# @req RS-006  @req RS-005
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Evidence endpoints — generate, list files, download compliance pack."""

import os
import shutil
import sys
import subprocess
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
