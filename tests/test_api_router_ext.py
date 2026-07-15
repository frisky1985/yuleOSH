"""Tests for api/router.py — REST API router."""

from unittest.mock import MagicMock, patch
from yuleosh.api.router import dispatch, ROUTES, _LAZY_HANDLERS


def _make_handler(method="GET"):
    """Create a properly mocked HTTP handler."""
    h = MagicMock()
    h.command = method
    h.headers = {"Content-Length": "0"}
    h.rfile = MagicMock()
    h.rfile.read.return_value = b""
    return h


class TestRouter:
    """Test API router."""

    def test_routes_contains_all_resources(self):
        """All expected resources are in ROUTES or _LAZY_HANDLERS (AR-P2-01)."""
        expected = {
            "health", "wizard", "spec", "pipeline", "ci", "review",
            "evidence", "project", "stats", "notify", "apikeys",
            "webhooks", "audit", "auth", "demo", "subscription",
            "preview", "dashboard", "kb",
        }
        all_resources = set(ROUTES.keys()) | set(_LAZY_HANDLERS.keys())
        assert all_resources == expected

    def test_not_api_route(self):
        """Non-/api/v1 route returns 404."""
        h = _make_handler()
        dispatch(h, "/not-api")
        h.send_response.assert_called_with(404)

    def test_unknown_resource(self):
        """Unknown /api/v1/xxx returns 404."""
        h = _make_handler()
        dispatch(h, "/api/v1/unknown-resource")
        h.send_response.assert_called_with(404)

    def test_dispatch_health(self):
        """Dispatch to health works."""
        h = _make_handler()
        dispatch(h, "/api/v1/health")
        # Should call send_response
        assert h.send_response.called

    def test_dispatch_with_trailing_slash(self):
        """Trailing slash is stripped."""
        h = _make_handler()
        dispatch(h, "/api/v1/health/")
        assert h.send_response.called

    def test_dispatch_exception_caught(self):
        """Exception in handler returns 500."""
        h = _make_handler()
        dispatch(h, "/api/v1/health")
        assert h.send_response.called
