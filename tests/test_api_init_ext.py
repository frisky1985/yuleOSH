"""Tests for api/__init__.py — Shared helpers and constants."""

from yuleosh.api import json_ok, json_error, read_body, OSH_HOME


class TestApiInit:
    """Test API init helpers."""

    def test_json_ok(self):
        result, code = json_ok({"key": "value"})
        assert result == {"ok": True, "data": {"key": "value"}}
        assert code == 200

    def test_json_ok_none(self):
        result, code = json_ok()
        assert result == {"ok": True, "data": None}
        assert code == 200

    def test_json_error_default(self):
        result, code = json_error("Bad request")
        assert result == {"ok": False, "error": "Bad request"}
        assert code == 400

    def test_json_error_custom_status(self):
        result, code = json_error("Not found", 404)
        assert result == {"ok": False, "error": "Not found"}
        assert code == 404

    def test_read_body_empty(self):
        class MockHandler:
            headers = {"Content-Length": "0"}
        result = read_body(MockHandler())
        assert result == {}

    def test_read_body_json(self):
        class MockHandler:
            headers = {"Content-Length": "15"}
            rfile = type("RFile", (), {"read": lambda self, n: b'{"key":"val"}'})()

        result = read_body(MockHandler())
        assert result == {"key": "val"}

    def test_read_body_query_string(self):
        class MockHandler:
            headers = {"Content-Length": "14"}
            rfile = type("RFile", (), {"read": lambda self, n: b"key=val&a=b"})()
        result = read_body(MockHandler())
        assert result["key"] == "val"
        assert result["a"] == "b"

    def test_osh_home_str(self):
        assert isinstance(OSH_HOME, str)
        assert len(OSH_HOME) > 0
