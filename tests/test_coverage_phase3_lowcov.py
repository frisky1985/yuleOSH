"""Phase 3 coverage boost — handler_helpers / project_routes / page_routes.

Milestone: 85% → 90%（2026-08-10 接力）。
Target modules（低覆盖大户）:
  - src/yuleosh/ui/routes/handler_helpers.py  (~46%)
  - src/yuleosh/ui/routes/project_routes.py   (~23%)
  - src/yuleosh/ui/routes/page_routes.py      (~55%)

策略：mock handler 直测 dispatch 分支 + TenantStore 直测项目 CRUD。
"""

from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest import mock

import pytest

# ── Mock handler factory ──────────────────────────────────────────────

def _make_handler(path="/", method="GET", headers=None, body=b""):
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
    handler._check_auth = mock.MagicMock(return_value=True)
    handler._request_start_time = 100.0
    handler._get_client_ip = mock.MagicMock(return_value="127.0.0.1")
    handler._response_status = 200
    return handler


# =====================================================================
# handler_helpers.py
# =====================================================================

class TestRateLimitCheck:
    def test_allowed_returns_true(self):
        from yuleosh.ui.routes.handler_helpers import rate_limit_check
        handler = _make_handler()
        with mock.patch("yuleosh.ui.server.check_rate_limit", return_value=(True, 0)) as m:
            assert rate_limit_check(handler) is True
        m.assert_called_once()

    def test_denied_sends_429(self):
        from yuleosh.ui.routes.handler_helpers import rate_limit_check
        handler = _make_handler()
        with mock.patch("yuleosh.ui.server.check_rate_limit", return_value=(False, 42)):
            assert rate_limit_check(handler) is False
        handler.send_response.assert_called_with(429)
        handler.send_header.assert_any_call("Retry-After", "42")
        handler.send_header.assert_any_call("X-RateLimit-Remaining", "0")
        body = handler.wfile.getvalue()
        assert b"Rate limit exceeded" in body


class TestSendAuthDenied:
    def test_api_path_gets_401_json(self):
        from yuleosh.ui.routes.handler_helpers import _send_auth_denied
        handler = _make_handler(path="/api/evidence")
        handler._json_response = mock.MagicMock()
        _send_auth_denied(handler)
        handler._json_response.assert_called_once()
        args = handler._json_response.call_args[0]
        assert args[0]["ok"] is False
        assert args[1] == 401

    def test_page_path_gets_login_page(self):
        from yuleosh.ui.routes.handler_helpers import _send_auth_denied
        handler = _make_handler(path="/dashboard")
        handler._serve_page = mock.MagicMock()
        _send_auth_denied(handler)
        handler._serve_page.assert_called_once_with("login.html", {"msg": ""})


