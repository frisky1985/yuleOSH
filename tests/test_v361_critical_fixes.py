# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""v3.6.1 ultra-review Critical×3 regression tests.

Fix 1 (SEC-C2): error responses never echo internal exception details —
  7 API sites (ci/review/pipeline/apikeys/subscription) return a generic
  "Internal server error" (details only in server logs).
Fix 2 (SEC-C1): evidence/dashboard project_dir must resolve inside
  OSH_HOME — ../ traversal and absolute escapes return 403.
Fix 3 (SEC-C3): legacy auth is fail-closed by default — with no API key
  configured, non-public legacy endpoints return 401; a whitelist
  (health/status/login/tenant onboarding/pages/static) stays public;
  YULEOSH_AUTH_DISABLED=1 opts out; valid tenant JWTs authenticate.
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
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ======================================================================
# Fix 1 — error masking (SEC-C2)
# ======================================================================

class TestErrorMasking:
    """Exception details never leak into JSON error bodies."""

    def _assert_masked(self, result, status, secret):
        assert result[1] == status
        err = result[0]["error"]
        assert err == "Internal server error"
        assert secret not in json.dumps(result[0])

    def test_internal_error_helper(self):
        from yuleosh.api._errors import internal_error
        secret = "/secret/server/path/data.db"
        result = internal_error("test", RuntimeError(f"sql boom: {secret}"))
        self._assert_masked(result, 500, secret)

    def test_internal_error_logs_exc_info(self, caplog):
        from yuleosh.api._errors import internal_error
        secret = "traceback-secret-xyz"
        with caplog.at_level("ERROR", logger="api.testmodule"):
            internal_error("testmodule", ValueError(secret))
        assert any(secret in r.message for r in caplog.records)
        assert any(r.exc_info for r in caplog.records)

    def test_ci_masks_details(self, monkeypatch):
        from yuleosh.api.ci import _run_ci_layer
        secret = "/home/user/.yuleosh/ci/private.log"
        monkeypatch.setattr(
            "yuleosh.api.ci.subprocess.run",
            mock.Mock(side_effect=RuntimeError(secret)),
        )
        result = _run_ci_layer("1")
        self._assert_masked(result, 500, secret)

    def test_review_auto_masks_details(self, monkeypatch):
        from yuleosh.api.review import _run_auto_review
        secret = "/srv/review/cache/secret"
        monkeypatch.setattr(
            "yuleosh.api.review.subprocess.run",
            mock.Mock(side_effect=RuntimeError(secret)),
        )
        result = _run_auto_review({})
        self._assert_masked(result, 500, secret)

    def test_review_task_masks_details(self, monkeypatch):
        from yuleosh.api.review import _run_task_review
        secret = "task-queue-deadlock"
        monkeypatch.setattr(
            "yuleosh.api.review.subprocess.run",
            mock.Mock(side_effect=RuntimeError(secret)),
        )
        result = _run_task_review({"task": "t1", "kind": "feature"})
        self._assert_masked(result, 500, secret)

    def test_pipeline_run_masks_details(self, monkeypatch, tmp_path):
        from yuleosh.api.pipeline import _run_pipeline
        secret = "/etc/passwd-leak"
        spec = tmp_path / "spec.md"
        spec.write_text("# spec")
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        monkeypatch.setattr(
            "yuleosh.api.pipeline.subprocess.run",
            mock.Mock(side_effect=RuntimeError(secret)),
        )
        result = _run_pipeline({"spec": "spec.md"})
        self._assert_masked(result, 500, secret)

    def test_pipeline_trigger_masks_details(self, monkeypatch, tmp_path):
        from yuleosh.api.pipeline import _trigger_pipeline
        secret = "async-pool-boom"
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        monkeypatch.setattr(
            "yuleosh.api.pipeline._check_trigger_throttle", lambda: True)
        monkeypatch.setattr(
            "yuleosh.pipeline.async_runner.submit_full_pipeline",
            mock.Mock(side_effect=RuntimeError(secret)),
        )
        result = _trigger_pipeline({
            "project_dir": str(tmp_path),
            "type": "full",
        })
        self._assert_masked(result, 500, secret)

    def test_apikeys_masks_details(self, monkeypatch):
        from yuleosh.api.apikeys import _generate_key
        secret = "sqlite-disk-full"
        fake_store = mock.Mock()
        fake_store.create_api_key.side_effect = RuntimeError(secret)
        monkeypatch.setattr("yuleosh.api.apikeys.Store", lambda: fake_store)
        result = _generate_key({"label": "My Key"})
        self._assert_masked(result, 500, secret)

    def test_subscription_cancel_masks_details(self, monkeypatch, tmp_path):
        from yuleosh.api.subscription import _handle_sub_cancel
        secret = "stripe-rate-limit-429"
        monkeypatch.setattr(
            "yuleosh.api.subscription._get_authenticated_org",
            lambda headers: (1, 1, "t@t.com"),
        )
        fake_store = mock.Mock()
        fake_store.get_subscription.return_value = {
            "stripe_subscription_id": "sub_123",
            "current_period_end": "2026-09-01",
        }
        monkeypatch.setattr("yuleosh.api.subscription.Store", lambda: fake_store)
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_xyz")

        stripe_mod = mock.Mock()
        stripe_mod.Subscription.modify.side_effect = RuntimeError(secret)
        monkeypatch.setitem(sys.modules, "stripe", stripe_mod)

        result = _handle_sub_cancel({}, handler=mock.Mock())
        self._assert_masked(result, 500, secret)

    def test_evidence_masks_details(self, monkeypatch, tmp_path):
        from yuleosh.api.evidence import _generate_evidence
        secret = "/data/evidence/secret-path"
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        monkeypatch.setattr(
            "yuleosh.api.evidence.subprocess.run",
            mock.Mock(side_effect=OSError(secret)),
        )
        result = _generate_evidence({"project_dir": str(tmp_path)})
        self._assert_masked(result, 500, secret)


