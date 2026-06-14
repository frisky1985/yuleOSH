# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Request audit logging for yuleOSH API.

Logs all API requests to an audit_log table in the SQLite store.
Exposes GET /api/v1/audit for listing recent entries (admin only).
"""

import json
import time
from datetime import datetime

from . import json_ok, json_error, get_store


def log_request(method: str, path: str, status_code: int, ip: str, duration_ms: float):
    """Record an API request in the audit log."""
    _ensure_table()
    store = get_store()
    now = datetime.now().isoformat()
    store.conn.execute(
        "INSERT INTO audit_log (timestamp, method, path, status_code, ip, duration_ms) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (now, method, path, status_code, ip, duration_ms),
    )
    store.conn.commit()


def _ensure_table():
    """Create the audit_log table if it does not exist."""
    store = get_store()
    store.conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            ip TEXT,
            duration_ms REAL
        )
    """)
    store.conn.commit()


def handle_audit(method: str, path_tail: str, body: dict, query: dict, **kwargs) -> tuple[dict, int]:
    """GET /api/v1/audit — list recent audit entries (admin only).

    Query params:
        limit (int, default 50): max entries to return
        offset (int, default 0): pagination offset
    """
    if method != "GET":
        return json_error("Method not allowed", 405)

    if path_tail:
        return json_error("Not found", 404)

    _ensure_table()

    try:
        limit = min(int(query.get("limit", [50])[0]), 200)
    except (ValueError, IndexError):
        limit = 50

    try:
        offset = int(query.get("offset", [0])[0])
    except (ValueError, IndexError):
        offset = 0

    store = get_store()
    cur = store.conn.execute(
        "SELECT id, timestamp, method, path, status_code, ip, duration_ms "
        "FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    entries = [dict(r) for r in cur.fetchall()]

    # Total count
    count_cur = store.conn.execute("SELECT COUNT(*) as c FROM audit_log")
    total = count_cur.fetchone()["c"]

    return json_ok({
        "entries": entries,
        "count": len(entries),
        "total": total,
        "limit": limit,
        "offset": offset,
    })