class TestHandleGet:
    def test_api_v1_dispatch_delegates(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/v1/pipeline/checkpoint")
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=True) as m:
            handle_get(handler)
        m.assert_called_once()

    def test_health_endpoint(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/health")
        handler._json_response = mock.MagicMock()
        handler._get_health = mock.MagicMock(return_value={"ok": True})
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._json_response.assert_called_once_with({"ok": True})

    def test_health_page(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/health")
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._serve_page.assert_called_once_with("health.html", {})

    @pytest.mark.parametrize("path,api_name", [
        ("/api/auth/session", "session"),
        ("/api/auth/logout", "logout"),
        ("/api/project/list", "project_list"),
        ("/api/org/info", "org_info"),
    ])
    def test_tenant_api_routes(self, path, api_name):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path=path)
        handler._handle_api = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._handle_api.assert_called_once_with(api_name)

    @pytest.mark.parametrize("path,page,ctx", [
        ("/welcome", "welcome.html", {}),
        ("/login", "login.html", {"msg": ""}),
        ("/org/setup", "org-setup.html", {}),
        ("/project/select", "project-select.html", {}),
    ])
    def test_public_pages(self, path, page, ctx):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path=path)
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._serve_page.assert_called_once_with(page, ctx)

    def test_register_redirects_to_login(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/register")
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler.send_response.assert_called_with(302)
        handler.send_header.assert_any_call("Location", "/login")

    def test_root_wizard_not_completed_redirects(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/")
        mock_store = mock.MagicMock()
        mock_row = mock.MagicMock()
        mock_row.__getitem__ = mock.MagicMock(return_value="0")
        mock_store.conn.execute.return_value.fetchone.return_value = mock_row
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.server.Store", return_value=mock_store):
            handle_get(handler)
        handler.send_response.assert_called_with(302)
        handler.send_header.assert_any_call("Location", "/welcome")

    def test_root_wizard_completed_serves_marketing(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/")
        mock_store = mock.MagicMock()
        mock_row = mock.MagicMock()
        mock_row.__getitem__ = mock.MagicMock(return_value="1")
        mock_store.conn.execute.return_value.fetchone.return_value = mock_row
        handler._serve_file = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.server.Store", return_value=mock_store):
            handle_get(handler)
        handler._serve_file.assert_called_once()
        assert "marketing" in str(handler._serve_file.call_args[0][0])

    def test_root_store_exception_falls_back(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/")
        handler._serve_file = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.server.Store", side_effect=RuntimeError("boom")):
            handle_get(handler)
        handler._serve_file.assert_called_once()

    @pytest.mark.parametrize("path,filename", [
        ("/pricing", "pricing.html"),
        ("/en", "en/index.html"),
        ("/en/index.html", "en/index.html"),
        ("/en/pricing", "en/pricing.html"),
        ("/dashboard", "dashboard-v5.html"),
        ("/onboarding", "onboarding.html"),
        ("/pipeline-flow", "pipeline-flow.html"),
        ("/pipeline-board", "pipeline-board.html"),
        ("/demo", "demo.html"),
    ])
    def test_marketing_and_pages(self, path, filename):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path=path)
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._serve_file = mock.MagicMock()
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        if filename.endswith(".html") and "pages" not in str(handler._serve_file.call_args):
            # dashboard/onboarding/demo 走 _serve_page
            if filename in ("dashboard-v5.html", "onboarding.html", "demo.html"):
                handler._serve_page.assert_called_once()
            else:
                handler._serve_file.assert_called_once()
                assert str(handler._serve_file.call_args[0][0]).endswith(filename)

    def test_apikeys_page(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/apikeys")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._serve_page.assert_called_once_with("apikeys.html", {})

    @pytest.mark.parametrize("path,getter", [
        ("/api/status", "_get_status"),
        ("/api/evidence", "_list_evidence"),
        ("/api/reviews", "_get_reviews"),
        ("/api/ci", "_get_ci_results"),
    ])
    def test_legacy_api_json(self, path, getter):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path=path)
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        # spec=BaseHTTPRequestHandler 限制未知属性 → 显式设置
        setattr(handler, getter, mock.MagicMock(return_value={"data": 1}))
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._json_response.assert_called_once()
        assert handler._json_response.call_args[0][0] == {"data": 1}

    def test_pipeline_status_route(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/v1/pipeline/status/job-1")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_pipeline_status",
                        return_value={"ok": True, "job": {"job_id": "job-1"}}):
            handle_get(handler)
        handler._json_response.assert_called_once()

    @pytest.mark.parametrize("path", [
        "/api/v1/pipeline/runs",
        "/api/v1/pipeline/stats",
        "/api/v1/pipeline/yuleasr-status",
        "/api/v1/pipeline/checkpoint",
    ])
    def test_pipeline_other_routes(self, path):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path=path)
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_pipeline_runs",
                        return_value={"ok": True}), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_pipeline_stats",
                        return_value={"ok": True}), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_yuleasr_status",
                        return_value={"ok": True}), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_pipeline_checkpoint",
                        return_value={"ok": True}):
            handle_get(handler)
        handler._json_response.assert_called_once()

    def test_pipeline_validate(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/v1/pipeline/validate")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.pipeline.config_validator.validate_pipeline_config",
                        return_value={"valid": True}):
            handle_get(handler)
        handler._json_response.assert_called_once()
        assert handler._json_response.call_args[0][0]["ok"] is True

    def test_loops_summary(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/loops/summary")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.api.loops.get_all_loops_data", return_value={"loops": []}):
            handle_get(handler)
        handler._json_response.assert_called_once_with({"loops": []})

    def test_kanban_page(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/kanban")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._serve_file = mock.MagicMock()
        handler._serve_static = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("pathlib.Path.exists", return_value=True):
            handle_get(handler)
        assert handler._serve_file.call_count >= 1 or handler._serve_static.call_count >= 1

    def test_loops_detail_data(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/loops/7/data")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.api.loops.get_loop_data", return_value={"loop": {"id": 7}}):
            handle_get(handler)
        handler._json_response.assert_called_once()

    def test_loops_detail_bad_id(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/api/loops/abc/data")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.api.loops.get_loop_data", return_value=None):
            handle_get(handler)
        handler._json_response.assert_called_once()

    def test_unknown_path_404(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/no/such/page")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._serve_page.assert_called_once_with("404.html", {})

    def test_auth_denied_when_unauthenticated(self):
        from yuleosh.ui.routes.handler_helpers import handle_get
        handler = _make_handler(path="/dashboard")
        handler._check_auth = mock.MagicMock(return_value=False)
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_get(handler)
        handler._serve_page.assert_called_once_with("login.html", {"msg": ""})


class TestHandlePost:
    def test_api_v1_dispatch_delegates(self):
        from yuleosh.ui.routes.handler_helpers import handle_post
        handler = _make_handler(path="/api/v1/pipeline/trigger", method="POST")
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=True) as m:
            handle_post(handler)
        m.assert_called_once()

    @pytest.mark.parametrize("path,api_name", [
        ("/_auth/login", "_handle_login"),
        ("/api/auth/signin", "signin"),
        ("/api/auth/refresh", "refresh"),
        ("/api/org/create", "org_create"),
        ("/api/project/create", "project_create"),
        ("/api/auth/logout", "logout"),
    ])
    def test_post_routes(self, path, api_name):
        from yuleosh.ui.routes.handler_helpers import handle_post
        handler = _make_handler(path=path, method="POST")
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            if api_name == "_handle_login":
                handler._handle_login = mock.MagicMock()
                handle_post(handler)
                handler._handle_login.assert_called_once()
            else:
                handler._handle_api = mock.MagicMock()
                handle_post(handler)
                handler._handle_api.assert_called_once_with(api_name)

    def test_pipeline_trigger(self):
        from yuleosh.ui.routes.handler_helpers import handle_post
        handler = _make_handler(path="/api/v1/pipeline/trigger", method="POST",
                                headers={"Content-Length": "2"}, body=b"{}")
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_pipeline_trigger",
                        return_value={"ok": True, "job_id": "j1"}):
            handle_post(handler)
        handler._json_response.assert_called_once_with({"ok": True, "job_id": "j1"})

    def test_yuleasr_notify(self):
        from yuleosh.ui.routes.handler_helpers import handle_post
        handler = _make_handler(path="/api/v1/pipeline/yuleasr-notify", method="POST",
                                headers={"Content-Length": "2"}, body=b"{}")
        handler._json_response = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False), \
             mock.patch("yuleosh.ui.routes.pipeline_routes.handle_yuleasr_notify",
                        return_value={"ok": True}):
            handle_post(handler)
        handler._json_response.assert_called_once_with({"ok": True})

    def test_post_unauthenticated_denied(self):
        from yuleosh.ui.routes.handler_helpers import handle_post
        handler = _make_handler(path="/some/post", method="POST")
        handler._check_auth = mock.MagicMock(return_value=False)
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_post(handler)
        handler._serve_page.assert_called_once_with("login.html", {"msg": ""})

    def test_post_unknown_404(self):
        from yuleosh.ui.routes.handler_helpers import handle_post
        handler = _make_handler(path="/some/post", method="POST")
        handler._check_auth = mock.MagicMock(return_value=True)
        handler._serve_page = mock.MagicMock()
        with mock.patch("yuleosh.ui.server.api_v1_dispatch", return_value=False):
            handle_post(handler)
        handler._serve_page.assert_called_once_with("404.html", {})