# ======================================================================
# Fix 2 — project_dir path guard (SEC-C1)
# ======================================================================

class TestProjectDirGuard:
    def test_evidence_rejects_absolute_escape(self, monkeypatch, tmp_path):
        from yuleosh.api.evidence import _generate_evidence
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        for bad in ("/etc", "/tmp", str(Path.home())):
            result = _generate_evidence({"project_dir": bad})
            assert result[1] == 403, bad
            assert "inside OSH_HOME" in result[0]["error"]

    def test_evidence_rejects_traversal(self, monkeypatch, tmp_path):
        from yuleosh.api.evidence import _generate_evidence
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        bad = str(tmp_path / "a" / ".." / ".." / ".." / ".." / "etc")
        result = _generate_evidence({"project_dir": bad})
        assert result[1] == 403
        assert "inside OSH_HOME" in result[0]["error"]

    def test_evidence_accepts_inside(self, monkeypatch, tmp_path):
        from yuleosh.api.evidence import _generate_evidence
        monkeypatch.setattr("yuleosh.api.OSH_HOME", str(tmp_path))
        monkeypatch.setattr(
            "yuleosh.api.evidence.subprocess.run",
            mock.Mock(return_value=mock.Mock(
                returncode=0, stdout="ok", stderr="")),
        )
        result = _generate_evidence({"project_dir": str(tmp_path / "sub")})
        assert result[1] == 200
        assert result[0]["data"]["status"] == "completed"

    def test_dashboard_rejects_escape(self, tmp_path):
        from yuleosh.api import dashboard as D
        _handle = D.handle_dashboard.__wrapped__
        with mock.patch.object(D, "OSH_HOME", str(tmp_path)):
            D._ev_tasks.clear()
            payload, status = _handle(
                "POST", "evidence/generate",
                {"project_dir": "/etc"}, {}, handler=None)
            assert status == 403
            assert "inside OSH_HOME" in payload["error"]
            assert D._ev_tasks == {}


# ======================================================================
# Fix 3 — legacy auth fail-closed (SEC-C3)
# ======================================================================

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _spawn_server(env_extra: dict | None = None):
    """Start a real server subprocess. YULEOSH_JWT_SECRET is always set;
    YULEOSH_API_KEY is NOT set unless explicitly provided."""
    port = _free_port()
    env = dict(os.environ)
    env["YULEOSH_JWT_SECRET"] = "v361-critical-fixes-secret-32chars!!"
    env["OSH_HOME"] = str(REPO_ROOT / "data" / "v344-p0ab-osh")
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
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
             token: str | None = None, headers: dict | None = None):
    """Real HTTP request helper. Returns (payload_dict, status)."""
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
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


class TestLegacyAuthFailClosed:
    """Default deployment (no YULEOSH_API_KEY): legacy data endpoints 401."""

    @pytest.fixture(scope="class")
    def server(self):
        proc, port = _spawn_server()
        yield port
        proc.kill()
        proc.wait(timeout=5)

    def test_health_public(self, server):
        data, status = _request(server, "/api/health")
        assert status == 200
        assert data.get("status") == "ok"

    def test_status_public(self, server):
        data, status = _request(server, "/api/status")
        assert status == 200

    def test_evidence_denied_by_default(self, server):
        data, status = _request(server, "/api/evidence")
        assert status == 401
        assert data.get("ok") is False

    def test_reviews_denied_by_default(self, server):
        data, status = _request(server, "/api/reviews")
        assert status == 401

    def test_ci_denied_by_default(self, server):
        data, status = _request(server, "/api/ci")
        assert status == 401

    def test_loops_denied_by_default(self, server):
        data, status = _request(server, "/api/loops/1/data")
        assert status == 401

    def test_dashboard_page_public_shell(self, server):
        """Frontend pages are static shells — reachable without cookies
        (the tenant flow keeps its token in localStorage)."""
        data, status = _request(server, "/dashboard")
        assert status == 200
        assert "html" in str(data).lower() or isinstance(data, dict)

    def test_login_page_public(self, server):
        data, status = _request(server, "/login")
        assert status == 200


