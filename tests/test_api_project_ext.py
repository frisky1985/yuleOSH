"""Tests for api/project.py — Project CRUD endpoints."""

# @tests src/yuleosh/api/pipeline.py

import pytest
from unittest.mock import patch, MagicMock
from yuleosh.api.project import handle_project


class TestApiProject:
    """Test project endpoints."""

    @patch("yuleosh.store.Store")
    def test_list_projects(self, mock_store_cls):
        """GET /project lists all projects.

        A4 (v3.8.0): list goes through Store.list_projects (interface)."""
        mock_store = MagicMock()
        mock_store.list_projects.return_value = [
            {"name": "proj1", "created_at": "2025-01-01"}
        ]
        mock_store_cls.return_value = mock_store

        result, code = handle_project("GET", "", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["count"] == 1

    @patch("yuleosh.store.Store")
    def test_list_projects_explicit(self, mock_store_cls):
        """GET /project/list lists all projects."""
        mock_store = MagicMock()
        mock_store.list_projects.return_value = []
        mock_store_cls.return_value = mock_store

        result, code = handle_project("GET", "list", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200

    @patch("yuleosh.store.Store")
    def test_get_project(self, mock_store_cls):
        """GET /project/{name} returns specific project."""
        mock_store = MagicMock()
        mock_store.get_project.return_value = {
            "name": "myproj", "description": "desc"
        }
        mock_store_cls.return_value = mock_store

        result, code = handle_project("GET", "myproj", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["name"] == "myproj"

    @patch("yuleosh.store.Store")
    def test_get_project_not_found(self, mock_store_cls):
        """GET /project/{name} when not found."""
        mock_store = MagicMock()
        mock_store.get_project.return_value = None
        mock_store_cls.return_value = mock_store

        result, code = handle_project("GET", "nonexistent", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 404

    @patch("yuleosh.store.Store")
    def test_create_project(self, mock_store_cls):
        """POST /project creates project."""
        mock_store = MagicMock()
        mock_store.get_project.return_value = {
            "name": "newproj",
            "description": "desc",
            "spec_path": "",
        }
        mock_store_cls.return_value = mock_store

        result, code = handle_project(
            "POST", "", {"name": "newproj", "description": "desc"}, {}
        , current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200
        assert result["data"]["name"] == "newproj"

    @patch("yuleosh.store.Store")
    def test_create_project_no_name(self, mock_store_cls):
        """POST /project without name returns 400."""
        result, code = handle_project("POST", "", {"description": "desc"}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 400

    @patch("yuleosh.store.Store")
    def test_create_project_with_spec_path(self, mock_store_cls):
        """POST /project with spec_path."""
        mock_store = MagicMock()
        mock_store.get_project.return_value = {
            "name": "p", "description": "d", "spec_path": "spec.md"
        }
        mock_store_cls.return_value = mock_store

        result, code = handle_project(
            "POST", "", {"name": "p", "spec_path": "spec.md"}, {}
        , current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200

    @patch("yuleosh.store.Store")
    def test_project_stats(self, mock_store_cls):
        """GET /project/stats returns aggregated stats."""
        mock_store = MagicMock()
        mock_count = MagicMock()
        mock_count.fetchone.return_value = {"c": 5}
        mock_status = MagicMock()
        mock_status.fetchall.return_value = [{"status": "completed", "c": 3}]
        mock_store.conn.execute.side_effect = [
            mock_count, mock_count, mock_count, mock_count, mock_count,
            mock_status,
        ]
        mock_store_cls.return_value = mock_store

        result, code = handle_project("GET", "stats", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 200

    def test_unsupported_method(self):
        """PUT returns 405."""
        result, code = handle_project("PUT", "", {}, {}, current_user={"user_id": 1, "org_id": 1, "email": "t@t.com", "role": "admin"})
        assert code == 405