class TestHandleDeleteOptions:
    def test_delete_serves_404(self):
        from yuleosh.ui.routes.handler_helpers import handle_delete
        handler = _make_handler(path="/x", method="DELETE")
        handler._serve_page = mock.MagicMock()
        handle_delete(handler)
        handler._serve_page.assert_called_once_with("404.html", {})

    def test_options_preflight(self):
        from yuleosh.ui.routes.handler_helpers import handle_options
        handler = _make_handler(path="/api/x", method="OPTIONS")
        handle_options(handler)
        handler.send_response.assert_called_with(204)
        handler.send_header.assert_any_call(
            "Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        handler.send_header.assert_any_call(
            "Access-Control-Allow-Headers", "Content-Type, X-API-Key, Authorization")


class TestLogAudit:
    def test_skips_non_api(self):
        from yuleosh.ui.routes.handler_helpers import log_audit
        handler = _make_handler(path="/dashboard")
        with mock.patch("yuleosh.api.audit.log_request") as m:
            log_audit(handler)
        m.assert_not_called()

    def test_skips_api_v1(self):
        from yuleosh.ui.routes.handler_helpers import log_audit
        handler = _make_handler(path="/api/v1/pipeline/checkpoint")
        with mock.patch("yuleosh.api.audit.log_request") as m:
            log_audit(handler)
        m.assert_not_called()

    def test_logs_legacy_api(self):
        from yuleosh.ui.routes.handler_helpers import log_audit
        handler = _make_handler(path="/api/evidence")
        with mock.patch("yuleosh.api.audit.log_request") as m:
            log_audit(handler)
        m.assert_called_once()
        assert m.call_args.kwargs["path"] == "/api/evidence"

    def test_exception_suppressed(self):
        from yuleosh.ui.routes.handler_helpers import log_audit
        handler = _make_handler(path="/api/evidence")
        with mock.patch("yuleosh.api.audit.log_request", side_effect=RuntimeError("db down")):
            log_audit(handler)  # 不应抛异常


