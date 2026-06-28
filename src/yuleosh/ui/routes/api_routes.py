"""
yuleOSH Dashboard — API endpoint route handlers.

Extracts API endpoint logic (status, health, evidence, reviews, CI results)
from the monolithic OSHHandler into standalone helper functions.
"""

import json
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler


def handle_status(handler: BaseHTTPRequestHandler) -> dict:
    """Return basic server status."""
    return {
        "status": "running",
        "osh_home": os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "version": "1.0.0",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }


def handle_health(handler: BaseHTTPRequestHandler) -> dict:
    """Return health check data."""
    try:
        from yuleosh.ui.auth import AUTH_ENABLED
    except ImportError:
        AUTH_ENABLED = False
    try:
        from yuleosh.ui.auth_extended import get_session_user
        tenant_auth = True
    except ImportError:
        tenant_auth = False

    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": None,
        "auth_enabled": AUTH_ENABLED,
        "tenant_auth": tenant_auth,
        "osh_home": os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    }


def list_evidence(handler: BaseHTTPRequestHandler) -> dict:
    """List evidence files from the .osh/evidence directory."""
    OSH_HOME = os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ev_dir = Path(OSH_HOME) / ".osh" / "evidence"
    files = []
    if ev_dir.exists():
        for f in sorted(ev_dir.iterdir()):
            if f.is_file() and f.name != "compliance-pack.zip":
                files.append({
                    "name": f.name,
                    "size": f"{f.stat().st_size} B",
                    "mtime": f.stat().st_mtime,
                })
        zip_file = ev_dir / "compliance-pack.zip"
        if zip_file.exists():
            files.append({
                "name": "compliance-pack.zip 🎯",
                "size": f"{zip_file.stat().st_size} B",
                "mtime": zip_file.stat().st_mtime,
            })
    return {"files": files, "count": len(files)}


def list_reviews(handler: BaseHTTPRequestHandler) -> dict:
    """List review sessions from the .osh/reviews directory."""
    OSH_HOME = os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    rev_dir = Path(OSH_HOME) / ".osh" / "reviews"
    sessions = []
    if rev_dir.exists():
        for d in sorted(rev_dir.iterdir()):
            if d.is_dir():
                sess_file = d / "review-session.json"
                if sess_file.exists():
                    data = json.loads(sess_file.read_text())
                    sessions.append(data)
    return {"sessions": sessions, "count": len(sessions)}


def list_ci_results(handler: BaseHTTPRequestHandler) -> dict:
    """List CI layer results from the .osh/ci directory."""
    OSH_HOME = os.environ.get("OSH_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ci_dir = Path(OSH_HOME) / ".osh" / "ci"
    results = []
    if ci_dir.exists():
        for f in sorted(ci_dir.glob("layer*.json")):
            data = json.loads(f.read_text())
            results.append(data)
    return {"results": results, "count": len(results)}


def handle_pipeline_status(handler: BaseHTTPRequestHandler, path: str):
    """GET /api/v1/pipeline/status/{job_id}"""
    job_id = path.rsplit("/", 1)[-1]
    try:
        from yuleosh.pipeline.async_runner import get_job_status
        status = get_job_status(job_id)
        if status:
            return status
        else:
            return {"error": "Job not found"}, 404
    except Exception:
        return {"error": "Pipeline status unavailable"}, 500


def handle_usage(handler: BaseHTTPRequestHandler) -> dict:
    """Get current org usage summary."""
    token = None
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]

    if not token:
        return {"error": "Unauthorized"}, 401

    try:
        from yuleosh.ui.auth_extended import get_session_user
        user = get_session_user(token)
        if not user:
            return {"error": "Invalid session"}, 401
        from yuleosh.store import Store
        store = Store()
        from yuleosh.usage.metering import get_usage_summary
        summary = get_usage_summary(store, user["org_id"])
        return summary
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}, 500
