"""Server integration tests for v1.0.0 — end-to-end API flows."""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestServerIntegration:
    """GIVEN running server WHEN making API calls THEN expected responses."""

    @classmethod
    def setup_class(cls):
        """Start server in background thread for integration tests."""
        from ui import server as srv
        cls.server_thread = threading.Thread(
            target=srv.main, kwargs={"port": 19876}, daemon=True
        )
        cls.server_thread.start()
        time.sleep(1)

    def _api(self, path, method="GET", body=None, token=None):
        """Make HTTP request to test server."""
        url = f"http://localhost:19876{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return json.loads(resp.read()), resp.status
        except urllib.error.HTTPError as e:
            return json.loads(e.read()), e.code

    def test_health(self):
        """GIVEN running server WHEN health check THEN ok."""
        data, status = self._api("/api/health")
        assert status == 200
        assert data["status"] == "ok"

    def test_signin_new_user(self):
        """GIVEN new email WHEN signin THEN needs_org response."""
        data, status = self._api("/api/auth/signin", method="POST",
                                  body={"email": "itest@v1.com"})
        assert status == 200
        assert data.get("needs_org") is True

    def test_unauthorized_session(self):
        """GIVEN invalid token WHEN session info THEN 401."""
        data, status = self._api("/api/auth/session", token="bad-token")
        assert status == 401

    def test_usage_unauthorized(self):
        """GIVEN no token WHEN usage API THEN 401."""
        data, status = self._api("/api/v1/usage")
        assert status == 401
