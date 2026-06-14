# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Healthcheck endpoint — comprehensive system health monitoring.

Checks:
- Database connectivity (SELECT 1)
- Store status (pipeline/ci/review counts)
- Disk space on .yuleosh/ directory
- Uptime tracking
"""

import os
import time
import json
import shutil
from pathlib import Path

from . import json_ok, json_error, OSH_HOME
from yuleosh.store import Store

# Uptime tracking
_START_TIME = time.time()


def handle_health(method: str, **kwargs):
    """GET /api/v1/health — return full system health status."""
    store = Store()

    # 1. Database connectivity
    db_status = _check_db(store)

    # 2. Store counts
    store_status = _check_store(store)

    # 3. Disk space on .yuleosh/
    disk_status = _check_disk()

    # 4. Uptime
    uptime_seconds = int(time.time() - _START_TIME)

    # Aggregate status
    all_ok = (
        db_status == "ok"
        and not disk_status.get("error")
    )
    overall_status = "healthy" if all_ok else "degraded"

    return json_ok({
        "status": overall_status,
        "db": db_status,
        "store": store_status,
        "disk": disk_status,
        "uptime_seconds": uptime_seconds,
        "version": "0.1.0",
        "auth_enabled": _auth_enabled(),
        "osh_home": OSH_HOME,
    })


def _check_db(store: Store) -> str:
    """Verify database connectivity with SELECT 1."""
    try:
        cur = store.conn.execute("SELECT 1 AS ok")
        row = cur.fetchone()
        if row and row["ok"] == 1:
            return "ok"
        return "error: unexpected result"
    except Exception as e:
        return f"error: {e}"


def _check_store(store: Store) -> dict:
    """Return counts from all store tables."""
    try:
        pipe_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM pipelines"
        ).fetchone()["c"]
        ci_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM ci_runs"
        ).fetchone()["c"]
        review_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM reviews"
        ).fetchone()["c"]
        proj_count = store.conn.execute(
            "SELECT COUNT(*) as c FROM projects"
        ).fetchone()["c"]
        return {
            "pipelines": pipe_count,
            "ci_runs": ci_count,
            "reviews": review_count,
            "projects": proj_count,
        }
    except Exception as e:
        return {"error": str(e)}


def _check_disk() -> dict:
    """Check disk space on the .yuleosh/ directory."""
    yuleosh_dir = Path(OSH_HOME) / ".yuleosh"
    if not yuleosh_dir.exists():
        yuleosh_dir.mkdir(parents=True, exist_ok=True)
    try:
        usage = shutil.disk_usage(str(yuleosh_dir))
        # Calculate total/free/used in MB
        total_mb = usage.total // (1024 * 1024)
        free_mb = usage.free // (1024 * 1024)
        used_mb = usage.used // (1024 * 1024)
        used_pct = round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0
        return {
            "path": str(yuleosh_dir),
            "total_mb": total_mb,
            "free_mb": free_mb,
            "used_mb": used_mb,
            "used_pct": used_pct,
            "ok": used_pct < 90,  # Flag if >90% full
        }
    except Exception as e:
        return {"error": str(e), "path": str(yuleosh_dir)}


def _auth_enabled() -> bool:
    try:
        from yuleosh.ui.auth import AUTH_ENABLED
        return AUTH_ENABLED
    except (ImportError, Exception):
        return False


def _extract_v1(path: str) -> str:
    """Strip /api/v1/ prefix, return the resource path."""
    for prefix in ("/api/v1/", "/api/v1"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path.lstrip("/")