class TestLegacyAuthDisabledEnv:
    """YULEOSH_AUTH_DISABLED=1 opts out of fail-closed auth (dev mode)."""

    @pytest.fixture(scope="class")
    def server(self):
        proc, port = _spawn_server(env_extra={"YULEOSH_AUTH_DISABLED": "1"})
        yield port
        proc.kill()
        proc.wait(timeout=5)

    def test_evidence_allowed_when_disabled(self, server):
        data, status = _request(server, "/api/evidence")
        assert status == 200


class TestLegacyAuthTenantJwt:
    """A valid tenant JWT (real frontend login chain) authenticates legacy
    endpoints — the dashboard page's data calls keep working."""

    @pytest.fixture(scope="class")
    def server(self):
        proc, port = _spawn_server()
        yield port
        proc.kill()
        proc.wait(timeout=5)

    def _full_login_chain(self, port: int, email: str) -> str:
        data, status = _request(port, "/api/auth/signin", "POST", {"email": email})
        assert status == 200
        assert data.get("needs_org") is True
        setup_token = data["token"]
        data, status = _request(port, "/api/org/create", "POST", {
            "org_name": "V361 Org",
            "org_slug": f"v361-{abs(hash(email)) % 100000}",
            "project_name": "V361 Project",
            "project_slug": "v361-project",
            "email": email,
            "password": "StrongPass123",
        }, token=setup_token)
        assert status == 200, f"org/create failed: {data}"
        return data["token"]

    def test_legacy_loops_with_tenant_jwt(self, server):
        email = f"v361-jwt-{int(time.time())}@test.com"
        token = self._full_login_chain(server, email)
        data, status = _request(server, "/api/loops/1/data", token=token)
        assert status == 200, f"expected 200 with JWT, got {status}: {data}"

    def test_legacy_evidence_with_tenant_jwt(self, server):
        email = f"v361-jwt2-{int(time.time())}@test.com"
        token = self._full_login_chain(server, email)
        data, status = _request(server, "/api/evidence", token=token)
        assert status == 200, f"expected 200 with JWT, got {status}: {data}"

    def test_protected_v1_still_works(self, server):
        email = f"v361-jwt3-{int(time.time())}@test.com"
        token = self._full_login_chain(server, email)
        data, status = _request(server, "/api/v1/dashboard/projects", token=token)
        assert status == 200
        assert data.get("ok") is True


# ======================================================================
# Unit-level auth module checks
# ======================================================================

class TestAuthUnit:
    def test_auth_enabled_fail_closed_without_key(self):
        """SEC-C3: AUTH_ENABLED is True even when no API key is set
        (deterministic check in a fresh interpreter — module import
        order in the pytest session must not affect this)."""
        env = dict(os.environ)
        env.pop("YULEOSH_AUTH_DISABLED", None)
        env.pop("YULEOSH_API_KEY", None)
        env["YULEOSH_JWT_SECRET"] = "x" * 20
        out = subprocess.run(
            [sys.executable, "-c",
             "from yuleosh.ui.auth import AUTH_ENABLED; print(AUTH_ENABLED)"],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
            timeout=30)
        assert out.stdout.strip() == "True", out.stderr

    def test_is_authenticated_rejects_empty(self):
        from yuleosh.ui.auth import is_authenticated
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True):
            assert is_authenticated({}) is False

    def test_is_authenticated_accepts_api_key(self):
        from yuleosh.ui.auth import is_authenticated
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "secret-key"):
            assert is_authenticated({"x-api-key": "secret-key"}) is True

    def test_is_authenticated_accepts_tenant_jwt(self):
        from yuleosh.ui.auth import is_authenticated
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth_extended.get_session_user",
                        return_value={"user_id": 1}):
            assert is_authenticated(
                {"authorization": "Bearer fake-jwt"}) is True

    def test_is_authenticated_rejects_bad_jwt(self):
        from yuleosh.ui.auth import is_authenticated
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth_extended.get_session_user",
                        return_value=None):
            assert is_authenticated(
                {"authorization": "Bearer forged"}) is False

    def test_is_authenticated_auth_disabled_env(self):
        from yuleosh.ui.auth import is_authenticated
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", False):
            assert is_authenticated({}) is True
