
# @tests src/yuleosh/api/pipeline.py
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Supplementary deep tests for auth, middleware, and remaining API modules.

Targets uncovered lines in middleware, auth, wizard, ci, and webhooks.
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src
os.environ.setdefault("OSH_HOME", str(Path(__file__).resolve().parent.parent))

# Test JWT secret used to sign tokens in these tests. NOTE: this must NOT be
# written into os.environ at module level — doing so mutates the global
# environment for every later test file (collection order dependent) and made
# auth tests flaky in the single-process suite. The middleware/auth module
# globals are patched per-test in setup_method() instead.
_JWT_SECRET = "test-middleware-secret-32-chars-minimum!!!"


# ======================================================================
# middleware.py — require_auth decorator
# ======================================================================

class TestMiddlewareDeep:
    """require_auth decorator — full coverage."""

    def setup_method(self):
        # Patch the _JWT_SECRET globals directly instead of deleting the
        # modules from sys.modules. Deleting + re-importing replaces the
        # module objects that other test files bound at collection time,
        # leaving the parent package attribute stale and making later
        # require_auth calls validate with a mismatched secret (401).
        import yuleosh.api.auth as _auth_mod
        import yuleosh.api.middleware as _mw_mod
        import yuleosh.ui.auth_extended as _ae_mod
        self._saved_auth_secret = _auth_mod._JWT_SECRET
        self._saved_mw_secret = _mw_mod._JWT_SECRET
        self._saved_ae_secret = _ae_mod.JWT_SECRET
        _auth_mod._JWT_SECRET = _JWT_SECRET
        _mw_mod._JWT_SECRET = _JWT_SECRET
        # A1 (v3.8.0): the unified decoder lives in ui/auth_extended — patch
        # the unified secret too, or signed tokens fail verification.
        _ae_mod.JWT_SECRET = _JWT_SECRET

    def teardown_method(self):
        import yuleosh.api.auth as _auth_mod
        import yuleosh.api.middleware as _mw_mod
        import yuleosh.ui.auth_extended as _ae_mod
        _auth_mod._JWT_SECRET = self._saved_auth_secret
        _mw_mod._JWT_SECRET = self._saved_mw_secret
        _ae_mod.JWT_SECRET = self._saved_ae_secret

    @patch("yuleosh.ui.auth_extended.Store")
    def test_require_auth_success(self, mock_store_class):
        from yuleosh.api.middleware import require_auth

        store = MagicMock()
        store.get_user_by_id.return_value = {"id": 1, "role": "admin"}
        store.get_session.return_value = {"token": "valid", "expires_at": "future"}
        mock_store_class.return_value = store

        import jwt
        token = jwt.encode({
            "user_id": 1, "org_id": 1, "email": "admin@test.com",
            "exp": int(time.time()) + 3600,
        }, _JWT_SECRET, algorithm="HS256")

        @require_auth
        def my_handler(method, path_tail, body, query, **kwargs):
            assert "current_user" in kwargs
            cu = kwargs["current_user"]
            assert cu["user_id"] == 1
            assert cu["email"] == "admin@test.com"
            assert cu["role"] == "admin"
            return {"ok": True, "data": "protected"}, 200

        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}

        result, status = my_handler(
            method="GET", path_tail="", body={}, query={}, handler=handler
        )
        assert status == 200
        assert result["data"] == "protected"

    def test_require_auth_no_handler(self):
        from yuleosh.api.middleware import require_auth

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        result, status = my_handler(
            method="GET", path_tail="", body={}, query={}
        )
        # P0 fix: no HTTP handler → fail closed with 401 (no dummy user)
        assert result["ok"] is False
        assert status == 401

    def test_require_auth_no_token(self):
        from yuleosh.api.middleware import require_auth

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        handler = MagicMock()
        handler.headers = {}
        result, status = my_handler(method="GET", path_tail="", body={}, query={}, handler=handler)
        assert result["ok"] is False
        assert status == 401

    def test_require_auth_bad_token(self):
        from yuleosh.api.middleware import require_auth

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer bad-token"}
        result, status = my_handler(method="GET", path_tail="", body={}, query={}, handler=handler)
        assert result["ok"] is False
        assert status == 401

    @patch("yuleosh.ui.auth_extended.Store")
    def test_require_auth_user_not_found(self, mock_store_class):
        from yuleosh.api.middleware import require_auth

        store = MagicMock()
        store.get_user_by_id.return_value = None
        mock_store_class.return_value = store

        import jwt
        token = jwt.encode({
            "user_id": 999, "org_id": 1, "email": "ghost@test.com",
            "exp": int(time.time()) + 3600,
        }, _JWT_SECRET, algorithm="HS256")

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        result, status = my_handler(method="GET", path_tail="", body={}, query={}, handler=handler)
        assert result["ok"] is False
        assert status == 401

    @patch("yuleosh.ui.auth_extended.Store")
    def test_require_auth_session_not_found(self, mock_store_class):
        from yuleosh.api.middleware import require_auth

        store = MagicMock()
        store.get_user_by_id.return_value = {"id": 1, "role": "member"}
        store.get_session.return_value = None
        mock_store_class.return_value = store

        import jwt
        token = jwt.encode({
            "user_id": 1, "org_id": 1, "email": "test@test.com",
            "exp": int(time.time()) + 3600,
        }, _JWT_SECRET, algorithm="HS256")

        @require_auth
        def my_handler(**kwargs):
            return {"ok": True}, 200

        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        result, status = my_handler(method="GET", path_tail="", body={}, query={}, handler=handler)
        assert result["ok"] is False
        assert status == 401

    def test_decode_token_expired(self):
        from yuleosh.api.middleware import _decode_token
        import jwt
        token = jwt.encode({
            "user_id": 1, "exp": int(time.time()) - 3600,
        }, _JWT_SECRET, algorithm="HS256")
        result = _decode_token(token)
        assert result is None

    def test_decode_token_invalid(self):
        from yuleosh.api.middleware import _decode_token
        result = _decode_token("definitely-not-a-jwt")
        assert result is None

    def test_extract_token_from_dict(self):
        from yuleosh.api.middleware import _extract_token
        result = _extract_token({"Authorization": "Bearer token123"})
        assert result == "token123"

    def test_extract_token_no_auth(self):
        from yuleosh.api.middleware import _extract_token
        result = _extract_token({"Other": "header"})
        assert result is None

    def test_extract_token_not_bearer(self):
        from yuleosh.api.middleware import _extract_token
        result = _extract_token({"Authorization": "Basic dXNlcjpwYXNz"})
        assert result is None

    def test_extract_token_other_type(self):
        from yuleosh.api.middleware import _extract_token
        result = _extract_token("just a string")
        assert result is None


