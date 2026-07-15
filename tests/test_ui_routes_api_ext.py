# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Extended tests for yuleosh.ui.routes.api_routes — API endpoint handlers."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Mock handler factory ──────────────────────────────────────────────

def _make_mock_handler(headers=None, path="/", method="GET", body=b""):
    """Create a minimal mock BaseHTTPRequestHandler."""
    handler = mock.MagicMock(spec=BaseHTTPRequestHandler)
    class MockHeaders(dict):
        def items(self):
            return super().items()
    handler.headers = MockHeaders(headers or {})
    handler.path = path
    handler.command = method
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.send_response = mock.MagicMock()
    handler.send_header = mock.MagicMock()
    handler.end_headers = mock.MagicMock()
    return handler


# =====================================================================
# handle_status
# =====================================================================

class TestHandleStatus:
    """GIVEN handle_status WHEN called THEN returns server status dict."""

    def test_status_returns_running(self):
        """GIVEN mock handler WHEN handle_status THEN status='running'."""
        from yuleosh.ui.routes.api_routes import handle_status
        handler = _make_mock_handler()
        result = handle_status(handler)
        assert result["status"] == "running"
        assert "osh_home" in result
        assert "version" in result
        assert "timestamp" in result

    def test_status_uses_osh_home_env(self):
        """GIVEN OSH_HOME env WHEN handle_status THEN uses it."""
        from yuleosh.ui.routes.api_routes import handle_status
        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": "/custom/path"}):
            result = handle_status(handler)
            assert result["osh_home"] == "/custom/path"


# =====================================================================
# handle_health
# =====================================================================

class TestHandleHealth:
    """GIVEN handle_health WHEN called THEN returns health data."""

    def test_health_returns_ok(self):
        """GIVEN mock handler WHEN handle_health THEN status='ok'."""
        from yuleosh.ui.routes.api_routes import handle_health
        handler = _make_mock_handler()
        result = handle_health(handler)
        assert result["status"] == "ok"
        assert result["version"] == "1.0.0"
        assert "auth_enabled" in result
        assert "tenant_auth" in result

    def test_health_auth_enabled(self):
        """GIVEN AUTH_ENABLED=True WHEN handle_health THEN reflects."""
        from yuleosh.ui.routes.api_routes import handle_health
        handler = _make_mock_handler()
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", True):
            result = handle_health(handler)
            assert result["auth_enabled"] is True

    def test_health_auth_disabled(self):
        """GIVEN AUTH_ENABLED=False WHEN handle_health THEN reflects."""
        from yuleosh.ui.routes.api_routes import handle_health
        handler = _make_mock_handler()
        with mock.patch("yuleosh.ui.auth.AUTH_ENABLED", False):
            result = handle_health(handler)
            assert result["auth_enabled"] is False

    def test_health_tenant_auth_available(self):
        """GIVEN auth_extended importable WHEN handle_health THEN tenant_auth=True."""
        from yuleosh.ui.routes.api_routes import handle_health
        handler = _make_mock_handler()
        result = handle_health(handler)
        # Since auth_extended is importable, tenant_auth should be True
        assert result["tenant_auth"] is True

    def test_health_uses_osh_home_env(self):
        """GIVEN OSH_HOME env WHEN handle_health THEN used."""
        from yuleosh.ui.routes.api_routes import handle_health
        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": "/custom/home"}):
            result = handle_health(handler)
            assert result["osh_home"] == "/custom/home"


# =====================================================================
# list_evidence
# =====================================================================

