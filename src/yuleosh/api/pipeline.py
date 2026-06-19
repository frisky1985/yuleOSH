# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Pipeline endpoints — run, status, list, get, delete."""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

from . import json_ok, json_error


def handle_pipeline(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to pipeline sub-resources."""
    if path_tail in ("", "run"):
        if method == "POST":
            return _run_pipeline(body)
        return json_error("Use POST to run pipeline", 405)

    if path_tail == "status":
        if method == "GET":
            return _list_pipelines()
        return json_error("Use GET for status", 405)

    if path_tail == "list" or (path_tail == "" and method == "GET"):
        return _list_pipelines()

    if path_tail == "steps":
        if method == "GET":
            return _list_pipeline_steps()
        return json_error("Use GET for steps", 405)

    return json_error(f"Unknown pipeline resource: {path_tail}", 404)


def _run_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/run — run pipeline for a spec."""
    spec_path = body.get("spec", "")
    name = body.get("name")

    if not spec_path:
        return json_error("'spec' is required")

    resolved = Path(spec_path)
    if not resolved.is_absolute():
        from . import OSH_HOME
        resolved = Path(OSH_HOME) / resolved

    if not resolved.exists():
        return json_error(f"Spec file not found: {resolved}")

    try:
        result = subprocess.run(
            [sys.executable, "src/pipeline/run.py", str(resolved)],
            capture_output=True, text=True, timeout=300,
            cwd=os.environ.get("OSH_HOME", Path(__file__).resolve().parent.parent.parent),
        )
        return json_ok({
            "spec": str(resolved),
            "name": name or resolved.stem,
            "exit_code": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
            "session_dir": str(Path(resolved).parent / ".osh" / "sessions"),
        })
    except subprocess.TimeoutExpired:
        return json_error("Pipeline timed out after 300s", 504)
    except Exception as e:
        return json_error(f"Pipeline error: {e}", 500)


def _list_pipeline_steps() -> tuple[dict, int]:
    """GET /api/v1/pipeline/steps — list all pipeline step definitions."""
    from yuleosh.pipeline.step_handlers import PIPELINE_STEPS

    steps = []
    for idx, (step_key, agent, name, _handler) in enumerate(PIPELINE_STEPS, start=1):
        steps.append({
            "index": idx,
            "key": step_key,
            "agent": agent,
            "name": name,
        })

    return json_ok({
        "steps": steps,
        "count": len(steps),
    })


def _list_pipelines() -> tuple[dict, int]:
    """GET /api/v1/pipeline/status — list all pipeline sessions."""
    from . import OSH_HOME
    from yuleosh.store import Store

    store = Store()
    db_sessions = store.list_pipelines()

    # Also scan filesystem sessions
    sessions_dir = Path(OSH_HOME) / ".osh" / "sessions"
    fs_sessions = []
    if sessions_dir.exists():
        for d in sorted(sessions_dir.iterdir(), reverse=True):
            if d.is_dir():
                sess_file = d / "session.json"
                if sess_file.exists():
                    data = json.loads(sess_file.read_text())
                    fs_sessions.append(data)

    return json_ok({
        "sessions": fs_sessions,
        "count": len(fs_sessions),
    })