# ======================================================================
# auth.py — Additional auth coverage
# ======================================================================

class TestAuthDeep:
    """Additional auth coverage for handle_me, handle_logout, rate limiting."""

    def setup_method(self):
        # Patch the module global in place (see TestMiddlewareDeep.setup_method
        # for why we never delete/re-import yuleosh.api.auth here).
        import yuleosh.api.auth as _auth_mod
        self._saved_auth_secret = _auth_mod._JWT_SECRET
        _auth_mod._JWT_SECRET = _JWT_SECRET

    def teardown_method(self):
        import yuleosh.api.auth as _auth_mod
        _auth_mod._JWT_SECRET = self._saved_auth_secret

    def test_slugify(self):
        from yuleosh.api.auth import _slugify
        result = _slugify("Hello World")
        # The slugify function is: re.sub(r"[^a-z0-9-]", "", text.lower().replace(" ", "-"))
        assert result == "hello-world"
        assert _slugify("Test Org!@#") == "test-org"
        assert _slugify("   Spaces   ") == "---spaces---"

    def test_hash_and_verify_password(self):
        from yuleosh.api.auth import _hash_password, _verify_password
        pw = "SecureP@ss123!"
        hashed = _hash_password(pw)
        assert hashed != pw
        assert hashed.startswith("$2b$")
        assert _verify_password(pw, hashed) is True
        assert _verify_password("wrong", hashed) is False
        assert _verify_password("", hashed) is False

    def test_verify_password_bad_hash(self):
        from yuleosh.api.auth import _verify_password
        assert _verify_password("pass", "not-a-bcrypt-hash") is False
        assert _verify_password("pass", "") is False

    def test_generate_token(self):
        from yuleosh.api.auth import _generate_token
        token = _generate_token(1, 1, "user@test.com")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_token_valid(self):
        from yuleosh.api.auth import _generate_token, _decode_token
        token = _generate_token(1, 1, "test@test.com")
        payload = _decode_token(token)
        assert payload is not None
        # A1 (v3.8.0): claims unified to sub/org (SHALL-A1.3).
        assert payload["sub"] == "1"
        assert payload["org"] == 1
        assert payload["email"] == "test@test.com"

    def test_decode_token_expired(self):
        from yuleosh.api.auth import _decode_token
        import jwt
        token = jwt.encode({
            "user_id": 1, "exp": int(time.time()) - 3600,
        }, _JWT_SECRET, algorithm="HS256")
        result = _decode_token(token)
        assert result is None

    def test_decode_token_invalid(self):
        from yuleosh.api.auth import _decode_token
        result = _decode_token("invalid-token")
        assert result is None

    def test_extract_token(self):
        from yuleosh.api.auth import _extract_token
        assert _extract_token({"Authorization": "Bearer tok"}) == "tok"
        assert _extract_token({}) is None
        assert _extract_token("") is None

    def test_check_rate_limit(self):
        # A1 (v3.8.0): shared limiter counts FAILED attempts only
        # (SHALL-A1.6); _check_rate_limit is a pure check.
        from yuleosh.api.auth import (
            _check_rate_limit, _SIGNIN_RATE_LIMIT,
            _check_and_record_failed_attempt, _MAX_SIGNIN_ATTEMPTS,
        )
        _SIGNIN_RATE_LIMIT.clear()
        email = "spammer@example.com"

        # First access - not blocked
        blocked = _check_rate_limit(email)
        assert blocked is False

        # Fill rate limit (failed attempts)
        for _ in range(_MAX_SIGNIN_ATTEMPTS):
            _check_and_record_failed_attempt(email)

        # Now should be blocked
        blocked = _check_rate_limit(email)
        assert blocked is True

    def test_check_rate_limit_window_reset(self):
        from yuleosh.api.auth import _check_rate_limit, _SIGNIN_RATE_LIMIT
        _SIGNIN_RATE_LIMIT.clear()
        email = "old-attempts@test.com"
        # Add old entries (older than the 5-minute window)
        _SIGNIN_RATE_LIMIT[email] = (5, int(time.time()) - 600)  # 10m ago
        blocked = _check_rate_limit(email)
        assert blocked is False  # Window expired, reset and counted as 1

    def test_user_response(self):
        from yuleosh.api.auth import _user_response
        user = {"id": 1, "email": "a@b.com", "role": "admin"}
        org = {"id": 1, "name": "Org", "slug": "org"}
        result = _user_response(user, org)
        assert result["id"] == 1
        assert result["email"] == "a@b.com"
        assert result["role"] == "admin"
        assert result["org"]["name"] == "Org"

    def test_handle_me_no_handler(self):
        from yuleosh.api.auth import handle_auth
        result, status = handle_auth(method="GET", path_tail="me", body={}, query={})
        assert status == 401

    def test_handle_me_bad_token(self):
        from yuleosh.api.auth import handle_auth
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer badtoken"}
        result, status = handle_auth(
            method="GET", path_tail="me", body={}, query={}, handler=handler
        )
        assert status == 401

    def test_handle_logout_no_handler(self):
        from yuleosh.api.auth import handle_auth
        result, status = handle_auth(method="POST", path_tail="logout", body={}, query={})
        assert status == 200

    def test_handle_logout_with_token(self):
        from yuleosh.api.auth import handle_auth
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer somerandomtoken"}
        result, status = handle_auth(
            method="POST", path_tail="logout", body={}, query={}, handler=handler
        )
        assert status == 200
        assert result["data"]["message"] == "Logged out successfully"

    def test_handle_login_rate_limited(self):
        from yuleosh.api.auth import handle_auth, _SIGNIN_RATE_LIMIT, _MAX_SIGNIN_ATTEMPTS
        _SIGNIN_RATE_LIMIT.clear()
        email = "ratelimited@test.com"
        for _ in range(_MAX_SIGNIN_ATTEMPTS):
            handle_auth(method="POST", path_tail="login",
                        body={"email": email, "password": "pass"}, query={})
        result, status = handle_auth(method="POST", path_tail="login",
                                     body={"email": email, "password": "pass"}, query={})
        assert status == 429
        assert "Too many attempts" in result["error"]

    def test_login_no_password(self):
        from yuleosh.api.auth import handle_auth
        result, status = handle_auth(method="POST", path_tail="login",
                                     body={"email": "test@test.com"}, query={})
        assert status == 400
        assert "Password is required" in result["error"]

    def test_handle_register_already_exists(self):
        from yuleosh.api.auth import handle_auth
        r1, s1 = handle_auth(method="POST", path_tail="register",
                             body={"email": "dup@test.com", "password": "TestPass123!",
                                   "organization_name": "DupOrg"}, query={})
        r2, s2 = handle_auth(method="POST", path_tail="register",
                             body={"email": "dup@test.com", "password": "TestPass123!",
                                   "organization_name": "DupOrg"}, query={})
        assert s2 == 409
        assert "already registered" in r2["error"].lower()


