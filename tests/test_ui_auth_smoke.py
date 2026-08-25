"""Smoke tests for yuleosh.ui.auth — authentication module."""

# @tests src/yuleosh/ui/
import os, sys, json
from pathlib import Path
from unittest.mock import patch, MagicMock
# A5 (v3.8.0): path bootstrap removed — pytest.ini pythonpath=src


class TestUiAuth:
    def test_import_vars(self):
        from yuleosh.ui.auth import AUTH_ENABLED, SESSION_TTL, API_KEY
        assert isinstance(AUTH_ENABLED, bool)
        assert isinstance(SESSION_TTL, int)

    def test_is_authenticated(self):
        from yuleosh.ui.auth import is_authenticated
        result = is_authenticated({})
        assert isinstance(result, bool)

    def test_has_login_page(self):
        from yuleosh.ui.auth import LOGIN_PAGE
        assert isinstance(LOGIN_PAGE, str)