class TestListEvidence:
    """GIVEN list_evidence WHEN called THEN lists files from .osh/evidence."""

    def test_no_evidence_dir(self, tmp_path):
        """GIVEN no .osh/evidence dir WHEN list_evidence THEN empty list."""
        from yuleosh.ui.routes.api_routes import list_evidence
        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_evidence(handler)
            assert result["count"] == 0
            assert result["files"] == []

    def test_lists_evidence_files(self, tmp_path):
        """GIVEN .osh/evidence with files WHEN list_evidence THEN lists them."""
        from yuleosh.ui.routes.api_routes import list_evidence
        ev_dir = tmp_path / ".osh" / "evidence"
        ev_dir.mkdir(parents=True)
        (ev_dir / "report.pdf").write_text("data")
        (ev_dir / "trace.txt").write_text("trace")

        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_evidence(handler)
            assert result["count"] == 2
            names = [f["name"] for f in result["files"]]
            assert "report.pdf" in names
            assert "trace.txt" in names

    def test_compliance_pack_gets_star(self, tmp_path):
        """GIVEN compliance-pack.zip in evidence WHEN list_evidence THEN name has star."""
        from yuleosh.ui.routes.api_routes import list_evidence
        ev_dir = tmp_path / ".osh" / "evidence"
        ev_dir.mkdir(parents=True)
        (ev_dir / "compliance-pack.zip").write_text("zip content")

        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_evidence(handler)
            assert any("🎯" in f["name"] for f in result["files"])

    def test_has_size_and_mtime(self, tmp_path):
        """GIVEN file in evidence WHEN list_evidence THEN includes size and mtime."""
        from yuleosh.ui.routes.api_routes import list_evidence
        ev_dir = tmp_path / ".osh" / "evidence"
        ev_dir.mkdir(parents=True)
        (ev_dir / "test.txt").write_text("hello")

        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_evidence(handler)
            f = result["files"][0]
            assert "size" in f
            assert "mtime" in f


# =====================================================================
# list_reviews
# =====================================================================

class TestListReviews:
    """GIVEN list_reviews WHEN called THEN lists review sessions."""

    def test_no_reviews_dir(self, tmp_path):
        """GIVEN no .osh/reviews dir WHEN list_reviews THEN empty list."""
        from yuleosh.ui.routes.api_routes import list_reviews
        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_reviews(handler)
            assert result["count"] == 0

    def test_lists_review_sessions(self, tmp_path):
        """GIVEN .osh/reviews with sessions WHEN list_reviews THEN lists them."""
        from yuleosh.ui.routes.api_routes import list_reviews
        rev_dir = tmp_path / ".osh" / "reviews"
        session_dir = rev_dir / "session-001"
        session_dir.mkdir(parents=True)
        (session_dir / "review-session.json").write_text(
            json.dumps({"id": "001", "name": "Code Review"})
        )

        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_reviews(handler)
            assert result["count"] == 1
            assert result["sessions"][0]["name"] == "Code Review"

    def test_skips_dirs_without_session_file(self, tmp_path):
        """GIVEN dir without review-session.json WHEN list_reviews THEN skips."""
        from yuleosh.ui.routes.api_routes import list_reviews
        rev_dir = tmp_path / ".osh" / "reviews"
        (rev_dir / "empty-dir").mkdir(parents=True)

        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_reviews(handler)
            assert result["count"] == 0


# =====================================================================
# list_ci_results
# =====================================================================

class TestListCiResults:
    """GIVEN list_ci_results WHEN called THEN lists CI results."""

    def test_no_ci_dir(self, tmp_path):
        """GIVEN no .osh/ci dir WHEN list_ci_results THEN empty."""
        from yuleosh.ui.routes.api_routes import list_ci_results
        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_ci_results(handler)
            assert result["count"] == 0

    def test_lists_layer_files(self, tmp_path):
        """GIVEN .osh/ci with layer files WHEN list_ci_results THEN listed."""
        from yuleosh.ui.routes.api_routes import list_ci_results
        ci_dir = tmp_path / ".osh" / "ci"
        ci_dir.mkdir(parents=True)
        (ci_dir / "layer1.json").write_text(json.dumps({"layer": 1, "passed": True}))
        (ci_dir / "layer2.json").write_text(json.dumps({"layer": 2, "passed": False}))

        handler = _make_mock_handler()
        with mock.patch.dict(os.environ, {"OSH_HOME": str(tmp_path)}):
            result = list_ci_results(handler)
            assert result["count"] == 2
            assert result["results"][0]["layer"] == 1


# =====================================================================
# handle_pipeline_status
# =====================================================================