# =====================================================================
# page_routes.py（补 serve_page 缺口）
# =====================================================================

class TestServePage:
    def _handler(self, **kw):
        return _make_handler(**kw)

    def _pages_dir(self):
        """真实 pages 目录（serve_page 内部 _Path(__file__) 指向源码目录）。"""
        from yuleosh.ui.routes import page_routes
        return Path(page_routes.__file__).resolve().parent.parent / "pages"

    def test_page_missing_uses_404_fallback(self):
        from yuleosh.ui.routes import page_routes
        handler = self._handler()
        with mock.patch.object(page_routes, "_send_html_response") as m_send:
            page_routes.serve_page(handler, "does-not-exist.html", {})
            m_send.assert_called_once()
            assert m_send.call_args[0][2] == 404

    def test_page_missing_no_fallback_json(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes import page_routes
        handler = self._handler()
        # 404.html 一定存在于真实 pages；这里模拟 fallback 也不存在 → JSON error
        with mock.patch("pathlib.Path.exists", return_value=False), \
             mock.patch.object(page_routes, "_send_json_error") as m_json:
            page_routes.serve_page(handler, "missing.html", {})
            m_json.assert_called_once()

    def test_page_served_with_substitution(self):
        """真实页面文件 + 模板替换 → 200。"""
        from yuleosh.ui.routes import page_routes
        # 用 onboarding.html（真实存在、内容小）测 200 路径
        pages = self._pages_dir()
        assert (pages / "onboarding.html").exists()
        handler = self._handler()
        page_routes.serve_page(handler, "onboarding.html", {"unused": "x"})
        handler.send_response.assert_called_with(200)
        assert handler.wfile.getvalue()  # body 已写入

    def test_page_304_not_modified(self):
        from yuleosh.ui.routes import page_routes
        from yuleosh.ui.routes.helpers import _compute_etag
        page_file = self._pages_dir() / "onboarding.html"
        etag = _compute_etag(page_file.read_bytes())
        handler = self._handler(headers={"If-None-Match": etag})
        page_routes.serve_page(handler, "onboarding.html", {})
        handler.send_response.assert_called_with(304)

    def test_page_ims_304(self):
        from yuleosh.ui.routes import page_routes
        from yuleosh.ui.routes.helpers import _format_http_datetime
        page_file = self._pages_dir() / "onboarding.html"
        # If-Modified-Since 与 mtime 相差 < 2s → 304
        ims = _format_http_datetime(page_file.stat().st_mtime)
        handler = self._handler(headers={"If-Modified-Since": ims})
        page_routes.serve_page(handler, "onboarding.html", {})
        handler.send_response.assert_called_with(304)

    def test_serve_file_no_fallback_json(self, tmp_path):
        """serve_file 文件不存在且无 404.html → JSON error。"""
        from yuleosh.ui.routes import page_routes
        handler = self._handler()
        with mock.patch("pathlib.Path.exists", return_value=False), \
             mock.patch.object(page_routes, "_send_json_error") as m_json:
            page_routes.serve_file(handler, tmp_path / "nope.bin", "application/octet-stream")
            m_json.assert_called_once()


# =====================================================================
# project_routes.py（SAAS-3 项目 CRUD + Kanban）
# =====================================================================

class TestProjectHelpers:
    def test_get_token_bearer(self):
        from yuleosh.ui.routes.project_routes import _get_token
        h = _make_handler(headers={"Authorization": "Bearer abc123"})
        assert _get_token(h) == "abc123"

    def test_get_token_missing(self):
        from yuleosh.ui.routes.project_routes import _get_token
        h = _make_handler()
        assert _get_token(h) is None

    def test_get_token_non_bearer(self):
        from yuleosh.ui.routes.project_routes import _get_token
        h = _make_handler(headers={"Authorization": "Basic xyz"})
        assert _get_token(h) is None

    def test_require_auth_no_token(self):
        from yuleosh.ui.routes.project_routes import _require_auth
        h = _make_handler()
        assert _require_auth(h) is None

    def test_require_auth_with_token(self):
        from yuleosh.ui.routes.project_routes import _require_auth
        h = _make_handler(headers={"Authorization": "Bearer tok1"})
        with mock.patch("yuleosh.ui.routes.project_routes.get_session_user",
                        return_value={"user_id": 1, "org_slug": "acme"}):
            assert _require_auth(h) == {"user_id": 1, "org_slug": "acme"}

    def test_auth_error_missing_token(self):
        from yuleosh.ui.routes.project_routes import _auth_error
        h = _make_handler()
        resp, code = _auth_error(h)
        assert resp == {"error": "Authorization required"}
        assert code == 401

    def test_auth_error_invalid_session(self):
        from yuleosh.ui.routes.project_routes import _auth_error
        h = _make_handler(headers={"Authorization": "Bearer bad"})
        resp, code = _auth_error(h)
        assert resp == {"error": "Invalid session"}
        assert code == 401

    def test_get_tenant_slug_from_org_slug(self):
        from yuleosh.ui.routes.project_routes import _get_tenant_slug
        assert _get_tenant_slug({"org_slug": "my-org"}) == "my-org"

    def test_get_tenant_slug_fallback_org_id(self):
        from yuleosh.ui.routes.project_routes import _get_tenant_slug
        assert _get_tenant_slug({"org_id": 42}) == "42"

    def test_new_project_shape(self):
        from yuleosh.ui.routes.project_routes import _new_project
        p = _new_project("My Project", "desc", "a@b.com")
        assert p["slug"] == "my-project"
        assert p["name"] == "My Project"
        assert p["description"] == "desc"
        assert p["owner"] == "a@b.com"
        assert p["members"] == ["a@b.com"]
        assert p["status"] == "active"
        assert len(p["items"]) == 5  # 5 个 kanban 状态
        assert [i["status"] for i in p["items"]] == ["需求", "开发", "审查", "测试", "发布"]

    def test_new_project_slug_strips_special_chars(self):
        from yuleosh.ui.routes.project_routes import _new_project
        p = _new_project("My  Project!!!")
        assert p["slug"] == "my--project"  # 空格→连字符，特殊字符剔除


class TestProjectRoutes:
    def _auth_user(self, org_slug="acme", org_id=1, email="u@t.com"):
        return {"user_id": 7, "org_slug": org_slug, "org_id": org_id, "email": email}

    def _h(self, token: str | None = "Bearer tok"):
        return _make_handler(headers={"Authorization": token} if token else {})

    def test_dispatcher_method_not_allowed(self):
        from yuleosh.ui.routes.project_routes import handle_projects
        resp, code = handle_projects("DELETE", "", {}, {}, handler=None)
        assert code == 405
        assert resp == {"error": "Method not allowed"}

    def test_list_projects_auth_failure(self):
        from yuleosh.ui.routes.project_routes import handle_list_projects
        _, code = handle_list_projects("GET", "", {}, {}, handler=self._h(token=None))
        assert code == 401

    def test_list_projects_empty(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_list_projects
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.list_projects.return_value = []
            resp, code = handle_list_projects("GET", "", {}, {}, handler=self._h())
        assert code == 200
        assert resp == {"projects": []}

    def test_get_project_auth_failure(self):
        from yuleosh.ui.routes.project_routes import handle_get_project
        _, code = handle_get_project("GET", "proj", {}, {}, handler=self._h(token=None))
        assert code == 401

    def test_get_project_missing_slug(self):
        from yuleosh.ui.routes.project_routes import handle_get_project
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user):
            _, code = handle_get_project("GET", "", {}, {}, handler=self._h())
        assert code == 400

    def test_get_project_tenant_not_found(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_get_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get.return_value = None
            resp, code = handle_get_project("GET", "proj", {}, {}, handler=self._h())
        assert code == 404
        assert resp == {"error": "Tenant not found"}

    def test_get_project_not_found(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_get_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        tenant = mock.MagicMock()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get.return_value = tenant
            m_store.return_value.get_project.return_value = None
            resp, code = handle_get_project("GET", "proj", {}, {}, handler=self._h())
        assert code == 404
        assert resp == {"error": "Project not found"}

    def test_get_project_success(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_get_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        project = {"slug": "proj", "name": "Proj", "items": []}
        tenant = mock.MagicMock()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get.return_value = tenant
            m_store.return_value.get_project.return_value = project
            resp, code = handle_get_project("GET", "proj", {}, {}, handler=self._h())
        assert code == 200
        assert resp == {"project": project}

    def test_create_project_auth_failure(self):
        from yuleosh.ui.routes.project_routes import handle_create_project
        _, code = handle_create_project("POST", "", {}, {}, handler=self._h(token=None))
        assert code == 401

    def test_create_project_missing_name(self):
        from yuleosh.ui.routes.project_routes import handle_create_project
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user):
            resp, code = handle_create_project("POST", "", {"name": "  "}, {},
                                               handler=self._h())
        assert code == 400
        assert resp == {"error": "Project name is required"}

    def test_create_project_rbac_denied(self):
        from yuleosh.ui.routes.project_routes import handle_create_project
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=False):
            _, code = handle_create_project("POST", "", {"name": "X"}, {},
                                               handler=self._h())
        assert code == 403

    def test_create_project_tenant_not_found(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_create_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get.return_value = None
            _, code = handle_create_project("POST", "", {"name": "X"}, {},
                                               handler=self._h())
        assert code == 404

    def test_create_project_plan_limit(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_create_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        tenant = mock.MagicMock()
        tenant.limits = {"max_projects": 2}
        tenant.plan = "free"
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get.return_value = tenant
            m_store.return_value.list_projects.return_value = [{"slug": "a"}, {"slug": "b"}]
            resp, code = handle_create_project("POST", "", {"name": "X"}, {},
                                               handler=self._h())
        assert code == 403
        assert "Project limit reached" in resp["error"]

    def test_create_project_success(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_create_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        tenant = mock.MagicMock()
        tenant.limits = {"max_projects": 10}
        tenant.plan = "pro"
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get.return_value = tenant
            m_store.return_value.list_projects.return_value = []
            resp, code = handle_create_project("POST", "", {"name": "New Proj"}, {},
                                               handler=self._h())
        assert code == 201
        assert resp["project"]["name"] == "New Proj"
        m_store.return_value.save_project.assert_called_once()

    def test_update_project_auth_failure(self):
        from yuleosh.ui.routes.project_routes import handle_update_project
        _, code = handle_update_project("POST", "proj", {}, {}, handler=self._h(token=None))
        assert code == 401

    def test_update_project_missing_slug(self):
        from yuleosh.ui.routes.project_routes import handle_update_project
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user):
            _, code = handle_update_project("POST", "", {}, {}, handler=self._h())
        assert code == 400

    def test_update_project_rbac_denied(self):
        from yuleosh.ui.routes.project_routes import handle_update_project
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=False):
            _, code = handle_update_project("POST", "proj", {}, {}, handler=self._h())
        assert code == 403

    def test_update_project_not_found(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_update_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get_project.return_value = None
            resp, code = handle_update_project("POST", "proj", {}, {}, handler=self._h())
        assert code == 404
        assert resp == {"error": "Project not found"}

    def test_update_project_success(self, tmp_path, monkeypatch):
        from yuleosh.ui.routes.project_routes import handle_update_project
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        user = self._auth_user()
        project = {"slug": "proj", "name": "Old", "description": "d",
                   "items": [], "members": [], "status": "active"}
        with mock.patch("yuleosh.ui.routes.project_routes._require_auth",
                        return_value=user), \
             mock.patch("yuleosh.rbac.check_role", return_value=True), \
             mock.patch("yuleosh.ui.routes.project_routes.TenantStore") as m_store:
            m_store.return_value.get_project.return_value = project
            resp, code = handle_update_project(
                "POST", "proj",
                {"name": "New", "description": "d2", "items": [{"id": "x"}],
                 "members": ["u@t.com"], "status": "archived"},
                {}, handler=self._h())
        assert code == 200
        assert resp["project"]["name"] == "New"
        assert resp["project"]["status"] == "archived"
        assert resp["project"]["items"] == [{"id": "x"}]
        m_store.return_value.save_project.assert_called_once()
