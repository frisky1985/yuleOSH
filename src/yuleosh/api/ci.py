# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""CI endpoints — run layers, list runs."""

import json
import os
import sys
import subprocess
from pathlib import Path

from . import json_ok, json_error
from .middleware import require_auth


@require_auth
def handle_ci(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to CI sub-resources."""
    if path_tail == "runs" and method == "GET":
        return _list_ci_runs()

    if path_tail.startswith("run/"):
        layer = path_tail.split("/")[1]
        if method == "POST":
            return _run_ci_layer(layer)
        return json_error("Use POST to run CI", 405)

    return json_error(f"Unknown CI resource: {path_tail}", 404)


def _run_ci_layer(layer: str) -> tuple[dict, int]:
    """POST /api/v1/ci/run/{layer} — run a CI layer."""
    if layer not in ("1", "2", "3"):
        return json_error(f"Invalid CI layer: {layer}. Must be 1, 2, or 3")

    project_dir = os.environ.get("OSH_HOME", Path(__file__).resolve().parent.parent.parent)

    try:
        result = subprocess.run(
            [sys.executable, "src/ci/run.py", layer],
            capture_output=True, text=True, timeout=180,
            cwd=project_dir,
        )
        return json_ok({
            "layer": int(layer),
            "exit_code": result.returncode,
            "status": "passed" if result.returncode == 0 else "failed",
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
        })
    except subprocess.TimeoutExpired:
        return json_error("CI run timed out after 180s", 504)
    except Exception as e:
        return json_error(f"CI error: {e}", 500)


def _list_ci_runs() -> tuple[dict, int]:
    """GET /api/v1/ci/runs — list all CI runs."""
    from . import OSH_HOME

    ci_dir = Path(OSH_HOME) / ".osh" / "ci"
    results = []
    if ci_dir.exists():
        for f in sorted(ci_dir.glob("layer*.json"), reverse=True):
            data = json.loads(f.read_text())
            results.append(data)

    return json_ok({"results": results, "count": len(results)})