class TestHandlePipelineStatus:
    """GIVEN handle_pipeline_status WHEN called THEN returns job status."""

    def test_returns_job_status(self):
        """GIVEN job exists WHEN handle_pipeline_status THEN returns status."""
        from yuleosh.ui.routes.api_routes import handle_pipeline_status
        handler = _make_mock_handler(path="/api/v1/pipeline/status/job-123")

        with mock.patch("yuleosh.pipeline.async_runner.get_job_status") as mock_get:
            mock_get.return_value = {"job_id": "job-123", "status": "completed"}
            result = handle_pipeline_status(handler, "/api/v1/pipeline/status/job-123")
            assert result["status"] == "completed"
            mock_get.assert_called_once_with("job-123")

    def test_returns_404_on_not_found(self):
        """GIVEN job not found WHEN handle_pipeline_status THEN error + 404."""
        from yuleosh.ui.routes.api_routes import handle_pipeline_status
        handler = _make_mock_handler(path="/api/v1/pipeline/status/job-999")

        with mock.patch("yuleosh.pipeline.async_runner.get_job_status", return_value=None):
            result = handle_pipeline_status(handler, "/api/v1/pipeline/status/job-999")
            assert isinstance(result, tuple)
            assert result[0]["error"] == "Job not found"
            assert result[1] == 404

    def test_returns_500_on_exception(self):
        """GIVEN exception in get_job_status WHEN handle_pipeline_status THEN 500."""
        from yuleosh.ui.routes.api_routes import handle_pipeline_status
        handler = _make_mock_handler(path="/api/v1/pipeline/status/job-err")

        with mock.patch("yuleosh.pipeline.async_runner.get_job_status",
                         side_effect=Exception("DB down")):
            result = handle_pipeline_status(handler, "/api/v1/pipeline/status/job-err")
            assert isinstance(result, tuple)
            assert "error" in result[0]
            assert result[1] == 500


# =====================================================================
# handle_usage
# =====================================================================

class TestHandleUsage:
    """GIVEN handle_usage WHEN called THEN returns usage data."""

    def test_unauthorized_no_token(self):
        """GIVEN no Authorization header WHEN handle_usage THEN 401."""
        from yuleosh.ui.routes.api_routes import handle_usage
        handler = _make_mock_handler(headers={})
        result = handle_usage(handler)
        assert isinstance(result, tuple)
        assert result[0]["error"] == "Unauthorized"
        assert result[1] == 401

    def test_unauthorized_invalid_session(self):
        """GIVEN invalid token WHEN handle_usage THEN 401."""
        from yuleosh.ui.routes.api_routes import handle_usage
        handler = _make_mock_handler(headers={"Authorization": "Bearer invalid-token"})

        with mock.patch("yuleosh.ui.auth_extended.get_session_user", return_value=None):
            result = handle_usage(handler)
            assert isinstance(result, tuple)
            assert result[0]["error"] == "Invalid session"
            assert result[1] == 401

    def test_returns_usage_summary(self):
        """GIVEN valid token WHEN handle_usage THEN returns summary."""
        from yuleosh.ui.routes.api_routes import handle_usage
        handler = _make_mock_handler(headers={"Authorization": "Bearer valid-token"})

        with mock.patch("yuleosh.ui.auth_extended.get_session_user") as mock_user:
            mock_user.return_value = {"org_id": 1}
            with mock.patch("yuleosh.usage.metering.get_usage_summary") as mock_summary:
                mock_summary.return_value = {"total_api_calls": 100}
                result = handle_usage(handler)
                assert result["total_api_calls"] == 100

    def test_500_on_exception(self):
        """GIVEN exception in get_usage_summary WHEN handle_usage THEN 500."""
        from yuleosh.ui.routes.api_routes import handle_usage
        handler = _make_mock_handler(headers={"Authorization": "Bearer token"})

        with mock.patch("yuleosh.ui.auth_extended.get_session_user") as mock_user:
            mock_user.return_value = {"org_id": 1}
            with mock.patch("yuleosh.usage.metering.get_usage_summary",
                             side_effect=Exception("DB error")):
                result = handle_usage(handler)
                assert isinstance(result, tuple)
                assert result[1] == 500
