
# @tests src/yuleosh/pipeline/orchestrator.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Regression tests for the v3.5.0 backlog fix round (sprint-backlog-p1-v3.5.0).

Covers every Wave-A P1 item with a focused, isolated test:

  P1-1  audit RBAC (admin/auditor only)
  P1-2  signin fail-closed + enumeration/lockout DoS hardening
  P1-3  _check_auth delegates to real auth (no constant-True)
  P1-4  preview rate limit atomicity + is_authed real validation
  P1-5  read_body Content-Length clamp + malformed-header handling
  P1-6  session tokens stored as sha256 (never plaintext)
  P1-7  error sanitization (kg_impact, server do_POST, osh_home leak)
  P1-8  async_runner fails explicitly (no simulated CI pass)
  P1-9  notify SMTP password write-only
  P1-10 fault_inject subprocess without shell=True
  P1-11 CORS preflight honors the cors.py whitelist

Plus selected Wave B: P2-2 (sandbox path traversal), P2-6 (zip bomb).
"""

import hashlib
import io
import json
import os
import stat
import tempfile
import threading
import time
import zipfile
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# P1-1: audit RBAC
# ---------------------------------------------------------------------------

class TestAuditRBAC:
    """GET /api/v1/audit must require audit:view (admin/auditor)."""

    def _call(self, role, has_user=True):
        from yuleosh.api.audit import handle_audit
        kwargs = {}
        if has_user:
            kwargs["current_user"] = {
                "user_id": 1, "org_id": 1, "email": "u@t.com", "role": role,
            }
        with mock.patch("yuleosh.api.audit.get_store") as m_store:
            store = mock.MagicMock()
            store.conn.execute.return_value.fetchall.return_value = []
            count = mock.MagicMock()
            count.fetchone.return_value = {"c": 0}
            store.conn.execute.side_effect = lambda *a, **k: (
                count if "COUNT" in (a[0] if a else "") else mock.MagicMock()
            )
            m_store.return_value = store
            return handle_audit("GET", "", {}, {}, **kwargs)

    def test_member_denied(self):
        result, status = self._call("member")
        assert status == 403
        assert "permission" in result["error"].lower()

    def test_developer_denied(self):
        result, status = self._call("developer")
        assert status == 403

    def test_admin_allowed(self):
        result, status = self._call("admin")
        assert status == 200

    def test_auditor_allowed(self):
        result, status = self._call("auditor")
        assert status == 200

    def test_missing_current_user_fails_closed(self):
        # require_auth intercepts before the handler body: 401, never data.
        result, status = self._call("admin", has_user=False)
        assert status == 401


# ---------------------------------------------------------------------------
# P1-2: signin fail-closed + lockout DoS
# ---------------------------------------------------------------------------

class TestSigninHardening:
    """No-password users must never authenticate with email alone."""

    def _make_user(self, store, org_id, email, password_hash=None):
        return store.create_user(org_id, email, "member", password_hash)

    def test_passwordless_user_cannot_login(self):
        """GIVEN user with NULL password_hash WHEN signin THEN 401 unified msg."""
        from yuleosh.ui import auth_extended as A
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(os.path.join(tmp, "t.db"))
            org = s.create_organization("Org", "org")
            self._make_user(s, org["id"], "victim@test.com", password_hash=None)
            with mock.patch.object(Store, "get_session", return_value=None):
                with mock.patch.object(A, "Store", return_value=s):
                    result, status = A.handle_signin({"email": "victim@test.com", "password": "Whatever123"})
            assert status == 401
            assert result["error"] == "Invalid email or password"

    def test_unified_message_prevents_enumeration(self):
        """GIVEN passwordless vs wrong-password vs unknown-in-org WHEN signin
        THEN identical 401 message (no per-state hints)."""
        from yuleosh.ui import auth_extended as A
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(os.path.join(tmp, "t.db"))
            org = s.create_organization("Org", "org")
            s.create_user(org["id"], "nopass@test.com", "member", None)
            s.create_user(org["id"], "haspass@test.com", "member", A._hash_password("RealPass123"))
            with mock.patch.object(A, "Store", return_value=s):
                no_pass = A.handle_signin({"email": "nopass@test.com", "password": "Whatever123"})
                wrong = A.handle_signin({"email": "haspass@test.com", "password": "WrongPass123"})
                missing = A.handle_signin({"email": "haspass@test.com", "password": ""})
            assert no_pass[0]["error"] == wrong[0]["error"] == missing[0]["error"] == "Invalid email or password"
            assert no_pass[1] == wrong[1] == missing[1] == 401

    def test_per_ip_cap_bounds_lockout(self):
        """GIVEN attacker IP WHEN exceeding per-IP cap THEN 429."""
        from yuleosh.ui import auth_extended as A
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(os.path.join(tmp, "t.db"))
            with mock.patch.object(A, "Store", return_value=s):
                messages = []
                for _ in range(A._MAX_SIGNIN_IP_ATTEMPTS):
                    res, _st = A.handle_signin(
                        {"email": "victim@test.com", "password": "x" * 12}, ip="203.0.113.77")
                    messages.append(res.get("error", ""))
                blocked_res, blocked = A.handle_signin(
                    {"email": "victim@test.com", "password": "x" * 12}, ip="203.0.113.77")
            assert blocked == 429
            assert "Too many attempts" in blocked_res["error"]

    def test_failed_attempts_lock_email_after_10(self):
        """GIVEN 10 failed attempts WHEN 11th signin THEN 429."""
        from yuleosh.ui import auth_extended as A
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            s = Store(os.path.join(tmp, "t.db"))
            org = s.create_organization("Org", "org")
            s.create_user(org["id"], "lock@test.com", "member", A._hash_password("RealPass123"))
            with mock.patch.object(A, "Store", return_value=s):
                for _ in range(A._MAX_SIGNIN_ATTEMPTS):
                    A.handle_signin({"email": "lock@test.com", "password": "WrongPass123"})
                _, st = A.handle_signin({"email": "lock@test.com", "password": "WrongPass123"})
            assert st == 429


# ---------------------------------------------------------------------------
# P1-3: _check_auth real delegation
# ---------------------------------------------------------------------------

class TestCheckAuthDelegation:
    def test_enabled_no_key_denied(self):
        from yuleosh.ui.server import OSHHandler, AUTH_ENABLED
        with mock.patch("yuleosh.ui.server.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "secret"):
            h = object.__new__(OSHHandler)
            h.path = "/api/evidence"  # gated path (SEC-C3 whitelist)
            h.headers = {}
            assert h._check_auth() is False

    def test_enabled_valid_key_allowed(self):
        from yuleosh.ui.server import OSHHandler
        with mock.patch("yuleosh.ui.server.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True), \
             mock.patch("yuleosh.ui.auth.API_KEY", "secret"):
            h = object.__new__(OSHHandler)
            h.path = "/api/evidence"  # gated path (SEC-C3 whitelist)
            h.headers = {"x-api-key": "secret"}
            assert h._check_auth() is True


# ---------------------------------------------------------------------------
# P1-4: preview rate limit atomicity + is_authed
# ---------------------------------------------------------------------------

class TestPreviewRateLimit:
    def test_concurrent_hits_not_lost(self):
        """GIVEN 20 threads WHEN rate-limit check THEN all hits recorded."""
        from yuleosh.api import preview as P
        P._preview_request_log.clear()
        barrier = threading.Barrier(20)
        def worker():
            barrier.wait()
            P._check_preview_rate_limit("10.0.0.1", is_authenticated=True)
        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with P._preview_request_log._lock:
            count = len(P._preview_request_log._dict["10.0.0.1"])
        assert count == 20  # no lost updates under concurrency
        P._preview_request_log.clear()

    def test_fake_bearer_not_authed(self):
        """GIVEN fake Authorization header WHEN is_authed THEN False."""
        from yuleosh.api import preview as P
        handler = mock.MagicMock()
        handler.headers.get.return_value = "Bearer not.a.real.token"
        assert P._is_authed(handler) is False

    def test_empty_headers_not_authed(self):
        from yuleosh.api import preview as P
        handler = mock.MagicMock()
        handler.headers.get.return_value = ""
        assert P._is_authed(handler) is False


# ---------------------------------------------------------------------------
# P1-5: read_body clamp
# ---------------------------------------------------------------------------

class TestReadBodyClamp:
    def _handler(self, content_length, raw=b"{}"):
        h = mock.MagicMock()
        h.headers.get.return_value = str(content_length)
        h.rfile.read.return_value = raw
        return h

    def test_malformed_content_length_raises_badrequest(self):
        from yuleosh.api import read_body, BadRequest
        with pytest.raises(BadRequest, match="Content-Length"):
            read_body(self._handler("abc"))

    def test_negative_content_length_raises_badrequest(self):
        from yuleosh.api import read_body, BadRequest
        with pytest.raises(BadRequest, match="Content-Length"):
            read_body(self._handler(-5))

    def test_huge_content_length_clamped(self):
        """GIVEN 20MB claim WHEN read THEN at most MAX_BODY_BYTES read."""
        from yuleosh.api import read_body, MAX_BODY_BYTES, BadRequest
        h = mock.MagicMock()
        h.headers.get.return_value = str(20 * 1024 * 1024)
        h.rfile.read.return_value = b"{}"
        # Clamp means we never raise on size; parse succeeds on small body.
        with mock.patch("yuleosh.api.MAX_BODY_BYTES", 10):
            # force tiny clamp so the truncation path is exercised
            result = read_body(h)
        assert result == {}
        # The raw body read is bounded by the clamp (10 bytes here)
        assert h.rfile.read.call_args[0][0] <= 10 * 1024 * 1024

    def test_router_returns_400_on_bad_length(self):
        """GIVEN router dispatch with malformed Content-Length THEN 400 JSON."""
        from yuleosh.api.router import dispatch
        h = mock.MagicMock()
        h.command = "GET"
        h.path = "/api/v1/health"
        h.headers.get.return_value = "not-a-number"
        dispatch(h, "/api/v1/health")
        # _respond was called with a 400 tuple
        assert h.send_response.call_args[0][0] == 400


# ---------------------------------------------------------------------------
# P1-6: session hash storage
# ---------------------------------------------------------------------------

class TestSessionHashStorage:
    def test_db_never_stores_plaintext_token(self):
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "s.db")
            s = Store(db)
            org = s.create_organization("Org", "org")
            user = s.create_user(org["id"], "u@t.com")
            s.create_session(user["id"], "super-secret-jwt-token", 24)
            rows = s.conn.execute("SELECT token FROM user_sessions").fetchall()
            assert len(rows) == 1
            assert rows[0]["token"] != "super-secret-jwt-token"
            assert rows[0]["token"] == hashlib.sha256(b"super-secret-jwt-token").hexdigest()
            # plaintext must not appear anywhere in the table
            assert all("super-secret-jwt-token" not in r["token"] for r in rows)

    def test_legacy_plaintext_rows_migrated_on_open(self):
        from yuleosh.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "m.db")
            s = Store(db)
            org = s.create_organization("Org", "org")
            user = s.create_user(org["id"], "u@t.com")
            # Simulate a legacy plaintext row
            s.conn.execute(
                "INSERT INTO user_sessions (user_id, token, created_at, expires_at) "
                "VALUES (?, ?, datetime('now'), datetime('now', '+1 day'))",
                (user["id"], "legacy-plaintext-token"),
            )
            s.conn.commit()
            # Reopen → migration hashes the legacy row (fresh instance)
            Store._instances.pop(db, None)
            s2 = Store(db)
            rows = s2.conn.execute("SELECT token FROM user_sessions").fetchall()
            assert all(len(r["token"]) == 64 for r in rows)
            assert s2.get_session("legacy-plaintext-token") is not None


# ---------------------------------------------------------------------------
# P1-7: error sanitization
# ---------------------------------------------------------------------------

class _RecordingHandler:
    def __init__(self):
        self.sent = []
        self.wfile = io.BytesIO()
        self.headers = {}

    def send_response(self, status):
        self.status = status

    def send_header(self, k, v):
        self.sent.append((k, v))

    def end_headers(self):
        pass


class TestErrorSanitization:
    def test_kg_impact_hides_exception_detail(self):
        from yuleosh.api import kg_impact
        handler = _RecordingHandler()
        with mock.patch.object(kg_impact, "impact_analysis",
                               side_effect=RuntimeError("SECRET-DB-DETAIL-xyz")):
            with mock.patch.object(kg_impact, "get_store", return_value=object()):
                kg_impact.handle_kg_impact(handler, {"changed_files": ["a.c"]})
        body = handler.wfile.getvalue().decode()
        assert handler.status == 500
        assert "SECRET-DB-DETAIL-xyz" not in body
        assert "Internal server error" in body

    def test_server_do_post_hides_exception_detail(self):
        from yuleosh.ui.server import OSHHandler
        h = object.__new__(OSHHandler)
        h.path = "/api/x"
        h.command = "POST"
        h.client_address = ("127.0.0.1", 0)
        h.wfile = io.BytesIO()
        h.sent = []
        h._json_response = lambda data, status=200: (
            h.sent.append((data, status)),
            h.wfile.write(json.dumps(data).encode()),
        )
        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_post",
                        side_effect=RuntimeError("LEAKED-INTERNAL-MARKER")):
            h.do_POST()
        body = h.wfile.getvalue().decode()
        assert "LEAKED-INTERNAL-MARKER" not in body
        assert "Internal server error" in body

    def test_status_and_health_do_not_leak_osh_home(self):
        from yuleosh.ui.routes.api_routes import handle_status, handle_health
        status = handle_status(_RecordingHandler())
        health = handle_health(_RecordingHandler())
        assert "osh_home" not in status
        assert "osh_home" not in health
        assert "osh_home_configured" in status
        assert "osh_home_configured" in health


# ---------------------------------------------------------------------------
# P1-8: async_runner explicit failure
# ---------------------------------------------------------------------------

class TestAsyncRunnerNoFakePass:
    def _job(self, job_id):
        return {
            "status": "queued", "project_dir": "/tmp/x", "layer": 1,
            "started_at": None, "completed_at": None, "result": None,
        }

    def test_signal_error_marks_job_failed(self):
        """GIVEN signal-in-thread ValueError WHEN CI job THEN failed (not simulated)."""
        import yuleosh.pipeline.async_runner as ar
        with mock.patch("yuleosh.ci.run_layer1",
                        side_effect=ValueError("signal only works in main thread")):
            ar._PIPELINE_JOBS["sig_job"] = self._job("sig_job")
            ar._run_ci_job("sig_job", "/tmp/x", 1)
        assert ar._PIPELINE_JOBS["sig_job"]["status"] == "failed"
        assert "simulated" not in str(ar._PIPELINE_JOBS["sig_job"]["result"]).lower()
        del ar._PIPELINE_JOBS["sig_job"]

    def test_import_error_marks_job_failed(self):
        """GIVEN ImportError in worker WHEN CI job THEN failed (not simulated)."""
        import yuleosh.pipeline.async_runner as ar
        with mock.patch("yuleosh.ci.run_layer1", side_effect=ImportError("no module")):
            ar._PIPELINE_JOBS["imp_job"] = self._job("imp_job")
            ar._run_ci_job("imp_job", "/tmp/x", 1)
        assert ar._PIPELINE_JOBS["imp_job"]["status"] == "failed"
        del ar._PIPELINE_JOBS["imp_job"]


# ---------------------------------------------------------------------------
# P1-9: notify SMTP password write-only
# ---------------------------------------------------------------------------

class TestNotifyPasswordWriteOnly:
    def test_get_config_never_returns_password(self):
        from yuleosh.api.notify import _get_config
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_EMAIL_PASS": "smtp-secret-99"}, clear=False):
            result, status = _get_config()
        assert status == 200
        payload = result["data"]
        assert "email_pass" not in payload
        assert payload["email_pass_set"] is True

    def test_empty_password_does_not_clear_existing(self):
        from yuleosh.api.notify import _put_config
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_EMAIL_PASS": "existing-pass"}, clear=False):
            result, status = _put_config({"email_pass": ""})
            assert status == 200
            assert os.environ["YULEOSH_NOTIFY_EMAIL_PASS"] == "existing-pass"

    def test_new_password_accepted(self):
        from yuleosh.api.notify import _put_config
        with mock.patch.dict(os.environ, {"YULEOSH_NOTIFY_EMAIL_PASS": "old-pass"}, clear=False):
            result, status = _put_config({"email_pass": "new-pass-42"})
            assert status == 200
            assert os.environ["YULEOSH_NOTIFY_EMAIL_PASS"] == "new-pass-42"
            assert result["data"]["email_pass_set"] is True


# ---------------------------------------------------------------------------
# P1-10: fault_inject without shell=True
# ---------------------------------------------------------------------------

class TestFaultInjectNoShell:
    def test_cmake_build_uses_argv_and_no_shell(self, tmp_path):
        from yuleosh.pipeline.step_handlers.fault_inject import FaultInjectStage
        # Fixture needs a real project root with CMakeLists.txt so the build
        # path is exercised (otherwise fault_inject skips to SIMULATED mode
        # and never reaches the cmake argv calls this test verifies).
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.16)\nproject(fi_test C)\n",
            encoding="utf-8",
        )
        stage = FaultInjectStage(build_dir="/tmp/fi-build")
        with mock.patch("yuleosh.pipeline.step_handlers.fault_inject.subprocess.run") as m_run:
            ok = stage.build_test_firmware(project_root=str(proj))
        assert ok is True
        calls = [c for c in m_run.call_args_list]
        assert len(calls) == 2
        args, kwargs = calls[1]
        assert args[0][0] == "cmake"
        assert args[0][1] == "--build"
        assert args[0][-2:] == ["-j", str(os.cpu_count() or 1)]
        assert kwargs.get("shell") is not True
        assert "shell" not in kwargs


# ---------------------------------------------------------------------------
# P1-11: CORS preflight whitelist
# ---------------------------------------------------------------------------

class TestCorsPreflight:
    def _options(self, origin):
        from yuleosh.ui.routes.handler_helpers import handle_options
        h = _RecordingHandler()
        h.headers = {"Origin": origin} if origin else {}
        handle_options(h)
        return dict(h.sent)

    def test_allowed_origin_echoed(self):
        with mock.patch("yuleosh.api.cors.is_development", return_value=False), \
             mock.patch("yuleosh.api.cors.get_allowed_origins",
                        return_value={"http://localhost:18789"}):
            headers = self._options("http://localhost:18789")
        assert headers["Access-Control-Allow-Origin"] == "http://localhost:18789"

    def test_evil_origin_not_echoed(self):
        with mock.patch("yuleosh.api.cors.is_development", return_value=False), \
             mock.patch("yuleosh.api.cors.get_allowed_origins",
                        return_value={"http://localhost:18789"}):
            headers = self._options("https://evil.example.com")
        assert headers["Access-Control-Allow-Origin"] != "*"
        assert headers["Access-Control-Allow-Origin"] != "https://evil.example.com"


# ---------------------------------------------------------------------------
# P2-6: zip bomb protection
# ---------------------------------------------------------------------------

class TestZipBomb:
    def _zip(self, names, symlink=False, content=b"hello-data"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for n in names:
                if symlink:
                    info = zipfile.ZipInfo(n)
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    zf.writestr(info, b"/etc/passwd")
                else:
                    zf.writestr(n, content)
        return buf.getvalue()

    def test_too_many_members_rejected(self):
        from yuleosh.api import preview as P
        data = self._zip([f"f{i}.c" for i in range(5)])
        with mock.patch.object(P, "MAX_ZIP_MEMBERS", 3):
            result, status = P._handle_zip_upload("p1", data, None)
        assert status == 413
        assert result["error"] == "archive_too_large"

    def test_member_size_cap_rejected(self):
        from yuleosh.api import preview as P
        data = self._zip(["big.c"], content=b"x" * 100)
        with mock.patch.object(P, "MAX_ZIP_MEMBER_BYTES", 10):
            result, status = P._handle_zip_upload("p1", data, None)
        assert status == 413
        assert result["error"] == "archive_too_large"

    def test_expanded_total_cap_rejected(self):
        from yuleosh.api import preview as P
        data = self._zip(["a.c", "b.c"], content=b"hello")  # 5 bytes each
        with mock.patch.object(P, "MAX_ZIP_EXPANDED_BYTES", 9):
            result, status = P._handle_zip_upload("p1", data, None)
        assert status == 413

    def test_symlink_member_rejected(self):
        from yuleosh.api import preview as P
        data = self._zip(["link.txt"], symlink=True)
        result, status = P._handle_zip_upload("p1", data, None)
        assert status == 400
        assert result["error"] == "invalid_archive"

    def test_absolute_path_member_rejected(self):
        from yuleosh.api import preview as P
        data = self._zip(["/etc/passwd"])
        result, status = P._handle_zip_upload("p1", data, None)
        assert status == 400
        assert result["error"] == "invalid_archive"

    def test_normal_zip_still_accepted(self, tmp_path, monkeypatch):
        from yuleosh.api import preview as P
        data = self._zip(["main.c"])
        monkeypatch.setattr("tempfile.mkdtemp", lambda prefix="": str(tmp_path / "t"))
        with mock.patch.object(P, "_analyze_in_background"):
            result, status = P._handle_zip_upload("p-ok", data, None)
        assert status == 202
        assert (tmp_path / "t" / "main.c").exists()


# ---------------------------------------------------------------------------
# P2-2: sandbox path traversal (prefix bypass)
# ---------------------------------------------------------------------------

class TestSandboxPathGuard:
    def _sandbox_open(self, tmp_path):
        from yuleosh.plugins.sandbox import PluginSandbox
        from yuleosh.plugins import Plugin, PluginManifest
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest = PluginManifest(
            name="t", version="1.0.0", type="tool",
            description="t", author="t", entry="main.py",
        )
        plugin = Plugin(manifest, plugin_dir)
        sandbox = PluginSandbox(plugin_dir, manifest)
        return sandbox._restricted_open(plugin), plugin_dir

    def test_prefix_sibling_directory_rejected(self, tmp_path):
        """P2-2: /allowed_dir_evil must NOT pass a startswith-prefix check."""
        from yuleosh.plugins.sandbox import SandboxViolation
        safe_open, plugin_dir = self._sandbox_open(tmp_path)
        sibling = tmp_path / "plugin_evil"  # same prefix, different dir
        sibling.mkdir()
        target = sibling / "pwn.txt"
        target.write_text("x")
        with pytest.raises(SandboxViolation):
            safe_open(str(target), "r")

    def test_parent_traversal_rejected(self, tmp_path):
        from yuleosh.plugins.sandbox import SandboxViolation
        safe_open, plugin_dir = self._sandbox_open(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("x")
        with pytest.raises(SandboxViolation):
            safe_open(str(outside), "w")

    def test_inside_plugin_dir_allowed(self, tmp_path):
        safe_open, plugin_dir = self._sandbox_open(tmp_path)
        inside = plugin_dir / "data.txt"
        with mock.patch("yuleosh.plugins.sandbox.builtins.open") as m_open:
            safe_open(str(inside), "r")
        m_open.assert_called_once_with(str(inside), "r")


# ---------------------------------------------------------------------------
# Wave D: json_error dict normalization
# ---------------------------------------------------------------------------

class TestJsonErrorContract:
    def test_dict_error_normalized(self):
        from yuleosh.api import json_error
        result, status = json_error({"error": "file_too_large", "max_size_mb": 50}, 413)
        assert status == 413
        assert result["ok"] is False
        assert result["error"] == "file_too_large"
        assert result["details"] == {"max_size_mb": 50}

    def test_str_error_unchanged(self):
        from yuleosh.api import json_error
        result, status = json_error("boom", 400)
        assert result == {"ok": False, "error": "boom"}
