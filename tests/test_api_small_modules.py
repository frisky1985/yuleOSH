#!/usr/bin/env python3
# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for small API modules: stats, review, project, wizard, middleware, pipeline.

Target: 80%+ statement coverage.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest


# ==================================================================
# api/stats.py
# ==================================================================


class TestApiStats:
    @mock.patch("yuleosh.api.stats.Store")
    def test_get_project_stats_basic(self, mock_store_cls):
        from yuleosh.api.stats import handle_stats

        # Configure mock store
        mock_store = mock.MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.get_usage_stats.return_value = {
            "total_projects": 5,
            "total_pipelines": 10,
            "total_ci_runs": 20,
            "pipeline_statuses": {"completed": 8, "failed": 2},
        }
        mock_conn = mock.MagicMock()
        mock_store.conn = mock_conn
        mock_cursor = mock.MagicMock()
        mock_conn.execute.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {"c": 15}

        result = handle_stats("GET", "overview", {}, {})
        assert result[1] == 200
        assert "data" in result[0]

    def test_stats_bad_method(self):
        from yuleosh.api.stats import handle_stats

        result = handle_stats("POST", "", {}, {})
        assert result[1] == 405


# ==================================================================
# api/review.py
# ==================================================================


class TestApiReview:
    def test_handle_review_unknown_action(self):
        from yuleosh.api.review import handle_review

        result = handle_review("GET", "unknown", {}, {})
        assert result[1] == 404

    @mock.patch("yuleosh.api.review._list_reviews")
    def test_handle_review_list(self, mock_list):
        from yuleosh.api.review import handle_review

        mock_list.return_value = ({"ok": True, "data": {"reviews": [], "count": 0}}, 200)
        result = handle_review("GET", "list", {}, {})
        assert result[1] == 200

    def test_handle_review_status_returns_404(self):
        from yuleosh.api.review import handle_review

        result = handle_review("GET", "status", {}, {})
        assert result[1] == 404  # 'status' is not a valid review sub-resource

    def test_get_review_results_no_dir(self, monkeypatch):
        from yuleosh.api.review import _list_reviews

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = _list_reviews()
        assert result[1] == 200
        assert result[0]["data"]["count"] == 0

    def test_get_review_results_with_reviews(self, monkeypatch):
        from yuleosh.api.review import _list_reviews

        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir) / ".osh" / "reviews" / "session-001"
            reviews_dir.mkdir(parents=True)
            (reviews_dir / "review-session.json").write_text(
                json.dumps({"task": "arch", "result": "pass"})
            )
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = _list_reviews()
        assert result[0]["data"]["count"] == 1
        assert result[0]["data"]["sessions"][0]["task"] == "arch"

    def test_get_review_list_with_reviews2(self, monkeypatch):
        from yuleosh.api.review import _list_reviews

        with tempfile.TemporaryDirectory() as tmpdir:
            reviews_dir = Path(tmpdir) / ".osh" / "reviews" / "magic-session"
            reviews_dir.mkdir(parents=True)
            (reviews_dir / "review-session.json").write_text(
                json.dumps({"result": "pass"})
            )
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = _list_reviews()
        assert "data" in result[0]
        assert result[0]["data"]["count"] == 1


# ==================================================================
# api/project.py
# ==================================================================


class TestApiProject:
    def test_handle_project_get(self):
        from yuleosh.api.project import handle_project

        result = handle_project("GET", "", {}, {})
        assert result[1] == 200
        assert "projects" in result[0]["data"]
        assert "count" in result[0]["data"]

    def test_handle_project_bad_method(self):
        from yuleosh.api.project import handle_project

        result = handle_project("DELETE", "", {}, {})
        assert result[1] == 405


# ==================================================================
# api/wizard.py
# ==================================================================


class TestApiWizard:
    @mock.patch("yuleosh.api.wizard.Store")
    def test_handle_wizard_complete(self, mock_store_cls):
        from yuleosh.api.wizard import handle_wizard

        mock_store = mock.MagicMock()
        mock_store_cls.return_value = mock_store

        result = handle_wizard("POST")
        assert result[1] == 200
        assert result[0]["data"]["completed"] is True

    def test_handle_wizard_bad_method(self):
        from yuleosh.api.wizard import handle_wizard

        result = handle_wizard("GET")
        assert result[1] == 405

    def test_handle_wizard_no_handler(self):
        from yuleosh.api.wizard import handle_wizard

        result = handle_wizard("POST")
        assert result[1] == 200


# ==================================================================
# api/middleware.py
# ==================================================================


class TestApiMiddleware:
    def test_middleware_importable(self):
        from yuleosh.api.middleware import (
            require_auth,
            _decode_token,
        )
        assert callable(require_auth)
        assert callable(_decode_token)

    def test_middleware_decode_token(self):
        from yuleosh.api.middleware import _decode_token, _JWT_SECRET, _JWT_ALGORITHM

        # Test with valid token
        import jwt
        payload = {"sub": "user-1", "org": 42}
        token = jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)
        result = _decode_token(token)
        assert result is not None
        assert result.get("sub") == "user-1"
        assert result.get("org") == 42

    def test_middleware_decode_bad_token(self):
        from yuleosh.api.middleware import _decode_token

        result = _decode_token("invalid-token")
        assert result is None


# ==================================================================
# api/pipeline.py
# ==================================================================


class TestApiPipeline:
    def test_handle_pipeline_unknown(self):
        from yuleosh.api.pipeline import handle_pipeline

        result = handle_pipeline("GET", "unknown", {}, {})
        assert result[1] == 404

    def test_handle_pipeline_list_no_dir(self, monkeypatch):
        from yuleosh.api.pipeline import handle_pipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("yuleosh.api.OSH_HOME", tmpdir)
            result = handle_pipeline("GET", "list", {}, {})
        assert result[1] == 200
        assert result[0]["data"]["count"] == 0

    def test_handle_pipeline_list_with_db_runs(self, monkeypatch):
        from yuleosh.api.pipeline import handle_pipeline

        result = handle_pipeline("GET", "list", {}, {})
        assert result[1] == 200
        assert "count" in result[0]["data"]

    def test_handle_pipeline_start_no_spec(self):
        from yuleosh.api.pipeline import handle_pipeline

        # No spec provided -> should return error
        result = handle_pipeline("POST", "", {}, {})
        assert result[1] == 400
        assert "error" in result[0] or "spec" in str(result[0])

    def test_handle_pipeline_status(self):
        from yuleosh.api.pipeline import handle_pipeline

        result = handle_pipeline("GET", "status", {}, {})
        assert result[1] == 200
