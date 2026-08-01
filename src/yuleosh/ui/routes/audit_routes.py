# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Audit log API route handlers (SAAS-4).

Endpoints:
    GET  /api/v1/audit?tenant=X&from=2026-07-01&to=2026-07-27&action=Y&actor=Z
    POST /api/v1/audit  — Record an audit event programmatically
"""

import json
import logging
import urllib.parse
from http.server import BaseHTTPRequestHandler
from typing import Optional

from yuleosh.audit.model import AuditLog


logger = logging.getLogger("audit.routes")


def _get_token(handler: BaseHTTPRequestHandler) -> Optional[str]:
    auth = handler.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _require_auth(handler: BaseHTTPRequestHandler) -> Optional[dict]:
    from yuleosh.ui.auth_extended import get_session_user
    token = _get_token(handler)
    if not token:
        _send_json(handler, {"error": "Authorization required"}, 401)
        return None
    user_info = get_session_user(token)
    if not user_info:
        _send_json(handler, {"error": "Invalid session"}, 401)
        return None
    return user_info


def _require_audit_role(handler: BaseHTTPRequestHandler, user_info: dict):
    """RBAC: only admin and auditor can view audit logs."""
    from yuleosh.rbac import check_role
    if not check_role(user_info, "audit", "view"):
        _send_json(handler, {"error": "Insufficient permissions. Admin or Auditor role required."}, 403)
        return False
    return True


def _send_json(handler: BaseHTTPRequestHandler, data, status: int = 200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    """Read and parse the request body (P1-5: unified clamped read_body).

    Delegates to yuleosh.api.read_body which clamps Content-Length to 10 MB
    and converts malformed headers to BadRequest.  Invalid JSON / bad
    Content-Length yield {} — caller validation returns the 4xx.
    """
    from yuleosh.api import read_body, BadRequest
    try:
        return read_body(handler)
    except BadRequest:
        return {}


# ── GET: Query audit logs ──────────────────────────────────────────────────

def handle_get_audit_logs(handler: BaseHTTPRequestHandler):
    """GET /api/v1/audit — Query audit events.

    Query parameters:
        tenant  — Filter by tenant slug
        from    — Start date YYYY-MM-DD (default: 30 days ago)
        to      — End date YYYY-MM-DD (default: today)
        action  — Filter by action type (e.g. 'project.create')
        actor   — Filter by actor (e.g. 'user:42')
        limit   — Max results (default: 100)
    """
    user = _require_auth(handler)
    if not user:
        return
    if not _require_audit_role(handler, user):
        return

    parsed = urllib.parse.urlparse(handler.path)
    params = urllib.parse.parse_qs(parsed.query)

    tenant = params.get("tenant", [""])[0] or user.get("org_slug", "")
    from_date = params.get("from", [""])[0] or ""
    to_date = params.get("to", [""])[0] or ""
    action = params.get("action", [""])[0] or ""
    actor = params.get("actor", [""])[0] or ""
    limit_str = params.get("limit", ["100"])[0]

    try:
        limit = int(limit_str)
    except (ValueError, TypeError):
        limit = 100
    if limit > 5000:
        limit = 5000

    audit_log = AuditLog()
    events = audit_log.query(
        tenant=tenant,
        from_date=from_date,
        to_date=to_date,
        action=action,
        actor=actor,
        limit=limit,
    )

    summary = audit_log.get_summary(tenant=tenant, from_date=from_date, to_date=to_date)

    _send_json(handler, {
        "ok": True,
        "events": [e.to_dict() for e in events],
        "total": len(events),
        "summary": summary,
    })


# ── POST: Record audit event ────────────────────────────────────────────────

def handle_post_audit_event(handler: BaseHTTPRequestHandler):
    """POST /api/v1/audit — Record a programmatic audit event.

    Body:
        {actor, action, target, tenant, detail}
    """
    user = _require_auth(handler)
    if not user:
        return
    if not _require_audit_role(handler, user):
        return

    body = _read_body(handler)
    actor = body.get("actor", user.get("email", f"user:{user['user_id']}"))
    action = body.get("action", "")
    target = body.get("target", "")
    tenant = body.get("tenant", user.get("org_slug", ""))
    detail = body.get("detail", {})

    if not action:
        _send_json(handler, {"error": "action is required"}, 400)
        return

    audit_log = AuditLog()
    event = audit_log.record(
        actor=actor,
        action=action,
        target=target,
        tenant=tenant,
        detail=detail,
    )

    _send_json(handler, {
        "ok": True,
        "event": event.to_dict(),
    }, 201)
