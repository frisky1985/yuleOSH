# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""v3.4.4 P0-A / P0-B integration tests.

P0-A: the frontend token contract (sub/org — signed by ui/auth_extended)
      must pass api/middleware require_auth, so the REAL frontend login
      chain (signin → org/create → token) can call protected v1 APIs.
      The existing onboarding E2E masked this by injecting logic-level
      users + _make_jwt carrying BOTH field sets — these tests go over
      real HTTP with a real subprocess server.

P0-B: legacy /api/v1/* routes (tenant/billing/tenants/projects/audit and
      pipeline runs/stats/yuleasr-status/validate/status/{id}) that were
      shadowed into 404 dead code by the router wiring must be reachable
      again (401 before valid auth, or 200 JSON).
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn_server(env_extra: dict | None = None):
    """Start a real server subprocess WITH the JWT secret (and extra env)."""
    port = _free_port()
    env = dict(os.environ)
    env["YULEOSH_JWT_SECRET"] = "v344-p0ab-integration-secret-32chars!!"
    env["OSH_HOME"] = env_extra.pop("OSH_HOME", None) if env_extra else None
    env["OSH_HOME"] = env["OSH_HOME"] or str(REPO_ROOT / "data" / "v344-p0ab-osh")
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'src');"
            f"from yuleosh.ui.server import main; main(host='127.0.0.1', port={port})",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc, port
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise AssertionError(f"server subprocess did not come up (rc={proc.poll()})")


def _request(port: int, path: str, method: str = "GET", body: dict | None = None,
              token: str | None = None):
    """Real HTTP request helper. Returns (payload_dict, status)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read()
        try:
            return json.loads(raw), resp.status
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"raw": raw.decode("utf-8", errors="replace")}, resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return json.loads(raw), e.code
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"raw": raw.decode("utf-8", errors="replace")}, e.code


class TestP0A_FrontendLoginChainProtectedV1:
    """P0-A: real frontend login chain → protected v1 API returns 200 JSON.

    Uses a REAL subprocess server + REAL HTTP (urllib) for every step —
    no logic injection, no _make_jwt.
    """

    @pytest.fixture(scope="class")
    def server(self):
        proc, port = _spawn_server()
        yield port
        proc.kill()
        proc.wait(timeout=5)

    def _full_login_chain(self, port: int, email: str):
        """signin → org/create → returns the real frontend session token."""
        # 1. signin (first-time user → needs_org, org_setup token)
        data, status = _request(port, "/api/auth/signin", "POST", {"email": email})
        assert status == 200, f"signin failed: {data}"
        assert data.get("needs_org") is True
        setup_token = data["token"]
        assert setup_token, "org_setup token missing"

        # 2. org/create (binds token.email == body.email)
        body = {
            "org_name": "P0A Org",
            "org_slug": f"p0a-{abs(hash(email)) % 100000}",
            "project_name": "P0A Project",
            "project_slug": "p0a-project",
            "email": email,
            "password": "StrongPass123",
        }
        data, status = _request(port, "/api/org/create", "POST", body, token=setup_token)
        assert status == 200, f"org/create failed: {data}"
        assert "token" in data, f"session token missing: {data}"
        return data["token"], data

    def test_protected_v1_dashboard_projects_200(self, server):
        """Frontend token → GET /api/v1/dashboard/projects → 200 JSON."""
        email = f"p0a-dash-{int(time.time())}@test.com"
        token, _ = self._full_login_chain(server, email)
        data, status = _request(server, "/api/v1/dashboard/projects", token=token)
        assert status == 200, f"expected 200, got {status}: {data}"
        assert data.get("ok") is True

    def test_protected_v1_project_list_200(self, server):
        """Frontend token → GET /api/v1/project → 200 JSON."""
        email = f"p0a-proj-{int(time.time())}@test.com"
        token, _ = self._full_login_chain(server, email)
        data, status = _request(server, "/api/v1/project", token=token)
        assert status == 200, f"expected 200, got {status}: {data}"
        assert data.get("ok") is True

    def test_protected_v1_kb_articles_200(self, server):
        """Frontend token → GET /api/v1/kb/articles → 200 JSON."""
        email = f"p0a-kb-{int(time.time())}@test.com"
        token, _ = self._full_login_chain(server, email)
        data, status = _request(server, "/api/v1/kb/articles", token=token)
        assert status == 200, f"expected 200, got {status}: {data}"
        assert data.get("ok") is True

    def test_frontend_token_payload_is_sub_org(self, server):
        """Guard: the real frontend token MUST use sub/org (regression trap).

        If auth_extended ever starts signing user_id/org_id instead, this
        test still passes (both formats accepted) — but it documents the
        format the middleware must keep accepting.
        """
        import jwt as _jwt
        email = f"p0a-payload-{int(time.time())}@test.com"
        token, _ = self._full_login_chain(server, email)
        payload = _jwt.decode(token, options={"verify_signature": False})
        assert "sub" in payload
        assert "org" in payload
        assert "user_id" not in payload  # frontend format must stay sub/org

    def test_pipeline_runs_200_with_frontend_token(self, server):
        """P0-B: GET /api/v1/pipeline/runs → 200 JSON with valid auth."""
        email = f"p0a-runs-{int(time.time())}@test.com"
        token, _ = self._full_login_chain(server, email)
        data, status = _request(server, "/api/v1/pipeline/runs", token=token)
        assert status == 200, f"expected 200, got {status}: {data}"
        assert data.get("ok") is True
        assert "runs" in data

    def test_pipeline_stats_200_with_frontend_token(self, server):
        """P0-B: GET /api/v1/pipeline/stats → 200 JSON with valid auth."""
        email = f"p0a-stats-{int(time.time())}@test.com"
        token, _ = self._full_login_chain(server, email)
        data, status = _request(server, "/api/v1/pipeline/stats", token=token)
        assert status == 200, f"expected 200, got {status}: {data}"
        assert data.get("ok") is True


class TestP0B_LegacyRoutesReachable:
    """P0-B: legacy routes must NOT be 404 — 401 before auth or 200 data."""

    @pytest.fixture(scope="class")
    def server(self):
        proc, port = _spawn_server()
        yield port
        proc.kill()
        proc.wait(timeout=5)

    def test_tenant_projects_not_404(self, server):
        """GET /api/v1/tenant/foo/projects → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/tenant/foo/projects")
        assert status != 404, f"legacy tenant route is 404: {data}"
        assert status == 401
        assert isinstance(data, dict)

    def test_tenant_info_not_404(self, server):
        """GET /api/v1/tenant/foo → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/tenant/foo")
        assert status != 404, f"legacy tenant route is 404: {data}"
        assert status == 401

    def test_tenants_list_not_404(self, server):
        """GET /api/v1/tenants → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/tenants")
        assert status != 404, f"legacy tenants route is 404: {data}"
        assert status == 401

    def test_billing_usage_not_404(self, server):
        """GET /api/v1/billing/usage → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/billing/usage")
        assert status != 404, f"legacy billing route is 404: {data}"
        assert status == 401

    def test_billing_plan_not_404(self, server):
        """GET /api/v1/billing/plan → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/billing/plan")
        assert status != 404, f"legacy billing route is 404: {data}"
        assert status == 401

    def test_projects_get_not_404(self, server):
        """GET /api/v1/projects/whatever → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/projects/whatever")
        assert status != 404, f"legacy projects route is 404: {data}"
        assert status == 401

    def test_pipeline_runs_unauth_401(self, server):
        """GET /api/v1/pipeline/runs without token → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/pipeline/runs")
        assert status == 401, f"expected 401, got {status}: {data}"
        assert "error" in data

    def test_pipeline_stats_unauth_401(self, server):
        """GET /api/v1/pipeline/stats without token → 401 JSON (not 404)."""
        data, status = _request(server, "/api/v1/pipeline/stats")
        assert status == 401, f"expected 401, got {status}: {data}"

    def test_pipeline_yuleasr_status_unauth_401(self, server):
        """GET /api/v1/pipeline/yuleasr-status without token → 401 (not 404)."""
        data, status = _request(server, "/api/v1/pipeline/yuleasr-status")
        assert status == 401, f"expected 401, got {status}: {data}"

    def test_pipeline_validate_unauth_401(self, server):
        """GET /api/v1/pipeline/validate without token → 401 (not 404)."""
        data, status = _request(server, "/api/v1/pipeline/validate")
        assert status == 401, f"expected 401, got {status}: {data}"

    def test_pipeline_status_job_unauth_401(self, server):
        """GET /api/v1/pipeline/status/xyz without token → 401 (not 404)."""
        data, status = _request(server, "/api/v1/pipeline/status/xyz")
        assert status == 401, f"expected 401, got {status}: {data}"

    def test_audit_legacy_get_reachable(self, server):
        """GET /api/v1/audit → 401 JSON (modern audit, auth-gated, not 404)."""
        data, status = _request(server, "/api/v1/audit")
        assert status != 404
        assert status == 401

    def test_unknown_still_404(self, server):
        """Safeguard: genuinely unknown resources must stay 404 JSON."""
        data, status = _request(server, "/api/v1/definitely-not-a-legacy-route")
        assert status == 404
        assert data.get("ok") is False


class TestP0A_MiddlewareDualFormatUnit:
    """Unit-level proof: middleware accepts BOTH sub/org and user_id/org_id."""

    @pytest.fixture(autouse=True)
    def _secret(self):
        import yuleosh.api.middleware as mw
        import yuleosh.api.auth as auth_mod
        saved = (mw._JWT_SECRET, auth_mod._JWT_SECRET)
        secret = "dual-format-unit-secret-32chars!!"
        mw._JWT_SECRET = secret
        auth_mod._JWT_SECRET = secret
        yield secret
        mw._JWT_SECRET, auth_mod._JWT_SECRET = saved

    @pytest.fixture(autouse=True)
    def _seed_user(self):
        from datetime import datetime
        from yuleosh.store import Store
        store = Store()
        uid = 42424242  # unique — avoid shared-store collisions
        now = datetime.now().isoformat()
        store.conn.execute(
            "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, 7, "dual@test.com", "admin", now),
        )
        store.conn.commit()
        yield uid
        try:
            store.conn.execute("DELETE FROM users WHERE id=?", (uid,))
            store.conn.execute("DELETE FROM user_sessions WHERE user_id=?", (uid,))
            store.conn.commit()
        except Exception:
            pass

    def _seed_session(self, uid: int, token: str):
        """Create a store session row so the middleware session check passes."""
        from datetime import datetime, timedelta
        from yuleosh.store import Store
        store = Store()
        now = datetime.now().isoformat()
        expires = (datetime.now() + timedelta(hours=72)).isoformat()
        # P1-6: sessions are stored as sha256 hashes — never plaintext.

        from yuleosh.store import _session_token_hash

        store.conn.execute(

            "INSERT OR IGNORE INTO user_sessions "

            "(user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",

            (uid, _session_token_hash(token), now, expires),

        )
        store.conn.commit()

    def _call_authed(self, secret: str, token: str, uid: int):
        from unittest import mock
        from yuleosh.api.middleware import require_auth

        @require_auth
        def _handler(**kwargs):
            cu = kwargs["current_user"]
            return {"ok": True, "user_id": cu["user_id"], "org_id": cu["org_id"]}, 200

        handler = mock.MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        handler.client_address = ("127.0.0.1", 12345)
        handler._request_start_time = 0.0
        self._seed_session(uid, token)
        return _handler(method="GET", path_tail="", body={}, query={}, handler=handler)

    def test_sub_org_format_accepted(self, _secret, _seed_user):
        """Frontend format {sub, org} passes require_auth."""
        import jwt as _jwt
        token = _jwt.encode(
            {"sub": str(_seed_user), "org": 7, "email": "dual@test.com",
             "iat": 0, "exp": 9999999999},
            _secret, algorithm="HS256",
        )
        result, status = self._call_authed(_secret, token, _seed_user)
        assert status == 200
        assert result["user_id"] == _seed_user
        assert result["org_id"] == 7

    def test_user_id_format_still_accepted(self, _secret, _seed_user):
        """Modern format {user_id, org_id} keeps working."""
        import jwt as _jwt
        token = _jwt.encode(
            {"user_id": _seed_user, "org_id": 7, "email": "dual@test.com",
             "iat": 0, "exp": 9999999999},
            _secret, algorithm="HS256",
        )
        result, status = self._call_authed(_secret, token, _seed_user)
        assert status == 200
        assert result["user_id"] == _seed_user
        assert result["org_id"] == 7
