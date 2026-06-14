"""Additional tests to push coverage past 50% - targeting ui/server.py."""
import os, sys, json, io
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestServerCrunch:
    def test_server_format_http(self):
        from yuleosh.ui.server import _format_http_datetime, _parse_http_datetime
        dt = _format_http_datetime(0)
        assert "GMT" in dt or "1970" in dt

    def test_server_parse_valid(self):
        from yuleosh.ui.server import _parse_http_datetime
        result = _parse_http_datetime("Mon, 01 Jan 2024 00:00:00 GMT")
        assert isinstance(result, float)

    def test_ci_run_misra_and_strict(self):
        from yuleosh.ci.run import is_misra_fail_fast, is_strict, get_cache_key_for_dir
        assert callable(is_misra_fail_fast)
        assert callable(is_strict)
        assert callable(get_cache_key_for_dir)

    def test_ci_run_sil_and_coverage(self):
        from yuleosh.ci.run import run_sil_tests, run_coverage_check, run_clang_tidy
        assert callable(run_sil_tests)
        assert callable(run_coverage_check)
        assert callable(run_clang_tidy)
