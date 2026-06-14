"""Focused coverage for ui/server.py — test core HTTP handler helpers."""
import os, sys, json, io
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestUiServerDeep:
    def test_import_handlers(self):
        from yuleosh.ui.server import (
            OSHHandler, main,
            _send_gzipped_json, _send_security_headers,
            _compute_etag, _format_http_datetime, _parse_http_datetime
        )
        assert hasattr(OSHHandler, "do_GET") or hasattr(OSHHandler, "do_POST")

    def test_send_gzipped_json(self):
        from yuleosh.ui.server import _send_gzipped_json
        handler = MagicMock()
        # Make wfile.write work
        handler.wfile = io.BytesIO()
        handler.wfile.write = lambda x: None
        result = _send_gzipped_json(handler, {"msg": "hello"}, 200)
        # Should not raise
        assert result is None

    def test_compute_etag(self):
        from yuleosh.ui.server import _compute_etag
        etag1 = _compute_etag(b"hello")
        etag2 = _compute_etag(b"hello")
        etag3 = _compute_etag(b"world")
        assert etag1 == etag2
        assert etag1 != etag3

    def test_format_parse_roundtrip(self):
        from yuleosh.ui.server import _format_http_datetime, _parse_http_datetime
        formatted = _format_http_datetime(1000000.0)
        parsed = _parse_http_datetime(formatted)
        assert abs(parsed - 1000000.0) < 2.0

    def test_send_security_headers(self):
        from yuleosh.ui.server import _send_security_headers
        handler = MagicMock()
        _send_security_headers(handler)
        assert handler.send_header.call_count >= 5
