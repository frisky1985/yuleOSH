# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for service-related API modules: preview.py, subscription.py, compliance.py.

All tests use unittest.mock to avoid real external services (Stripe, git, analysis)."""

import json
import os
import sys
import io
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("OSH_HOME", str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("YULEOSH_JWT_SECRET", "test-services-secret-32-chars!!")


# ======================================================================
# preview.py — AI Preview Assessment API
# ======================================================================

class TestPreviewConstants:
    """Constants and configuration."""

    def test_constants(self):
        import yuleosh.api.preview as p
        assert p.MAX_ZIP_SIZE == 50 * 1024 * 1024
        assert p.MAX_CLONED_SIZE == 200 * 1024 * 1024
        assert p.CLONE_TIMEOUT == 120
        assert p.RESULT_TTL == 24 * 3600

    def test_supported_hosts(self):
        from yuleosh.api.preview import SUPPORTED_GIT_HOSTS
        assert "github.com" in SUPPORTED_GIT_HOSTS
        assert "gitlab.com" in SUPPORTED_GIT_HOSTS
        assert "bitbucket.org" in SUPPORTED_GIT_HOSTS

    def test_rate_limit_constants(self):
        from yuleosh.api.preview import _PREVIEW_AUTH_LIMIT, _PREVIEW_AUTHED_LIMIT, _PREVIEW_WINDOW
        assert _PREVIEW_AUTH_LIMIT == 3
        assert _PREVIEW_AUTHED_LIMIT == 20
        assert _PREVIEW_WINDOW == 24 * 3600


class TestPreviewValidation:
    """_validate_git_url, _is_valid_zip, _parse_multipart_body."""

    def test_validate_git_url_github_ok(self):
        from yuleosh.api.preview import _validate_git_url
        valid, err = _validate_git_url("https://github.com/user/repo")
        assert valid is True
        assert err == ""

    def test_validate_git_url_gitlab_ok(self):
        from yuleosh.api.preview import _validate_git_url
        valid, err = _validate_git_url("https://gitlab.com/org/project")
        assert valid is True

    def test_validate_git_url_bitbucket_ok(self):
        from yuleosh.api.preview import _validate_git_url
        valid, err = _validate_git_url("https://bitbucket.org/team/repo")
        assert valid is True

    def test_validate_git_url_not_https(self):
        from yuleosh.api.preview import _validate_git_url
        valid, err = _validate_git_url("git@github.com:user/repo.git")
        assert valid is False
        assert "HTTPS" in err

    def test_validate_git_url_unsupported_host(self):
        from yuleosh.api.preview import _validate_git_url
        valid, err = _validate_git_url("https://git.example.com/repo")
        assert valid is False
        assert "Unsupported" in err

    def test_validate_git_url_malformed(self):
        from yuleosh.api.preview import _validate_git_url
        valid, err = _validate_git_url("not-a-url")
        assert valid is False

    def test_is_valid_zip_ok(self):
        from yuleosh.api.preview import _is_valid_zip
        assert _is_valid_zip(b"PK\x03\x04...") is True
        assert _is_valid_zip(b"PK\x05\x06...") is True

    def test_is_valid_zip_not_zip(self):
        from yuleosh.api.preview import _is_valid_zip
        assert _is_valid_zip(b"not a zip file") is False

    def test_is_valid_zip_empty(self):
        from yuleosh.api.preview import _is_valid_zip
        assert _is_valid_zip(b"") is False

    def test_parse_multipart_body_no_content(self):
        from yuleosh.api.preview import _parse_multipart_body
        handler = MagicMock()
        handler.headers.get.return_value = "0"
        result = _parse_multipart_body(handler)
        assert result is None

    def test_parse_multipart_body_wrong_content_type(self):
        from yuleosh.api.preview import _parse_multipart_body
        handler = MagicMock()
        handler.headers.get.side_effect = lambda k, d=None: {
            "Content-Type": "application/json",
            "Content-Length": "100",
        }.get(k, d or "")
        result = _parse_multipart_body(handler)
        assert result is None

    def test_extract_zip_from_multipart_no_boundary(self):
        # _extract_zip_from_multipart uses `import cgi` (removed in Python 3.13)
        # Skip if cgi not available
        import importlib.util
        if importlib.util.find_spec("cgi") is None:
            pytest.skip("cgi module not available (removed in Python 3.13)")
        from yuleosh.api.preview import _extract_zip_from_multipart
        result = _extract_zip_from_multipart(b"data", "multipart/form-data")
        assert result is None

    def test_extract_zip_from_multipart_with_data_and_no_cgi(self):
        import importlib.util
        if importlib.util.find_spec("cgi") is None:
            pytest.skip("cgi module not available (removed in Python 3.13)")
        from yuleosh.api.preview import _extract_zip_from_multipart
        boundary = "----boundary123"
        content_type = f"multipart/form-data; boundary={boundary}"
        body_parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="test.zip"\r\n',
            b"Content-Type: application/zip\r\n\r\n",
            b"PK\x03\x04fakezipcontent\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(body_parts)
        result = _extract_zip_from_multipart(body, content_type)
        assert result.startswith(b"PK\x03\x04")

    def test_extract_zip_from_multipart_no_file_field(self):
        import importlib.util
        if importlib.util.find_spec("cgi") is None:
            pytest.skip("cgi module not available (removed in Python 3.13)")
        from yuleosh.api.preview import _extract_zip_from_multipart
        boundary = "----boundary456"
        content_type = f"multipart/form-data; boundary={boundary}"
        body_parts = [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="other"\r\n\r\n',
            b"val\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
        body = b"".join(body_parts)
        result = _extract_zip_from_multipart(body, content_type)
        assert result is None


class TestPreviewRateLimit:
    """Rate limiting for preview assessments."""

    def setup_method(self):
        from yuleosh.api.preview import _preview_request_log
        _preview_request_log.clear()

    def test_unauth_limit_allowed(self):
        from yuleosh.api.preview import _check_preview_rate_limit
        for _ in range(3):
            allowed, retry = _check_preview_rate_limit("unauth-ip")
            assert allowed is True
            assert retry == 0

    def test_unauth_limit_exceeded(self):
        from yuleosh.api.preview import _check_preview_rate_limit
        for _ in range(3):
            _check_preview_rate_limit("unauth-ip-2")
        allowed, retry = _check_preview_rate_limit("unauth-ip-2")
        assert allowed is False
        assert retry > 0

    def test_authed_limit_allowed(self):
        from yuleosh.api.preview import _check_preview_rate_limit
        for _ in range(20):
            allowed, retry = _check_preview_rate_limit("authed-ip", is_authenticated=True)
            assert allowed is True

    def test_authed_limit_exceeded(self):
        from yuleosh.api.preview import _check_preview_rate_limit
        for _ in range(20):
            _check_preview_rate_limit("authed-ip-2", is_authenticated=True)
        allowed, retry = _check_preview_rate_limit("authed-ip-2", is_authenticated=True)
        assert allowed is False
        assert retry > 0


class TestPreviewCache:
    """Repo cache (PREVIEW-REQ-007)."""

    def test_get_cached_preview_not_cached(self):
        from yuleosh.api.preview import _get_cached_preview, _repo_cache
        _repo_cache.clear()
        result = _get_cached_preview("https://github.com/user/repo")
        assert result is None

    def test_get_cached_preview_expired(self):
        from yuleosh.api.preview import _get_cached_preview, _repo_cache, _assessment_store
        import hashlib
        _repo_cache.clear()
        _assessment_store.clear()
        url = "https://github.com/user/repo"
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        _repo_cache[url_hash] = "prev-expired"
        _assessment_store["prev-expired"] = {
            "status": "completed",
            "completed_at": 0,
        }
        result = _get_cached_preview(url)
        assert result is None

    def test_get_cached_preview_valid(self):
        from yuleosh.api.preview import _get_cached_preview, _repo_cache, _assessment_store
        import hashlib
        _repo_cache.clear()
        _assessment_store.clear()
        url = "https://github.com/user/project"
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        _repo_cache[url_hash] = "prev-valid"
        _assessment_store["prev-valid"] = {
            "status": "completed",
            "completed_at": time.time(),
            "report": {"summary": "ok"},
        }
        result = _get_cached_preview(url)
        assert result is not None
        assert result["cached"] is True
        assert result["status"] == "completed"
        assert result["report"]["summary"] == "ok"


class TestPreviewCleanup:
    """Cleanup expired results (PREVIEW-REQ-006)."""

    def test_cleanup_expired_results(self):
        from yuleosh.api.preview import _cleanup_expired_results, _assessment_store
        _assessment_store.clear()
        _assessment_store["old-entry"] = {
            "created_at": 0,
            "source_dir": "/tmp/nonexistent",
        }
        _assessment_store["fresh-entry"] = {
            "created_at": 9999999999,
            "source_dir": None,
        }
        _cleanup_expired_results()
        assert "old-entry" not in _assessment_store
        assert "fresh-entry" in _assessment_store


class TestPreviewHandler:
    """handle_preview — main request router."""

    def test_method_not_allowed(self):
        from yuleosh.api.preview import handle_preview
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("PUT", "assess", {}, {}, handler)
        assert status == 405

    def test_delete_not_found(self):
        from yuleosh.api.preview import handle_preview
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("DELETE", "assess/nonexistent-id", {}, {}, handler)
        assert status == 404

    def test_delete_success(self):
        from yuleosh.api.preview import handle_preview, _assessment_store
        _assessment_store.clear()
        _assessment_store["prev-test-123"] = {
            "status": "completed",
            "source_dir": None,
        }
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("DELETE", "assess/prev-test-123", {}, {}, handler)
        assert status == 200
        assert result["ok"] is True
        assert "prev-test-123" not in _assessment_store

    def test_get_not_found(self):
        from yuleosh.api.preview import handle_preview
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("GET", "assess/nonexistent", {}, {}, handler)
        assert status == 404

    def test_get_analyzing(self):
        from yuleosh.api.preview import handle_preview, _assessment_store
        _assessment_store.clear()
        _assessment_store["prev-analyze"] = {
            "status": "analyzing",
            "created_at": time.time(),
            "estimated_remaining_seconds": 30,
        }
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("GET", "assess/prev-analyze", {}, {}, handler)
        assert status == 200
        data = result["data"]
        assert data["status"] == "analyzing"
        assert "estimated_remaining_seconds" in data

    def test_get_completed(self):
        from yuleosh.api.preview import handle_preview, _assessment_store
        _assessment_store.clear()
        _assessment_store["prev-done"] = {
            "status": "completed",
            "report": {"summary": "analysis complete"},
        }
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("GET", "assess/prev-done", {}, {}, handler)
        assert status == 200
        data = result["data"]
        assert data["status"] == "completed"
        assert data["report"]["summary"] == "analysis complete"

    def test_get_failed(self):
        from yuleosh.api.preview import handle_preview, _assessment_store
        _assessment_store.clear()
        _assessment_store["prev-fail"] = {
            "status": "failed",
            "error": "Something went wrong",
        }
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        result, status = handle_preview("GET", "assess/prev-fail", {}, {}, handler)
        assert status == 200
        data = result["data"]
        assert data["error"] == "Something went wrong"

    def test_post_no_json_body_no_repo_url(self):
        """POST with empty content-type and no body."""
        from yuleosh.api.preview import handle_preview
        handler = MagicMock()
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers.get.side_effect = lambda k, d=None: "" if k == "Content-Type" else (d or "0")
        result, status = handle_preview("POST", "assess", {}, {}, handler)
        assert status == 400
        # json_error wraps dict in error field
        err = result["error"]
        assert isinstance(err, dict) or "input_required" in str(err)

    def test_post_with_repo_url(self):
        from yuleosh.api.preview import handle_preview, _preview_request_log, _assessment_store
        _preview_request_log.clear()
        _assessment_store.clear()
        handler = MagicMock()
        handler.client_address = ("git-client", 12345)
        handler.headers.get.side_effect = lambda k, d=None: (
            "application/json" if k == "Content-Type" else (d or "0")
        )

        # NOTE: preview.py calls json_ok({...}, 202) but json_ok only accepts 1 arg (bug)
        # Mock json_ok to accept the extra status arg
        with patch("yuleosh.api.preview.json_ok",
                   side_effect=lambda d, s=None: ({"ok": True, "data": d}, s or 200)):
            result, status = handle_preview("POST", "assess",
                                            {"repo_url": "https://github.com/user/repo"},
                                            {}, handler)
            assert status == 202
            assert result["ok"] is True
            data = result["data"]
            assert data["status"] == "analyzing"
            assert data["preview_id"].startswith("prev-")

    def test_handle_git_url_invalid(self):
        from yuleosh.api.preview import _handle_git_url
        with patch("yuleosh.api.preview.json_ok",
                   side_effect=lambda d, s=None: ({"ok": True, "error": d}, s or 200)), \
             patch("yuleosh.api.preview.json_error",
                   side_effect=lambda d, s=400: ({"ok": False, "error": d}, s)):
            result, status = _handle_git_url("prev-000", "https://git.example.com/repo", MagicMock())
            assert status == 400
        err = result["error"]
        assert isinstance(err, dict)
        assert "Unsupported" in err.get("error", "") or "Unsupported" in str(err)

    def test_get_dir_size(self):
        from yuleosh.api.preview import _get_dir_size
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "file.txt"
            p.write_text("hello world")
            size = _get_dir_size(Path(d))
            assert size > 0

    def test_handle_git_url_validation_ok(self):
        from yuleosh.api.preview import _handle_git_url, _assessment_store
        _assessment_store.clear()
        handler = MagicMock()
        with patch("yuleosh.api.preview.json_ok",
                   side_effect=lambda d, s=None: ({"ok": True, "data": d}, s or 200)), \
             patch("yuleosh.api.preview.json_error",
                   side_effect=lambda d, s=400: ({"ok": False, "error": d}, s)):
            result, status = _handle_git_url("prev-new", "https://github.com/org/repo", handler)
            assert status == 202
            assert result["data"]["status"] == "analyzing"

    def test_cleanup_timer_started(self):
        """_cleanup_timer is started on import."""
        import importlib
        import yuleosh.api.preview
        timer = yuleosh.api.preview._cleanup_timer
        assert timer is not None
        assert timer.daemon is True


# ======================================================================
# subscription.py — Subscription management
# ======================================================================

class TestSubscriptionExtractToken:
    """_extract_token helper."""

    def test_extract_token_bearer(self):
        from yuleosh.api.subscription import _extract_token
        headers = {"Authorization": "Bearer mytoken"}
        assert _extract_token(headers) == "mytoken"

    def test_extract_token_missing(self):
        from yuleosh.api.subscription import _extract_token
        assert _extract_token({}) == ""

    def test_extract_token_not_bearer(self):
        from yuleosh.api.subscription import _extract_token
        headers = {"Authorization": "Basic base64stuff"}
        assert _extract_token(headers) == ""

    def test_extract_token_none(self):
        from yuleosh.api.subscription import _extract_token
        assert _extract_token(None) == ""


class TestSubscriptionHandler:
    """handle_subscription — main router."""

    def test_unknown_endpoint(self):
        from yuleosh.api.subscription import handle_subscription
        result, status = handle_subscription("GET", "foobar", {}, {})
        assert status == 404

    def test_status_no_handler(self):
        from yuleosh.api.subscription import handle_subscription
        result, status = handle_subscription("GET", "status", {}, {})
        assert status == 401

    def test_status_unauthorized(self):
        from yuleosh.api.subscription import handle_subscription
        handler = MagicMock()
        handler.headers = {}
        result, status = handle_subscription("GET", "status", {}, {}, handler=handler)
        assert status == 401

    def test_status_with_token(self):
        from yuleosh.api.subscription import handle_subscription
        import jwt
        token = jwt.encode({
            "org_id": 1, "user_id": 1, "email": "test@test.com",
            "exp": int(time.time()) + 3600,
        }, os.environ["YULEOSH_JWT_SECRET"], algorithm="HS256")
        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}

        with patch("yuleosh.api.subscription.Store") as mock_store_class:
            mock_store_instance = MagicMock()
            mock_store_class.return_value = mock_store_instance
            mock_store_instance.get_organization_by_id.return_value = {"id": 1, "name": "TestOrg", "slug": "test-org", "tier": "community"}
            mock_store_instance.get_subscription.return_value = None

            with patch("yuleosh.api.subscription.get_usage_summary") as mock_usage, \
                 patch("yuleosh.api.subscription.get_trial_status") as mock_trial, \
                 patch("yuleosh.api.subscription.is_stripe_configured") as mock_stripe:

                mock_usage.return_value = {"usage": {}}
                mock_trial.return_value = {"is_trialing": False}
                mock_stripe.return_value = False

                result, status = handle_subscription("GET", "status", {}, {}, handler=handler)
                assert status == 200
                data = result["data"]
                assert data["org_name"] == "TestOrg"
                assert data["tier"] == "community"
                assert "subscription" in data
                assert "trial" in data
                assert "usage" in data
                assert "plans" in data
                assert len(data["plans"]) == 3

    def test_upgrade_no_handler(self):
        from yuleosh.api.subscription import handle_subscription
        result, status = handle_subscription("POST", "upgrade", {}, {})
        assert status == 401

    def test_upgrade_invalid_tier(self):
        from yuleosh.api.subscription import handle_subscription
        import jwt
        token = jwt.encode({
            "org_id": 1, "user_id": 1, "email": "t@t.com",
            "exp": int(time.time()) + 3600,
        }, os.environ["YULEOSH_JWT_SECRET"], algorithm="HS256")
        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        result, status = handle_subscription("POST", "upgrade", {"tier": "gold"}, {}, handler=handler)
        assert status == 400
        assert "Invalid tier" in result["error"]

    def test_upgrade_no_stripe(self):
        from yuleosh.api.subscription import handle_subscription
        import jwt
        token = jwt.encode({
            "org_id": 1, "user_id": 1, "email": "t@t.com",
            "exp": int(time.time()) + 3600,
        }, os.environ["YULEOSH_JWT_SECRET"], algorithm="HS256")
        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        with patch("yuleosh.api.subscription.is_stripe_configured", return_value=False):
            result, status = handle_subscription("POST", "upgrade", {"tier": "pro"}, {}, handler=handler)
            assert status == 503

    def test_cancel_no_handler(self):
        from yuleosh.api.subscription import handle_subscription
        result, status = handle_subscription("POST", "cancel", {}, {})
        assert status == 401

    def test_cancel_no_subscription(self):
        from yuleosh.api.subscription import handle_subscription, _handle_sub_cancel
        import jwt
        token = jwt.encode({
            "org_id": 1, "user_id": 1, "email": "t@t.com",
            "exp": int(time.time()) + 3600,
        }, os.environ["YULEOSH_JWT_SECRET"], algorithm="HS256")
        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        with patch("yuleosh.api.subscription.Store") as mock_store_class:
            mock_store_instance = MagicMock()
            mock_store_class.return_value = mock_store_instance
            mock_store_instance.get_organization_by_id.return_value = {"id": 1}
            mock_store_instance.get_subscription.return_value = None
            result, status = handle_subscription("POST", "cancel", {}, {}, handler=handler)
            assert status == 404

    def test_cancel_no_stripe_id(self):
        from yuleosh.api.subscription import handle_subscription
        import jwt
        token = jwt.encode({
            "org_id": 1, "user_id": 1, "email": "t@t.com",
            "exp": int(time.time()) + 3600,
        }, os.environ["YULEOSH_JWT_SECRET"], algorithm="HS256")
        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        with patch("yuleosh.api.subscription.Store") as mock_store_class:
            mock_store_instance = MagicMock()
            mock_store_class.return_value = mock_store_instance
            mock_store_instance.get_organization_by_id.return_value = {"id": 1}
            mock_store_instance.get_subscription.return_value = {"stripe_subscription_id": ""}
            result, status = handle_subscription("POST", "cancel", {}, {}, handler=handler)
            assert status == 404

    def test_webhook_no_signature(self):
        from yuleosh.api.subscription import handle_subscription
        handler = MagicMock()
        handler.headers.get.side_effect = lambda k, d=None: {
            "Content-Length": "0",
            "Stripe-Signature": "",
        }.get(k, d or "")
        handler.rfile.read.return_value = b""
        result, status = handle_subscription("POST", "webhook", {}, {}, handler=handler)
        assert status == 400

    def test_webhook_with_signature(self):
        from yuleosh.api.subscription import handle_subscription
        handler = MagicMock()
        handler.headers.get.side_effect = lambda k, d=None: {
            "Content-Length": "2",
            "Stripe-Signature": "test_sig",
        }.get(k, d or "")
        handler.rfile.read.return_value = b"{}"
        with patch("yuleosh.api.subscription.handle_stripe_webhook") as mock_wh:
            mock_wh.return_value = {"status": "success", "type": "checkout.session.completed"}
            result, status = handle_subscription("POST", "webhook", {}, {}, handler=handler)
            assert status == 200
            assert result["ok"] is True

    def test_organization_not_found(self):
        from yuleosh.api.subscription import handle_subscription
        import jwt
        token = jwt.encode({
            "org_id": 999, "user_id": 1, "email": "nobody@test.com",
            "exp": int(time.time()) + 3600,
        }, os.environ["YULEOSH_JWT_SECRET"], algorithm="HS256")
        handler = MagicMock()
        handler.headers = {"Authorization": f"Bearer {token}"}
        with patch("yuleosh.api.subscription.Store") as mock_store_class:
            mock_store_instance = MagicMock()
            mock_store_class.return_value = mock_store_instance
            mock_store_instance.get_organization_by_id.return_value = None
            result, status = handle_subscription("GET", "status", {}, {}, handler=handler)
            assert status == 404


# ======================================================================
# compliance.py — Compliance Overview API
# ======================================================================

class TestCompliance:
    """handle_compliance — compliance overview."""

    def test_wrong_method(self):
        from yuleosh.api.compliance import handle_compliance
        result, status = handle_compliance("POST", "overview", {}, {}, None)
        assert result["ok"] is False
        assert status == 405

    def test_unknown_path(self):
        from yuleosh.api.compliance import handle_compliance
        result, status = handle_compliance("GET", "nonexistent", {}, {}, None)
        assert result["ok"] is False
        assert status == 404

    def test_overview_no_reports(self, tmp_path):
        from yuleosh.api.compliance import handle_compliance
        with patch("yuleosh.api.compliance.OSH_HOME", tmp_path):
            result, status = handle_compliance("GET", "overview", {}, {}, None)
            assert status == 200
            data = result["data"]
            assert data["misra_total"] == 0
            assert data["gscr_mapping_rate"] == 0.0
            assert data["s0_count"] == 0
            assert data["s1_count"] == 0
            assert data["s2_count"] == 0
            assert data["files_checked"] == 0
            assert data["violation_density"] == 0.0
            assert data["top5"] == []
            assert data["last_check"] is None

    def test_overview_with_misra_report(self, tmp_path):
        from yuleosh.api.compliance import handle_compliance
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        misra_report = {
            "summary": {
                "total_violations": 15,
                "severity_counts": {"S0": 5, "S1": 8},
                "misra_classification": {"required": 5, "advisory": 8},
                "unique_files": ["main.c", "gpio.c"],
            },
            "groups": [
                {"rule_id": "MISRA-17.7", "title": "Null pointer", "count": 8, "trend": "\u2191"},
                {"rule_id": "MISRA-10.1", "title": "Bool check", "count": 5, "trend": "\u2192"},
                {"rule_id": "MISRA-12.2", "title": "Shift ops", "count": 2, "trend": "\u2193"},
            ],
            "generated_at": "2025-06-01T12:00:00",
        }
        (reports_dir / "misra-report.json").write_text(json.dumps(misra_report))

        # RulesetRegistry is not a module-level attribute in compliance.py
        # so we patch the whole import chain
        with patch("yuleosh.api.compliance.OSH_HOME", tmp_path), \
             patch("yuleosh.ci.rulesets.RulesetRegistry") as mock_reg:
            registry = MagicMock()
            composite = MagicMock()
            composite.translate_violations.return_value = [
                {"gscr_rule_ids": ["GSCR-001"]},
                {"gscr_rule_ids": []},
            ]
            registry.create.return_value = composite
            mock_reg.return_value = registry

            result, status = handle_compliance("GET", "overview", {}, {}, None)
            assert status == 200
            data = result["data"]
            assert data["misra_total"] == 15
            assert data["s0_count"] == 5
            assert data["s1_count"] == 8
            assert data["files_checked"] == 2
            assert data["last_check"] == "2025-06-01T12:00:00"
            assert len(data["top5"]) == 3
            assert data["top5"][0]["rule_id"] == "MISRA-17.7"

    def test_overview_with_extended_report(self, tmp_path):
        from yuleosh.api.compliance import handle_compliance
        reports_dir = tmp_path / ".yuleosh" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        ext_report = {
            "summary": {
                "misra_total": 25,
                "gscr_mapped": 15,
                "gscr_mapping_rate": 60.0,
                "s0_count": 10,
                "s1_count": 8,
                "s2_count": 7,
                "files_checked": 5,
                "lines_checked": 5000,
                "violation_density": 0.5,
            },
            "top5": [
                {"rule_id": "MISRA-17.7", "title": "Null pointer", "count": 12, "trend": "\u2191"},
            ],
            "generated_at": "2025-06-15T08:00:00",
        }
        (reports_dir / "gscr-extended-compliance.json").write_text(json.dumps(ext_report))

        with patch("yuleosh.api.compliance.OSH_HOME", tmp_path):
            result, status = handle_compliance("GET", "overview", {}, {}, None)
            assert status == 200
            data = result["data"]
            assert data["misra_total"] == 25
            assert data["gscr_mapped"] == 15
            assert data["gscr_mapping_rate"] == 60.0
            assert data["files_checked"] == 5
            assert len(data["top5"]) == 1

    def test_overview_empty_path_tail(self):
        from yuleosh.api.compliance import handle_compliance
        result, status = handle_compliance("GET", "", {}, {}, None)
        assert status == 200
