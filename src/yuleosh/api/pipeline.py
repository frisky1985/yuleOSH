# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Pipeline endpoints — run, status, list, get, delete."""

import json
import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

from . import json_ok, json_error
from .middleware import require_auth

# ── Submission throttle (P0): protect the async thread pool from DoS ──
_TRIGGER_GATE_LOCK = threading.Lock()
_TRIGGER_GATE_TIMES: list[float] = []
_TRIGGER_MAX_PER_WINDOW = 10        # max pipeline submissions per window
_TRIGGER_WINDOW_SECONDS = 60.0
_MAX_ARXML_BYTES = 1_000_000        # 1 MB
_MAX_CONFIG_JSON_BYTES = 1_000_000  # 1 MB


def _check_trigger_throttle() -> bool:
    """Return True if a new submission is allowed (sliding window)."""
    global _TRIGGER_GATE_TIMES
    now = time.time()
    with _TRIGGER_GATE_LOCK:
        _TRIGGER_GATE_TIMES = [
            t for t in _TRIGGER_GATE_TIMES if now - t < _TRIGGER_WINDOW_SECONDS
        ]
        if len(_TRIGGER_GATE_TIMES) >= _TRIGGER_MAX_PER_WINDOW:
            return False
        _TRIGGER_GATE_TIMES.append(now)
        return True


@require_auth
def handle_pipeline(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to pipeline sub-resources."""
    if path_tail in ("", "run"):
        if method == "POST":
            return _run_pipeline(body)
        return json_error("Use POST to run pipeline", 405)

    if path_tail == "trigger":
        if method == "POST":
            return _trigger_pipeline(body)
        return json_error("Use POST to trigger pipeline", 405)

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

    # ── P0-B: legacy pipeline sub-routes restored ───────────────────────
    # These endpoints predate the modular router (served by
    # ui/routes/pipeline_routes via handler_helpers) and were shadowed into
    # 404/401 dead code after the router wiring.  Delegate to the same
    # legacy handlers so consumers (incl. old frontends/scripts) keep
    # working: 401 without valid auth, 200 data with auth.
    if path_tail == "runs" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_runs
        result = handle_pipeline_runs(kwargs.get("handler"))
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "stats" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_stats
        result = handle_pipeline_stats(kwargs.get("handler"))
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "yuleasr-status" and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_status
        result = handle_yuleasr_status(kwargs.get("handler"))
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "validate" and method == "GET":
        from yuleosh.pipeline.config_validator import validate_pipeline_config
        result = validate_pipeline_config(
            project_dir=os.environ.get("OSH_HOME", ""))
        return {"ok": True, **result}, 200

    if path_tail.startswith("status/") and method == "GET":
        from yuleosh.ui.routes.pipeline_routes import handle_pipeline_status
        full_path = f"/api/v1/pipeline/{path_tail}"
        result = handle_pipeline_status(kwargs.get("handler"), full_path)
        return (result, 200) if isinstance(result, dict) else result

    if path_tail == "yuleasr-notify" and method == "POST":
        from yuleosh.ui.routes.pipeline_routes import handle_yuleasr_notify
        raw = json.dumps(body).encode("utf-8") if body else b"{}"
        result = handle_yuleasr_notify(kwargs.get("handler"), raw)
        return (result, 200) if isinstance(result, dict) else result

    return json_error(f"Unknown pipeline resource: {path_tail}", 404)


def _run_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/run — run pipeline for a spec.

    SECURITY: resolves path safely and validates it's within project root.
    """
    spec_path = body.get("spec", "")
    name = body.get("name")

    if not spec_path:
        return json_error("'spec' is required")

    from . import OSH_HOME
    project_root = Path(OSH_HOME).resolve()
    if Path(spec_path).is_absolute():
        resolved = Path(spec_path).resolve()
    else:
        resolved = (project_root / spec_path.lstrip("/")).resolve()

    # SECURITY: path traversal guard — resolved path MUST be inside project root
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return json_error("Spec path must be within project directory", 403)

    if not resolved.exists():
        return json_error(f"Spec file not found: {resolved}")

    if not resolved.is_file():
        return json_error(f"Spec path is not a file", 400)

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


def _trigger_pipeline(body: dict) -> tuple[dict, int]:
    """POST /api/v1/pipeline/trigger — start a pipeline run.

    Security (P0):
      - requires authentication (enforced by @require_auth on handle_pipeline)
      - project_dir must resolve inside OSH_HOME (blocks ../ traversal)
      - type/layer whitelist
      - arxml_content / config_json size caps
      - sliding-window submission throttle (protects the async thread pool)
    """
    if not isinstance(body, dict):
        return json_error("Request body must be a JSON object", 400)

    project_dir = body.get("project_dir") or os.environ.get("OSH_HOME", "")
    if not project_dir:
        return json_error("project_dir is required or set OSH_HOME", 400)

    osh_home = Path(os.environ.get("OSH_HOME", "")).resolve()
    try:
        resolved = Path(project_dir).expanduser().resolve()
        resolved.relative_to(osh_home)
    except (ValueError, OSError):
        return json_error("project_dir must be inside OSH_HOME", 403)

    pipeline_type = body.get("type", "full")
    if pipeline_type not in ("full", "full_pipeline", "ci"):
        return json_error("type must be one of: full, ci", 400)

    layer = body.get("layer", 1)
    if layer not in (1, 2, 3):
        return json_error("layer must be 1, 2 or 3", 400)

    arxml_content = body.get("arxml_content") or ""
    if len(arxml_content) > _MAX_ARXML_BYTES:
        return json_error(f"arxml_content too large (max {_MAX_ARXML_BYTES} bytes)", 400)

    config_json = body.get("config_json")
    if config_json is not None and len(config_json) > _MAX_CONFIG_JSON_BYTES:
        return json_error(f"config_json too large (max {_MAX_CONFIG_JSON_BYTES} bytes)", 400)

    if not _check_trigger_throttle():
        return json_error(
            "Too many pipeline submissions. Try again later.", 429)

    from yuleosh.pipeline.async_runner import submit_pipeline, submit_full_pipeline

    try:
        if pipeline_type in ("full", "full_pipeline"):
            job_id = submit_full_pipeline(
                project_dir=str(resolved),
                config_json=config_json,
                arxml_content=arxml_content,
            )
        else:
            job_id = submit_pipeline(project_dir=str(resolved), layer=layer)

        return json_ok({
            "job_id": job_id,
            "status": "queued",
            "type": pipeline_type,
            "poll_url": f"/api/v1/pipeline/status/{job_id}",
        })
    except Exception as e:
        return json_error(f"Pipeline trigger failed: {e}", 500)


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
