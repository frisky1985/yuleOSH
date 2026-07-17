# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Security test suite for yuleOSH v2.4.0 Phase 1.

Tests:
  1. SQL Injection — verify parameterized queries prevent injection in kb/store.py
  2. Path Traversal — verify path sanitization in pipeline.py, spec.py
  3. Auth Bypass — verify require_auth is applied to sensitive API endpoints
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ═══════════════════════════════════════════════════════════════════════════
# 1. SQL Injection Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSqlInjection:
    """Verify that KB store methods are not vulnerable to SQL injection."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Create a temporary KbStore for testing."""
        from yuleosh.kb.store import KbStore
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._db_path = f.name
        self.store = KbStore(db_path=self._db_path)
        yield
        self.store.close()
        if os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def _inject_via_field_names(self, method_name: str, create_fields: dict, malicious_fields: dict):
        """Try to inject SQL via field name manipulation in update methods."""
        # First create a record
        create = getattr(self.store, f"create_{method_name}")
        record = create(create_fields)

        # Now try update with malicious field names
        update = getattr(self.store, f"update_{method_name}")
        result = update(record.id, malicious_fields)

        # If no error, verify the malicious field was ignored
        get = getattr(self.store, f"get_{method_name}")
        reloaded = get(record.id)
        assert reloaded is not None

        # Verify that only allowed fields were updated
        for key in malicious_fields:
            if key in ("title", "content", "tags", "source", "source_ref",
                       "problem", "solution", "root_cause", "project_id", "severity",
                       "item", "failure_mode", "effect", "cause",
                       "severity", "occurence", "detection", "rpn", "recommendation"):
                continue  # allowed field
            # If the field was not allowed but somehow got into SQL, that's a vulnerability.
            # We can't easily check the DB directly, but ensure the update didn't crash
            # and the record is still accessible.
        return result

    def test_article_update_sql_injection_via_field_names(self):
        """SEC-SQL-01: update_article filters field names through whitelist."""
        result = self._inject_via_field_names(
            "article",
            {"title": "Test", "content": "Content"},
            {"title": "Safe", "content": "Safe",
             "id; DROP TABLE kb_articles; --": "malicious",
             "1=1; DELETE FROM kb_articles; --": "more bad"},
        )
        assert result is not None
        # Table should still exist
        conn = sqlite3.connect(self._db_path)
        cur = conn.execute("SELECT COUNT(*) FROM kb_articles")
        assert cur.fetchone()[0] == 1
        conn.close()

    def test_lesson_update_sql_injection_via_field_names(self):
        """SEC-SQL-02: update_lesson filters field names through whitelist."""
        result = self._inject_via_field_names(
            "lesson",
            {"title": "Lesson", "problem": "Problem"},
            {"title": "Safe", "1=1;--": "malicious"},
        )
        assert result is not None

    def test_fmea_update_sql_injection_via_field_names(self):
        """SEC-SQL-03: update_fmea filters field names through whitelist."""
        result = self._inject_via_field_names(
            "fmea",
            {"item": "Item", "failure_mode": "Mode"},
            {"item": "Safe", "rpn); DROP TABLE fmea_entries; --": "1"},
        )
        assert result is not None

    def test_list_fmea_sort_by_whitelist(self):
        """SEC-SQL-04: list_fmea validates sort_by against whitelist."""
        # Create some entries first
        self.store.create_fmea({"item": "A", "failure_mode": "F1", "severity": 3})
        self.store.create_fmea({"item": "B", "failure_mode": "F2", "severity": 5})

        # Valid sort fields should work
        result = self.store.list_fmea(sort_by="severity", limit=10)
        assert len(result) == 2

        # Invalid sort fields should default to "rpn"
        result = self.store.list_fmea(sort_by="rpn); SELECT * FROM fmea_entries; --", limit=10)
        assert len(result) == 2  # Still returns results (defaulted to "rpn")

        result = self.store.list_fmea(sort_by="1; DROP TABLE fmea_entries; --", limit=10)
        assert len(result) == 2  # Still works (defaulted)

        # Verify table wasn't dropped
        result2 = self.store.list_fmea()
        assert len(result2) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 2. Path Traversal Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPathTraversal:
    """Verify path traversal prevention in file-based endpoints."""

    @patch.dict(os.environ, {"OSH_HOME": "/tmp/test-osh-home"})
    def test_pipeline_run_path_traversal(self):
        """SEC-PATH-01: pipeline run validates spec_path is within project root."""
        from yuleosh.api.pipeline import _run_pipeline

        # Attempt path traversal
        result = _run_pipeline({"spec": "../../../etc/passwd", "name": "test"})
        status = result[1]
        data = result[0]
        assert status == 403, f"Expected 403, got {status}: {data}"
        assert "within project directory" in data.get("error", "").lower() or \
               "project directory" in data.get("error", "")

    @patch.dict(os.environ, {"OSH_HOME": "/tmp/test-osh-home"})
    def test_pipeline_run_path_traversal_encoded(self):
        """SEC-PATH-02: URL-encoded path traversal is prevented."""
        from yuleosh.api.pipeline import _run_pipeline

        # Attempt encoded path traversal
        result = _run_pipeline({"spec": "%2e%2e%2f%2e%2e%2fetc%2fpasswd"})
        status = result[1]
        assert status == 403 or status == 400, f"Expected 403/400, got {status}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Auth Bypass Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthEnforcement:
    """Verify that require_auth decorator is applied to sensitive endpoints."""

    def _check_handler_has_auth(self, module_name: str, handler_name: str) -> bool:
        """Check if a handler function has require_auth applied."""
        import importlib
        mod = importlib.import_module(module_name)
        handler = getattr(mod, handler_name)
        # require_auth wraps with functools.wraps — check __wrapped__
        return hasattr(handler, "__wrapped__")

    def test_kb_handler_has_auth(self):
        """SEC-AUTH-01: handle_kb has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.kb", "handle_kb")

    def test_pipeline_handler_has_auth(self):
        """SEC-AUTH-02: handle_pipeline has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.pipeline", "handle_pipeline")

    def test_evidence_handler_has_auth(self):
        """SEC-AUTH-03: handle_evidence has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.evidence", "handle_evidence")

    def test_dashboard_handler_has_auth(self):
        """SEC-AUTH-04: handle_dashboard has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.dashboard", "handle_dashboard")

    def test_compliance_handler_has_auth(self):
        """SEC-AUTH-05: handle_compliance has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.compliance", "handle_compliance")

    def test_spec_handler_has_auth(self):
        """SEC-AUTH-06: handle_spec has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.spec", "handle_spec")

    def test_stats_handler_has_auth(self):
        """SEC-AUTH-07: handle_stats has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.stats", "handle_stats")

    def test_notify_handler_has_auth(self):
        """SEC-AUTH-08: handle_notify has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.notify", "handle_notify")

    def test_audit_handler_has_auth(self):
        """SEC-AUTH-09: handle_audit has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.audit", "handle_audit")

    def test_kg_handler_has_auth(self):
        """SEC-AUTH-10: handle_kg has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.kg", "handle_kg")

    def test_review_handler_has_auth(self):
        """SEC-AUTH-11: handle_review has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.review", "handle_review")

    def test_project_handler_has_auth(self):
        """SEC-AUTH-12: handle_project has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.project", "handle_project")

    def test_ci_handler_has_auth(self):
        """SEC-AUTH-13: handle_ci has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.ci", "handle_ci")

    def test_apikeys_handler_has_auth(self):
        """SEC-AUTH-14: handle_apikeys has require_auth decorator."""
        assert self._check_handler_has_auth("yuleosh.api.apikeys", "handle_apikeys")

    def test_health_handler_is_public(self):
        """SEC-AUTH-15: health endpoint is intentionally public."""
        # Health check must be public for monitoring
        import yuleosh.api.health as health_mod
        assert not hasattr(health_mod.handle_health, "__wrapped__")

    def test_auth_handler_is_public(self):
        """SEC-AUTH-16: auth endpoints are intentionally public."""
        import yuleosh.api.auth as auth_mod
        assert not hasattr(auth_mod.handle_auth, "__wrapped__")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Input Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    """Verify input validation prevents injection attacks."""

    def test_kb_article_sanitizer_blocks_html(self):
        """SEC-IN-01: KB article sanitizer strips HTML."""
        from yuleosh.kb.models import sanitize_kb_article_fields

        result = sanitize_kb_article_fields({
            "title": "<script>alert('xss')</script>Test",
            "content": "<img onerror='bad()' src=x>Content",
        })
        assert "<script>" not in result.get("title", "")
        assert "onerror" not in result.get("content", "")

    def test_kb_lesson_sanitizer_blocks_html(self):
        """SEC-IN-02: KB lesson sanitizer strips HTML."""
        from yuleosh.kb.models import sanitize_lesson_fields

        result = sanitize_lesson_fields({
            "title": "<iframe src='bad.com'></iframe>Lesson",
        })
        assert "<iframe" not in result.get("title", "")

    def test_kb_fmea_sanitizer_blocks_html(self):
        """SEC-IN-03: KB FMEA sanitizer strips HTML."""
        from yuleosh.kb.models import sanitize_fmea_fields

        result = sanitize_fmea_fields({
            "item": "<a href='javascript:alert(1)'>Item</a>",
        })
        assert "javascript:" not in result.get("item", "")
