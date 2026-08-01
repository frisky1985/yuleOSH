# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""P0 security tests for POST /api/v1/pipeline/trigger.

Covers:
  - authentication required (401 without valid session)
  - project_dir path whitelist (../ traversal → 403)
  - type / layer whitelist (400)
  - arxml_content / config_json size caps (400)
  - submission throttle (429)
"""

import json
import os
from pathlib import Path
from unittest import mock

import pytest
import jwt as pyjwt

# JWT secret must match the middleware secret used by api/auth at import time.
_TEST_SECRET = "pipeline-trigger-test-secret-32chars!!"
_TEST_USER_ID = 987654321  # unique id: avoid colliding with shared-store user 1


@pytest.fixture(autouse=True)
def _jwt_secret():
    import yuleosh.api.auth as _auth_mod
    import yuleosh.api.middleware as _mw_mod
    saved_a = _auth_mod._JWT_SECRET
    saved_m = _mw_mod._JWT_SECRET
    _auth_mod._JWT_SECRET = _TEST_SECRET
    _mw_mod._JWT_SECRET = _TEST_SECRET
    yield
    _auth_mod._JWT_SECRET = saved_a
    _mw_mod._JWT_SECRET = saved_m


def _authed_handler(token: str):
    handler = mock.MagicMock()
    handler.headers = {"Authorization": f"Bearer {token}"}
    handler.client_address = ("127.0.0.1", 12345)
    handler._request_start_time = 0.0
    return handler


def _valid_token() -> str:
    return pyjwt.encode(
        {"user_id": _TEST_USER_ID, "org_id": 1, "email": "t@t.com",
         "iat": 0, "exp": 9999999999},
        _TEST_SECRET, algorithm="HS256",
    )


def _call(body: dict, token: str = None):
    """Call handle_pipeline('trigger') through the require_auth wrapper."""
    from yuleosh.api.pipeline import handle_pipeline
    kwargs = {}
    if token is None:
        # No auth → expect 401 (fail-closed via handler with empty headers)
        handler = mock.MagicMock()
        handler.headers = {}
        kwargs["handler"] = handler
    else:
        kwargs["handler"] = _authed_handler(token)
    return handle_pipeline("POST", "trigger", body, {}, **kwargs)


@pytest.fixture(autouse=True)
def _seed_user_session():
    """Seed the store so the JWT user + session resolve (auth success path).

    Uses a unique user id and removes its rows afterwards so the shared
    Store singleton is not polluted for other test files.
    """
    from datetime import datetime
    from yuleosh.store import Store
    store = Store()
    token = _valid_token()
    now = datetime.now().isoformat()
    store.conn.execute(
        "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
        (_TEST_USER_ID, 1, "t@t.com", "admin", now)
    )
    store.conn.execute(
        "INSERT OR IGNORE INTO user_sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_TEST_USER_ID, token, now, "2099-12-31")
    )
    store.conn.commit()
    yield
    try:
        store.conn.execute("DELETE FROM users WHERE id=?", (_TEST_USER_ID,))
        store.conn.execute(
            "DELETE FROM user_sessions WHERE user_id=?", (_TEST_USER_ID,))
        store.conn.commit()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Reset the submission gate between tests."""
    from yuleosh.api import pipeline as _pipe
    with _pipe._TRIGGER_GATE_LOCK:
        _pipe._TRIGGER_GATE_TIMES.clear()
    yield
    with _pipe._TRIGGER_GATE_LOCK:
        _pipe._TRIGGER_GATE_TIMES.clear()


@pytest.fixture
def osh_home(tmp_path, monkeypatch):
    monkeypatch.setenv("OSH_HOME", str(tmp_path))
    return tmp_path


class TestPipelineTriggerAuth:
    def test_trigger_requires_auth(self):
        """No Authorization header → 401 (fail-closed)."""
        result, status = _call({"project_dir": "/tmp"})
        assert status == 401
        assert result["ok"] is False

    def test_trigger_invalid_token(self):
        """Bad bearer token → 401."""
        result, status = _call({"project_dir": "/tmp"}, token="not-a-jwt")
        assert status == 401


