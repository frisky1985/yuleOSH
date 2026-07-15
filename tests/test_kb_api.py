# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for kb API handler — direct handler calls, no HTTP server."""

import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("OSH_HOME", str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def kb_db_path():
    """Use temp KB database to avoid cross-test pollution."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    old_env = os.environ.get("YULEOSH_KB_DB")
    os.environ["YULEOSH_KB_DB"] = db_path
    yield db_path
    os.environ.pop("YULEOSH_KB_DB", None)
    if old_env:
        os.environ["YULEOSH_KB_DB"] = old_env
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def patch_store():
    """Patch KbStore to use temp DB from env."""
    from yuleosh.kb import store as kb_store
    orig_init = kb_store.KbStore.__init__

    def patched_init(self, db_path=None):
        db_path = os.environ.get("YULEOSH_KB_DB", db_path)
        orig_init(self, db_path)

    with patch.object(kb_store.KbStore, "__init__", patched_init):
        yield


@pytest.fixture
def handler():
    from yuleosh.api.kb import handle_kb
    return handle_kb


class TestKbArticlesAPI:
    """Test /api/v1/kb/articles endpoints."""

    def test_list_articles_empty(self, handler, patch_store):
        """GET articles returns empty list."""
        result, status = handler("GET", "articles", {}, {})
        assert status == 200
        assert result["ok"] is True
        assert result["data"]["items"] == []
        assert result["data"]["total"] == 0

    def test_create_article(self, handler, patch_store):
        """POST articles creates an article."""
        body = {"title": "Test Article", "content": "# Hello", "source": "manual", "tags": "test"}
        result, status = handler("POST", "articles", body, {})
        assert status == 200
        assert result["ok"] is True
        assert result["data"]["title"] == "Test Article"
        assert result["data"]["id"] is not None

    def test_create_article_missing_title(self, handler, patch_store):
        """POST articles without title returns error."""
        result, status = handler("POST", "articles", {"content": "No title"}, {})
        assert status == 400
        assert result["ok"] is False
        assert "title" in result["error"].lower()

    def test_get_article_by_id(self, handler, patch_store):
        """GET articles/:id returns the article."""
        create_result, _ = handler("POST", "articles", {"title": "My Article", "content": "Body"}, {})
        article_id = create_result["data"]["id"]
        result, status = handler("GET", f"articles/{article_id}", {}, {})
        assert status == 200
        assert result["data"]["id"] == article_id
        assert result["data"]["title"] == "My Article"

    def test_get_article_not_found(self, handler, patch_store):
        """GET articles/:id with non-existent id returns 404."""
        result, status = handler("GET", "articles/999", {}, {})
        assert status == 404
        assert result["ok"] is False

    def test_list_articles_with_search(self, handler, patch_store):
        """GET articles?search=... filters results."""
        handler("POST", "articles", {"title": "Memory leak fix", "content": "Free memory"}, {})
        handler("POST", "articles", {"title": "Null pointer", "content": "Check ptr"}, {})
        result, status = handler("GET", "articles", {}, {"search": ["memory"]})
        assert result["data"]["total"] == 1

    def test_update_article(self, handler, patch_store):
        """PUT articles/:id updates the article."""
        create_result, _ = handler("POST", "articles", {"title": "Old", "content": "Old content"}, {})
        a_id = create_result["data"]["id"]
        result, status = handler("PUT", f"articles/{a_id}", {"title": "New Title"}, {})
        assert status == 200
        assert result["data"]["title"] == "New Title"
        assert result["data"]["content"] == "Old content"  # unchanged

    def test_update_article_not_found(self, handler, patch_store):
        """PUT articles/:id on non-existent returns 404."""
        result, status = handler("PUT", "articles/999", {"title": "Nope"}, {})
        assert status == 404

    def test_delete_article(self, handler, patch_store):
        """DELETE articles/:id deletes the article."""
        create_result, _ = handler("POST", "articles", {"title": "Delete me"}, {})
        a_id = create_result["data"]["id"]
        result, status = handler("DELETE", f"articles/{a_id}", {}, {})
        assert status == 200
        assert result["data"]["deleted"] is True

        # Verify it's gone
        get_result, get_status = handler("GET", f"articles/{a_id}", {}, {})
        assert get_status == 404

    def test_delete_article_not_found(self, handler, patch_store):
        """DELETE articles/:id on non-existent returns 404."""
        result, status = handler("DELETE", "articles/999", {}, {})
        assert status == 404


class TestKbLessonsAPI:
    """Test /api/v1/kb/lessons endpoints."""

    def test_list_lessons_empty(self, handler, patch_store):
        """GET lessons returns empty list."""
        result, status = handler("GET", "lessons", {}, {})
        assert status == 200
        assert result["data"]["items"] == []

    def test_create_lesson(self, handler, patch_store):
        """POST lessons creates a lesson."""
        body = {
            "title": "Null check lesson",
            "problem": "Dereferenced null ptr",
            "solution": "Add null check",
            "severity": "high",
        }
        result, status = handler("POST", "lessons", body, {})
        assert status == 200
        assert result["data"]["title"] == "Null check lesson"
        assert result["data"]["severity"] == "high"

    def test_create_lesson_missing_title(self, handler, patch_store):
        """POST lessons without title returns error."""
        result, status = handler("POST", "lessons", {"problem": "Something"}, {})
        assert status == 400
        assert "title" in result["error"].lower()

    def test_list_lessons_filter_severity(self, handler, patch_store):
        """GET lessons?severity=... filters results."""
        handler("POST", "lessons", {"title": "L1", "severity": "high"}, {})
        handler("POST", "lessons", {"title": "L2", "severity": "low"}, {})
        result, status = handler("GET", "lessons", {}, {"severity": ["high"]})
        assert result["data"]["total"] == 1
        assert result["data"]["items"][0]["title"] == "L1"

    def test_list_lessons_invalid_severity(self, handler, patch_store):
        """GET lessons?severity=invalid returns error."""
        result, status = handler("GET", "lessons", {}, {"severity": ["invalid"]})
        assert status == 400
        assert "severity" in result["error"].lower()


class TestKbFmeaAPI:
    """Test /api/v1/kb/fmea endpoints."""

    def test_list_fmea_empty(self, handler, patch_store):
        """GET fmea returns empty list."""
        result, status = handler("GET", "fmea", {}, {})
        assert status == 200
        assert result["data"]["items"] == []

    def test_create_fmea(self, handler, patch_store):
        """POST fmea creates a FMEA entry."""
        body = {
            "item": "Brake Controller",
            "failure_mode": "Stuck high",
            "effect": "Brake stays on",
            "cause": "MOSFET short",
            "severity": 8,
            "occurence": 4,
            "detection": 3,
            "recommendation": "Add redundancy",
        }
        result, status = handler("POST", "fmea", body, {})
        assert status == 200
        assert result["data"]["item"] == "Brake Controller"
        assert result["data"]["rpn"] == 96

    def test_create_fmea_missing_item(self, handler, patch_store):
        """POST fmea without item returns error."""
        result, status = handler("POST", "fmea", {"failure_mode": "F"}, {})
        assert status == 400
        assert "item" in result["error"].lower()

    def test_create_fmea_missing_failure_mode(self, handler, patch_store):
        """POST fmea without failure_mode returns error."""
        result, status = handler("POST", "fmea", {"item": "X"}, {})
        assert status == 400
        assert "failure_mode" in result["error"].lower()

    def test_fmea_sorted_by_rpn(self, handler, patch_store):
        """GET fmea defaults to sort by RPN descending."""
        handler("POST", "fmea", {"item": "Low", "failure_mode": "F1", "severity": 1, "occurence": 1, "detection": 1}, {})
        handler("POST", "fmea", {"item": "High", "failure_mode": "F2", "severity": 10, "occurence": 10, "detection": 10}, {})
        result, status = handler("GET", "fmea", {}, {})
        assert result["data"]["items"][0]["item"] == "High"
        assert result["data"]["items"][1]["item"] == "Low"

    def test_unknown_kb_resource(self, handler, patch_store):
        """GET with unknown resource returns 404."""
        result, status = handler("GET", "unknown", {}, {})
        assert status == 404


class TestRouterIntegration:
    """Test that the router correctly dispatches to the KB handler."""

    def test_kb_route_registered(self):
        """KB handler is registered in router ROUTES."""
        from yuleosh.api.router import ROUTES
        assert "kb" in ROUTES
        from yuleosh.api.kb import handle_kb
        assert ROUTES["kb"] is handle_kb

    def test_router_dispatches_kb(self):
        """Router dispatches /api/v1/kb/articles to the right handler."""
        from yuleosh.api.router import dispatch
        from http.server import BaseHTTPRequestHandler
        from unittest.mock import MagicMock, PropertyMock

        mock_handler = MagicMock(spec=BaseHTTPRequestHandler)
        mock_handler.command = "GET"
        mock_handler.headers = {}

        # rfile needs to be a readable stream
        import io
        mock_handler.rfile = io.BytesIO(b"")
        mock_handler.wfile = io.BytesIO()

        dispatch(mock_handler, "/api/v1/kb/articles")

        # Should have sent a 200 response
        assert mock_handler.send_response.call_args[0][0] == 200
