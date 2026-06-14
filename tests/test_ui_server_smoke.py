"""Smoke tests for yuleosh.ui.server — HTTP server.
Checks import, class instantiation, and basic helpers.
All external calls mocked.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ======================================================================
# yuleosh.ui.server — basic import and class checks
# ======================================================================

class TestUiServer:
    def test_import_class(self):
        from yuleosh.ui.server import OSHHandler
        assert OSHHandler is not None
        assert issubclass(OSHHandler, object)

    def test_main_exists(self):
        from yuleosh.ui.server import main
        assert callable(main)

    def test_security_headers(self):
        from yuleosh.ui.server import _send_security_headers
        handler = MagicMock()
        _send_security_headers(handler)
        assert handler.send_header.call_count >= 5

    def test_compute_etag(self):
        from yuleosh.ui.server import _compute_etag
        etag = _compute_etag(b"hello world")
        assert isinstance(etag, str)
        assert len(etag) > 0

    def test_format_http_datetime(self):
        from yuleosh.ui.server import _format_http_datetime
        result = _format_http_datetime(1000000.0)
        assert "GMT" in result

    def test_parse_http_datetime(self):
        from yuleosh.ui.server import _parse_http_datetime
        # Invalid date should return 0
        result = _parse_http_datetime("invalid")
        assert result == 0.0
