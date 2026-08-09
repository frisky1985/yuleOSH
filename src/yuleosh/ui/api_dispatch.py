# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard — API route dispatch (TD-004, split from server.py).

Domain: API routing for the OSHHandler server — the /api/v1/* gateway
(api_v1_dispatch, P0-1 fail-closed) and the legacy /api/* endpoint
delegation helpers (_get_health, _get_status, _list_evidence,
_get_reviews, _get_ci_results, _handle_api, _handle_login).  Moved
verbatim from yuleosh/ui/server.py; the helpers are attached to
OSHHandler by server.py.
"""

from http.server import BaseHTTPRequestHandler


def api_v1_dispatch(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """Dispatch /api/v1/* requests to the modular router.

    Returns True when the router handled the request (response written).
    Returns False only for non-API paths, so callers fall back to
    page/static serving.

    P0-1 guarantee: a /api/v1/* path is NEVER degraded to an HTML page.
    If the router cannot serve it (e.g. missing YULEOSH_JWT_SECRET raises
    at import time, or any other unexpected failure), a JSON 500 error is
    written instead, so API clients always receive machine-readable
    responses.
    """
    if not path.startswith("/api/v1/"):
        return False
    try:
        from yuleosh.api.router import dispatch
        dispatch(handler, path)
    except Exception as e:  # noqa: BLE001 — 故意 fail-closed：API 路径必须返回 JSON 错误
        # Fail closed for API paths — never fall through to HTML page
        # serving (the P0-1 symptom: /api/v1/* answered with a 200 HTML
        # landing page).
        try:
            handler._json_response(
                {"ok": False, "error": f"API dispatch failed: {e}"}, 500
            )
        except Exception:  # noqa: BLE001, S110 — 无 HTTP 管道（单元测试裸 mock）时静默，仍视为已处理
            # No live HTTP plumbing (e.g. bare mock in unit tests) —
            # nothing writable, but still report handled so callers do
            # not serve an HTML page for an API path.
            pass
    return True

def _get_health(self) -> dict:
    from yuleosh.ui.routes import handle_health
    return handle_health(self)

def _get_status(self) -> dict:
    from yuleosh.ui.routes import handle_status
    return handle_status(self)

def _list_evidence(self) -> list:
    from yuleosh.ui.routes import list_evidence
    return list_evidence(self)

def _get_reviews(self) -> list:
    from yuleosh.ui.routes import list_reviews
    return list_reviews(self)

def _get_ci_results(self) -> list:
    from yuleosh.ui.routes import list_ci_results
    return list_ci_results(self)

def _handle_api(self, action: str) -> None:
    from yuleosh.ui.routes import handle_api_action
    # FIX (v3.9.0 P1): handle_api_action already sends the response
    # (via auth_routes._send_json_response → self._json_response).  The
    # previous ``result = ...; self._json_response(result)`` emitted a
    # SECOND HTTP response ("…}HTTP/1.0 200 OK…null") on the same
    # connection — corrupted wire output for every /api/auth/* route.
    handle_api_action(self, action)

def _handle_login(self) -> None:
    from yuleosh.ui.routes import handle_auth_login
    content_length = int(self.headers.get("Content-Length", 0))
    body = self.rfile.read(content_length) if content_length else b"{}"
    result = handle_auth_login(self, body)
    if isinstance(result, dict):
        self._json_response(result)
    else:
        self.send_response(302)
        self.send_header("Location", "/dashboard")
        self.end_headers()
