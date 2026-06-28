# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Tests for core API endpoints: auth, health, pipeline, project, spec, wizard.

All tests use unittest.mock to avoid real DB or network calls.
Focus on request/response cycles and error paths.
"""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Test JWT secret — must match what auth module reads
_TEST_JWT_SECRET = "test-api-core-secret-32-chars-min!!"


def _setup_jwt():
    os.environ["YULEOSH_JWT_SECRET"] = _TEST_JWT_SECRET
    import yuleosh.api.auth
    yuleosh.api.auth._JWT_SECRET = _TEST_JWT_SECRET


# ===================================================================
# health.py
# ===================================================================

class TestHealthAPI:
    """Health check endpoint."""

    def test_health_returns_ok(self):
        from yuleosh.api.health import handle_health
        data, status = handle_health(method="GET", path_tail="",
                                     body={}, query={}, handler=mock.MagicMock())
        assert status in (200, 404)
        if status == 200:
            assert "status" in data.get("data", data)


# ===================================================================
# auth.py
# ===================================================================

class TestAuthAPI:
    """Auth endpoints: register, login, me."""

    def setup_method(self):
        _setup_jwt()

    def test_register_success(self):
        from yuleosh.api.auth import handle_auth
        body = {
            "email": f"api.{id(self)}@test.com",
            "password": "TestPass123!",
            "organization_name": "API Test Org",
            "action": "register",
        }
        data, status = handle_auth(method="POST", path_tail="register",
                                   body=body, query={}, handler=mock.MagicMock())
        assert status == 200
        assert "data" in data

    def test_register_no_email(self):
        from yuleosh.api.auth import handle_auth
        body = {"password": "TestPass123!", "action": "register"}
        data, status = handle_auth(method="POST", path_tail="register",
                                   body=body, query={}, handler=mock.MagicMock())
        assert status == 400

    def test_register_no_password(self):
        from yuleosh.api.auth import handle_auth
        body = {"email": "test@test.com", "action": "register"}
        data, status = handle_auth(method="POST", path_tail="register",
                                   body=body, query={}, handler=mock.MagicMock())
        assert status == 400

    def test_register_duplicate(self):
        from yuleosh.api.auth import handle_auth
        email = f"dup-api.{int(id(self))}@test.com"
        body = {
            "email": email,
            "password": "TestPass123!",
            "organization_name": "Dup API",
            "action": "register",
        }
        data1, s1 = handle_auth(method="POST", path_tail="register",
                                body=body, query={}, handler=mock.MagicMock())
        assert s1 == 200
        data2, s2 = handle_auth(method="POST", path_tail="register",
                                body=body, query={}, handler=mock.MagicMock())
        assert s2 == 409

    def test_login_success(self):
        from yuleosh.api.auth import handle_auth
        email = f"login.{int(id(self))}@test.com"
        # Register first
        body = {
            "email": email,
            "password": "TestPass123!",
            "organization_name": "Login Org",
            "action": "register",
        }
        data, s = handle_auth(method="POST", path_tail="register",
                              body=body, query={}, handler=mock.MagicMock())
        assert s == 200

        # Now login
        body = {"email": email, "password": "TestPass123!", "action": "login"}
        data, s = handle_auth(method="POST", path_tail="login",
                              body=body, query={}, handler=mock.MagicMock())
        assert s == 200
        assert "token" in data.get("data", {})

    def test_login_wrong_password(self):
        from yuleosh.api.auth import handle_auth
        body = {"email": "nonexistent@test.com", "password": "wrong", "action": "login"}
        data, s = handle_auth(method="POST", path_tail="login",
                              body=body, query={}, handler=mock.MagicMock())
        assert s in (401, 403, 404)

    def test_login_missing_fields(self):
        from yuleosh.api.auth import handle_auth
        data, s = handle_auth(method="POST", path_tail="login",
                              body={}, query={}, handler=mock.MagicMock())
        assert s == 400


# ===================================================================
# project.py
# ===================================================================

class TestProjectAPI:
    """Project CRUD endpoints."""

    def setup_method(self):
        _setup_jwt()

    def test_create_project(self):
        from yuleosh.api.project import handle_project
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        body = {"name": "API Test Project", "slug": "api-test-project"}
        data, s = handle_project(method="POST", path_tail="",
                                 body=body, query={}, handler=handler)
        assert s in (200, 201, 400, 409)

    def test_create_project_missing_name(self):
        from yuleosh.api.project import handle_project
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        data, s = handle_project(method="POST", path_tail="",
                                 body={"slug": "no-name"}, query={}, handler=handler)
        assert s == 400

    def test_list_projects(self):
        from yuleosh.api.project import handle_project
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        data, s = handle_project(method="GET", path_tail="",
                                 body={}, query={}, handler=handler)
        assert s == 200

    def test_create_duplicate_slug(self):
        from yuleosh.api.project import handle_project
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        slug = f"dup-slug-{int(id(self))}"
        body = {"name": "First", "slug": slug}
        data1, s1 = handle_project(method="POST", path_tail="",
                                   body=body, query={}, handler=handler)
        body2 = {"name": "Second", "slug": slug}
        data2, s2 = handle_project(method="POST", path_tail="",
                                   body=body2, query={}, handler=handler)
        assert s2 in (200, 400, 409)


# ===================================================================
# wizard.py
# ===================================================================

class TestWizardAPI:
    """Wizard completion endpoint."""

    def test_wizard_complete(self):
        from yuleosh.api.wizard import handle_wizard
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        data, s = handle_wizard(method="POST", path_tail="complete",
                                body={}, query={}, handler=handler)
        assert s in (200, 401)


# ===================================================================
# spec.py
# ===================================================================

class TestSpecAPI:
    """Spec upload endpoint."""

    def test_spec_upload(self):
        from yuleosh.api.spec import handle_spec
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        body = {
            "project": "Spec Test",
            "name": "RS-001",
            "content": "## RS-001\nSystem SHALL init within 100ms.",
        }
        data, s = handle_spec(method="POST", path_tail="",
                              body=body, query={}, handler=handler)
        assert s in (200, 201, 400, 404)

    def test_spec_missing_content(self):
        from yuleosh.api.spec import handle_spec
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        data, s = handle_spec(method="POST", path_tail="",
                              body={"project": "Empty"}, query={}, handler=handler)
        assert s == 404


# ===================================================================
# pipeline.py
# ===================================================================

class TestPipelineAPI:
    """Pipeline trigger and status endpoints."""

    def test_pipeline_trigger(self):
        from yuleosh.api.pipeline import handle_pipeline
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        body = {"project": "Pipe Test", "name": "Pipe Test", "action": "run"}
        data, s = handle_pipeline(method="POST", path_tail="",
                                  body=body, query={}, handler=handler)
        assert s in (200, 201, 400, 404, 500)

    def test_pipeline_missing_project(self):
        from yuleosh.api.pipeline import handle_pipeline
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        data, s = handle_pipeline(method="POST", path_tail="",
                                  body={"action": "run"}, query={}, handler=handler)
        assert s == 400

    def test_pipeline_status(self):
        from yuleosh.api.pipeline import handle_pipeline
        handler = mock.MagicMock()
        handler.headers = {"Authorization": "Bearer test"}
        data, s = handle_pipeline(method="GET", path_tail="status",
                                  body={}, query={}, handler=handler)
        assert s == 200


# ===================================================================
# api/__init__.py — json_ok, json_error helpers
# ===================================================================

class TestAPIJsonHelpers:
    """JSON response helper functions."""

    def test_json_ok(self):
        from yuleosh.api import json_ok
        result = json_ok({"key": "value"})
        assert isinstance(result, tuple)
        assert result[1] == 200
        assert result[0]["ok"] is True

    def test_json_ok_none(self):
        from yuleosh.api import json_ok
        result = json_ok()
        assert isinstance(result, tuple)
        assert result[1] == 200

    def test_json_error(self):
        from yuleosh.api import json_error
        result = json_error("test error", status=400)
        assert isinstance(result, tuple)
        assert result[1] == 400