# ======================================================================
# wizard.py — _get_org_id_from_handler edge cases
# ======================================================================

class TestWizardDeep:
    """Additional wizard coverage."""

    def test_wizard_no_handler(self):
        from yuleosh.api.wizard import _get_org_id_from_handler
        result = _get_org_id_from_handler(None)
        assert result == 0

    def test_wizard_no_auth_header(self):
        from yuleosh.api.wizard import _get_org_id_from_handler
        handler = MagicMock()
        handler.headers = {}
        result = _get_org_id_from_handler(handler)
        assert result == 0

    def test_wizard_bad_token(self):
        from yuleosh.api.wizard import _get_org_id_from_handler
        handler = MagicMock()
        handler.headers = {"Authorization": "Bearer invalid-token"}
        result = _get_org_id_from_handler(handler)
        assert result == 0

    def test_wizard_not_bearer(self):
        from yuleosh.api.wizard import _get_org_id_from_handler
        handler = MagicMock()
        handler.headers = {"Authorization": "Basic base64"}
        result = _get_org_id_from_handler(handler)
        assert result == 0


# ======================================================================
# ci.py — Additional edge cases
# ======================================================================

class TestCIDeep:
    """Additional CI coverage."""

    def test_list_ci_runs_empty_dir(self, tmp_path):
        from yuleosh.api.ci import handle_ci
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_ci("GET", "runs", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
            assert status == 200
            assert result["data"]["count"] == 0

    def test_list_ci_runs_no_ci_dir(self, tmp_path):
        from yuleosh.api.ci import handle_ci
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            result, status = handle_ci("GET", "runs", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
            assert status == 200
            assert result["data"]["count"] == 0

    def test_list_ci_runs_with_json_error(self, tmp_path):
        """Broken JSON files raise JSONDecodeError (source code doesn't catch)."""
        from yuleosh.api.ci import handle_ci
        import json
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "layer1-broken.json").write_text("not-valid-json")
        with patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            with pytest.raises(json.JSONDecodeError):
                handle_ci("GET", "runs", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})

    def test_run_invalid_layer_zero(self):
        from yuleosh.api.ci import handle_ci
        result, status = handle_ci("POST", "run/0", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert result["ok"] is False
        assert "Invalid CI layer" in result["error"]

    def test_run_layer_3_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
            from yuleosh.api.ci import handle_ci
            result, status = handle_ci("POST", "run/3", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
            assert status == 200
            assert result["data"]["layer"] == 3


# ======================================================================
# webhooks.py — trigger_ci success path
# ======================================================================

class TestWebhooksDeep:
    """Additional webhook coverage — trigger_ci success and failure."""

    def test_trigger_ci_success(self):
        """_trigger_pipeline submits a job via async runner (v3.4.0)."""
        from yuleosh.api.webhooks import _trigger_pipeline
        with patch("yuleosh.pipeline.async_runner.submit_pipeline",
                   return_value="job-1234567890abcdef") as m_submit:
            with patch("yuleosh.store.Store") as m_store:
                m_store.return_value.save_ci.return_value = None
                result = _trigger_pipeline(
                    "/tmp/proj", "user/repo", "generic-embedded-c",
                    "main", "abc123def", "commit message",
                )
        assert result is not None
        assert result["status"] == "queued"
        assert result["job_id"] == "job-1234567890abcdef"
        assert result["type"] == "ci"
        m_submit.assert_called_once()

    def test_trigger_ci_failure(self):
        """_trigger_pipeline returns None when the runner fails."""
        from yuleosh.api.webhooks import _trigger_pipeline
        with patch("yuleosh.pipeline.async_runner.submit_pipeline",
                   side_effect=RuntimeError("boom")):
            result = _trigger_pipeline(
                "/tmp/proj", "user/repo", "generic-embedded-c",
                "main", "abc123def", "commit message",
            )
        assert result is None
