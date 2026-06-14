# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Evidence endpoints — generate, list files, download compliance pack."""

import os
import sys
import subprocess
from pathlib import Path

from . import json_ok, json_error


def handle_evidence(method: str, path_tail: str, body: dict, query: dict, handler=None):
    """Route to evidence sub-resources."""
    if path_tail == "generate" and method == "POST":
        return _generate_evidence(body)
    elif path_tail == "files" and method == "GET":
        return _list_evidence_files()
    elif path_tail == "pack" and method == "GET":
        return _download_pack(handler)
    return json_error(f"Unknown evidence resource: {path_tail}", 404)


def _generate_evidence(body: dict) -> tuple[dict, int]:
    """POST /api/v1/evidence/generate — run evidence generation."""
    project_dir = body.get("project_dir") or os.environ.get(
        "OSH_HOME", str(Path(__file__).resolve().parent.parent.parent)
    )

    try:
        result = subprocess.run(
            [sys.executable, "src/evidence/pack.py", "pack"],
            capture_output=True, text=True, timeout=120,
            cwd=project_dir, check=False,
        )
        return json_ok({
            "status": "completed",
            "project_dir": project_dir,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        })
    except subprocess.TimeoutExpired:
        return json_error("Evidence generation timed out", 504)
    except (OSError, subprocess.CalledProcessError) as e:
        return json_error("Evidence generation error: " + str(e), 500)


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


def _download_pack(handler) -> tuple[dict, int]:
    """GET /api/v1/evidence/pack — download compliance ZIP pack."""
    from . import OSH_HOME

    zip_path = Path(OSH_HOME) / ".osh" / "evidence" / "compliance-pack.zip"
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
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(data)
        # Signal that the response was already sent
        return None

    return json_ok({
        "path": str(zip_path),
        "size": zip_path.stat().st_size,
        "status": "ready",
    })