class TestPipelineTriggerPathWhitelist:
    def test_trigger_path_outside_osh_home(self, osh_home):
        """Absolute path outside OSH_HOME → 403."""
        result, status = _call({"project_dir": "/etc"}, token=_valid_token())
        assert status == 403
        assert "inside OSH_HOME" in result["error"]

    def test_trigger_path_traversal(self, osh_home):
        """../ traversal escaping OSH_HOME → 403."""
        escape = str(osh_home / ".." / ".." / "..")
        result, status = _call({"project_dir": escape}, token=_valid_token())
        assert status == 403

    @mock.patch("yuleosh.pipeline.async_runner.submit_full_pipeline", return_value="job-1")
    def test_trigger_valid_full(self, mock_submit, osh_home):
        """Valid project_dir inside OSH_HOME → job_id."""
        result, status = _call({"project_dir": str(osh_home), "type": "full"},
                               token=_valid_token())
        assert status == 200
        assert result["data"]["job_id"] == "job-1"
        mock_submit.assert_called_once()

    @mock.patch("yuleosh.pipeline.async_runner.submit_pipeline", return_value="job-2")
    def test_trigger_valid_ci(self, mock_submit, osh_home):
        """Valid CI trigger with layer → job_id."""
        result, status = _call({"project_dir": str(osh_home), "type": "ci", "layer": 2},
                               token=_valid_token())
        assert status == 200
        assert result["data"]["job_id"] == "job-2"


class TestPipelineTriggerValidation:
    def test_trigger_bad_type(self, osh_home):
        result, status = _call({"project_dir": str(osh_home), "type": "evil"},
                               token=_valid_token())
        assert status == 400

    def test_trigger_bad_layer(self, osh_home):
        result, status = _call({"project_dir": str(osh_home), "type": "ci", "layer": 99},
                               token=_valid_token())
        assert status == 400

    def test_trigger_arxml_too_large(self, osh_home):
        result, status = _call(
            {"project_dir": str(osh_home), "arxml_content": "x" * 1_000_001},
            token=_valid_token(),
        )
        assert status == 400
        assert "arxml_content too large" in result["error"]

    def test_trigger_config_too_large(self, osh_home):
        result, status = _call(
            {"project_dir": str(osh_home), "config_json": "x" * 1_000_001},
            token=_valid_token(),
        )
        assert status == 400

    def test_trigger_missing_project_dir(self, monkeypatch):
        monkeypatch.delenv("OSH_HOME", raising=False)
        result, status = _call({}, token=_valid_token())
        assert status == 400


class TestPipelineTriggerThrottle:
    def test_trigger_throttled(self, osh_home):
        """Sliding-window gate rejects excess submissions with 429."""
        import time as _t
        from yuleosh.api import pipeline as _pipe
        with _pipe._TRIGGER_GATE_LOCK:
            _pipe._TRIGGER_GATE_TIMES = [_t.time()] * _pipe._TRIGGER_MAX_PER_WINDOW
        result, status = _call({"project_dir": str(osh_home)}, token=_valid_token())
        assert status == 429


class TestPipelineTriggerRouterIntegration:
    """Trigger reachable via router.dispatch (POST /api/v1/pipeline/trigger)."""

    def test_router_trigger_unauth_401(self):
        """Router dispatch of trigger without token → 401 JSON."""
        from yuleosh.api.router import dispatch
        import io
        handler = mock.MagicMock()
        handler.command = "POST"
        handler.headers.get.side_effect = lambda k, d="": {
            "Content-Length": str(len(b"{}")),
            "Content-Type": "application/json",
        }.get(k, d)
        handler.rfile.read.return_value = b"{}"
        handler.client_address = ("127.0.0.1", 12345)
        handler._request_start_time = 0.0
        handler.wfile = io.BytesIO()
        dispatch(handler, "/api/v1/pipeline/trigger")
        assert handler.send_response.call_args[0][0] == 401
