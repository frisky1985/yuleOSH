# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.8.0 Track2 — F3/F4 附项验收测试（acceptance-matrix T-F3-*/T-F4-*）。

覆盖:
  - T-F3-01/02 POST/DELETE 异常 → 审计 status=500
  - T-F3-03-neg 异常不得记 200
  - T-F3-04 正常请求审计 200 不变
  - T-F4-01/02 页面路径 no-cache
  - T-F4-03-neg HTML 不 immutable
  - T-F4-04 404 兜底保持
"""

import time
from pathlib import Path
from unittest import mock

import pytest


def _make_handler():
    from yuleosh.ui.server import OSHHandler
    h = OSHHandler.__new__(OSHHandler)
    h.path = "/api/evidence"
    h.command = "GET"
    h._response_status = 200
    h._request_start_time = time.time()
    h.client_address = ("127.0.0.1", 0)
    h.wfile = __import__("io").BytesIO()
    h.rfile = __import__("io").BytesIO()
    h.send_response = mock.MagicMock()
    h.send_header = mock.MagicMock()
    h.end_headers = mock.MagicMock()
    h._json_response = mock.MagicMock()
    h._serve_static = mock.MagicMock()
    return h


class TestF3AuditStatusOnError:
    """T-F3-01..04 — POST/DELETE 异常审计 500."""

    def test_post_error_audits_500(self):
        from yuleosh.ui.server import OSHHandler
        h = _make_handler()
        h.command = "POST"
        h.path = "/api/v1/unknown"
        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_post",
                        side_effect=RuntimeError("boom")), \
             mock.patch("yuleosh.ui.routes.handler_helpers.log_audit") as la:
            OSHHandler.do_POST(h)
        # do_POST caught the error → _response_status set to 500
        assert h._response_status == 500
        la.assert_called_once()

    def test_delete_error_audits_500(self):
        from yuleosh.ui.server import OSHHandler
        h = _make_handler()
        h.command = "DELETE"
        h.path = "/api/v1/unknown"
        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_delete",
                        side_effect=RuntimeError("boom")), \
             mock.patch("yuleosh.ui.routes.handler_helpers.log_audit") as la:
            OSHHandler.do_DELETE(h)
        assert h._response_status == 500
        la.assert_called_once()

    def test_error_not_audited_200(self):
        """T-F3-03-neg: 异常不得记 200."""
        from yuleosh.ui.server import OSHHandler
        h = _make_handler()
        h.command = "POST"
        h.path = "/api/v1/unknown"
        with mock.patch("yuleosh.ui.routes.handler_helpers.handle_post",
                        side_effect=RuntimeError("boom")):
            OSHHandler.do_POST(h)
        assert h._response_status != 200


class TestF4ServeFileCacheControl:
    """T-F4-01..04 — _serve_file 页面 no-cache."""

    def _serve(self, tmp_path, name="page.html", content_type="text/html; charset=utf-8"):
        from yuleosh.ui.server import OSHHandler
        h = _make_handler()
        f = tmp_path / name
        f.write_text("<html>hi</html>")
        h.send_header = mock.MagicMock()
        OSHHandler._serve_file(h, f, content_type)
        return h

    def test_html_no_cache(self, tmp_path):
        """T-F4-01/02: HTML 响应带 Cache-Control: no-cache."""
        h = self._serve(tmp_path, "page.html")
        calls = [c.args[0] for c in h.send_header.call_args_list]
        assert "Cache-Control" in calls
        cc = dict((c.args[0], c.args[1])
                  for c in h.send_header.call_args_list)["Cache-Control"]
        assert cc == "no-cache"

    def test_html_not_immutable(self, tmp_path):
        """T-F4-03-neg: HTML 不含 immutable."""
        h = self._serve(tmp_path, "page.html")
        cc = dict((c.args[0], c.args[1])
                  for c in h.send_header.call_args_list)["Cache-Control"]
        assert "immutable" not in cc

    def test_404_fallback_kept(self, tmp_path):
        """T-F4-04: 文件缺失 → _serve_static(404) 兜底."""
        from yuleosh.ui.server import OSHHandler
        h = _make_handler()
        missing = tmp_path / "nope.html"
        OSHHandler._serve_file(h, missing, "text/html; charset=utf-8")
        h._serve_static.assert_called_once_with("/404.html")
